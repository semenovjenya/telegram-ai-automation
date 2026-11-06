"""Short-lived HMAC claims for the browser login-client identifier.

The opaque identifier is minted by the trusted Next.js BFF.  It is not an
authentication credential; the signature only proves that the limiter key
came through that BFF instead of from a caller-controlled forwarding header.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
import unicodedata
from collections.abc import Callable, Mapping

CLAIM_VERSION = "v1"
CLIENT_ID_HEADER = "x-login-client-id"
SIGNATURE_HEADER = "x-login-client-signature"
TIMESTAMP_HEADER = "x-login-client-timestamp"
VERSION_HEADER = "x-login-client-version"

_CLIENT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP_PATTERN = re.compile(r"[0-9]{1,10}\Z")
_MAX_USERNAME_CHARACTERS = 128
_MAX_USERNAME_BYTES = 512


class LoginClientClaimError(ValueError):
    """Raised for missing, malformed, stale, or untrusted login claims."""


def canonical_login_username(username: str) -> str:
    """Return the bounded Unicode-normalized username bound by the claim."""

    if not isinstance(username, str):
        raise LoginClientClaimError("invalid username")
    normalized = unicodedata.normalize("NFKC", username.strip())
    if (
        not normalized
        or len(normalized) > _MAX_USERNAME_CHARACTERS
        or len(normalized.encode("utf-8")) > _MAX_USERNAME_BYTES
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F for character in normalized
        )
    ):
        raise LoginClientClaimError("invalid username")
    return normalized


def _signature_payload(
    *,
    version: str,
    timestamp: int,
    client_id: str,
    username: str,
) -> bytes:
    canonical_username = canonical_login_username(username)
    username_digest = hashlib.sha256(canonical_username.encode("utf-8")).hexdigest()
    return f"{version}\n{timestamp}\n{client_id}\n{username_digest}".encode("ascii")


def build_login_client_signature(
    *,
    signing_key: str,
    timestamp: int,
    client_id: str,
    username: str,
    version: str = CLAIM_VERSION,
) -> str:
    """Build the reviewed v1 signature (also used by regression tests)."""

    if version != CLAIM_VERSION or not _CLIENT_ID_PATTERN.fullmatch(client_id):
        raise LoginClientClaimError("invalid claim fields")
    if not signing_key:
        raise LoginClientClaimError("missing signing key")
    payload = _signature_payload(
        version=version,
        timestamp=timestamp,
        client_id=client_id,
        username=username,
    )
    return hmac.new(signing_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_login_client_claim(
    headers: Mapping[str, str],
    *,
    username: str,
    signing_key: str,
    max_age_seconds: int,
    future_skew_seconds: int,
    clock: Callable[[], float] = time.time,
) -> str:
    """Verify a BFF claim and return its opaque identifier.

    Header values are validated before any expensive or stateful work.  Errors
    deliberately contain no submitted identifier so callers can log the error
    category without leaking the stable browser pseudonym.
    """

    version = headers.get(VERSION_HEADER, "")
    timestamp_text = headers.get(TIMESTAMP_HEADER, "")
    client_id = headers.get(CLIENT_ID_HEADER, "")
    signature = headers.get(SIGNATURE_HEADER, "")

    if (
        version != CLAIM_VERSION
        or not _TIMESTAMP_PATTERN.fullmatch(timestamp_text)
        or not _CLIENT_ID_PATTERN.fullmatch(client_id)
        or not _SIGNATURE_PATTERN.fullmatch(signature)
    ):
        raise LoginClientClaimError("malformed login client claim")

    timestamp = int(timestamp_text)
    now = int(clock())
    if timestamp > now + future_skew_seconds or now - timestamp > max_age_seconds:
        raise LoginClientClaimError("stale login client claim")

    expected = build_login_client_signature(
        signing_key=signing_key,
        timestamp=timestamp,
        client_id=client_id,
        username=username,
        version=version,
    )
    if not hmac.compare_digest(signature, expected):
        raise LoginClientClaimError("invalid login client claim")
    return client_id
