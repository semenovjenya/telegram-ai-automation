"""Bounded in-process login rate limiting.

This protects a single gateway process. Production deployments must also use a
distributed limiter at the ingress/edge so limits are shared across replicas.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
import unicodedata
from collections import deque
from collections.abc import Callable


class _Bucket:
    def __init__(self) -> None:
        self.attempts: deque[float] = deque()
        self.blocked_until = 0.0


class LoginRateLimiter:
    """Sliding-window limiter keyed by client and client/username pair.

    Capacity exhaustion fails closed: active entries are never evicted merely
    to admit a new identity, which would otherwise let attackers rotate keys to
    bypass the limiter.
    """

    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        block_seconds: int,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if window_seconds < 1 or block_seconds < 1:
            raise ValueError("window_seconds and block_seconds must be positive")
        if max_entries < 2:
            raise ValueError("max_entries must be at least 2")

        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._entries: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _keys(self, username: str, client_id: str) -> tuple[str, str]:
        normalized_username = (
            unicodedata.normalize("NFKC", username.strip()).casefold() or "<empty>"
        )
        normalized_client = client_id.strip() or "<unknown>"
        pair_value = f"{normalized_username}\0{normalized_client}"
        return (
            f"client:{self._digest(normalized_client)}",
            f"pair:{self._digest(pair_value)}",
        )

    def _prune_bucket(self, bucket: _Bucket, now: float) -> None:
        cutoff = now - self.window_seconds
        while bucket.attempts and bucket.attempts[0] <= cutoff:
            bucket.attempts.popleft()
        if bucket.blocked_until <= now:
            bucket.blocked_until = 0.0

    def _cleanup(self, now: float) -> None:
        expired: list[str] = []
        for key, bucket in self._entries.items():
            self._prune_bucket(bucket, now)
            if not bucket.attempts and not bucket.blocked_until:
                expired.append(key)
        for key in expired:
            del self._entries[key]

    def _capacity_retry_after(self, now: float) -> int:
        expirations = []
        for bucket in self._entries.values():
            if bucket.blocked_until > now:
                expirations.append(bucket.blocked_until)
            if bucket.attempts:
                expirations.append(bucket.attempts[0] + self.window_seconds)
        if not expirations:
            return 1
        return max(1, math.ceil(min(expirations) - now))

    def register_attempt(self, username: str, client_id: str) -> int | None:
        """Atomically admit an attempt or return ``Retry-After`` seconds."""

        now = self._clock()
        keys = self._keys(username, client_id)
        with self._lock:
            self._cleanup(now)

            missing = sum(key not in self._entries for key in keys)
            if len(self._entries) + missing > self.max_entries:
                return self._capacity_retry_after(now)

            buckets = [self._entries.setdefault(key, _Bucket()) for key in keys]
            retry_after = 0
            for bucket in buckets:
                self._prune_bucket(bucket, now)
                if bucket.blocked_until > now:
                    retry_after = max(
                        retry_after, math.ceil(bucket.blocked_until - now)
                    )
                elif len(bucket.attempts) >= self.max_attempts:
                    bucket.blocked_until = now + self.block_seconds
                    retry_after = max(retry_after, self.block_seconds)

            if retry_after:
                return max(1, retry_after)

            for bucket in buckets:
                bucket.attempts.append(now)
            return None

    def record_success(self, username: str, client_id: str) -> None:
        """Forgive the admitted success without erasing prior client failures.

        A successful authentication clears the pair scope, because the caller
        proved knowledge of that account's credential.  Only the newest client
        attempt is removed, so an attacker cannot use one known credential to
        reset a client-wide username-spraying budget.
        """

        client_key, pair_key = self._keys(username, client_id)
        with self._lock:
            self._entries.pop(pair_key, None)
            client_bucket = self._entries.get(client_key)
            if client_bucket and client_bucket.attempts:
                client_bucket.attempts.pop()
            if (
                client_bucket
                and not client_bucket.attempts
                and not client_bucket.blocked_until
            ):
                self._entries.pop(client_key, None)

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)
