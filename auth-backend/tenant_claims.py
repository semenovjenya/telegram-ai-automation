"""Service-signed tenant claims for the Telegram adapter boundary."""

from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time

CLAIM_VERSION = "2"
TENANT_ID_HEADER = "X-Tenant-ID"
TENANT_TIMESTAMP_HEADER = "X-Tenant-Timestamp"
TENANT_SIGNATURE_HEADER = "X-Tenant-Signature"
TENANT_VERSION_HEADER = "X-Tenant-Claim-Version"
TENANT_BODY_SHA256_HEADER = "X-Tenant-Body-SHA256"

_timestamp_lock = threading.Lock()
_last_timestamp_ns = 0


def normalize_claim_path(path: str) -> str:
    normalized = path.strip().lstrip("/")
    if not normalized or normalized.endswith("/"):
        raise ValueError("claim path must be a canonical relative path")
    return normalized


def canonical_tenant_claim(
    tenant_id: int,
    timestamp_ns: int,
    method: str,
    normalized_path: str,
    body_sha256: str,
) -> bytes:
    if tenant_id <= 0:
        raise ValueError("tenant_id must be positive")
    if timestamp_ns <= 0:
        raise ValueError("timestamp_ns must be positive")
    canonical_path = normalize_claim_path(normalized_path)
    canonical_method = method.strip().upper()
    if not canonical_method:
        raise ValueError("method is required")
    if not re.fullmatch(r"[0-9a-f]{64}", body_sha256):
        raise ValueError("body_sha256 must be a lowercase SHA-256 digest")
    return (
        f"v{CLAIM_VERSION}\n{tenant_id}\n{timestamp_ns}\n"
        f"{canonical_method}\n{canonical_path}\n{body_sha256}"
    ).encode()


def sign_tenant_claim(
    signing_key: str,
    tenant_id: int,
    timestamp_ns: int,
    method: str,
    normalized_path: str,
    body_sha256: str,
) -> str:
    if not signing_key:
        raise ValueError("signing_key is required")
    return hmac.new(
        signing_key.encode("utf-8"),
        canonical_tenant_claim(
            tenant_id,
            timestamp_ns,
            method,
            normalized_path,
            body_sha256,
        ),
        hashlib.sha256,
    ).hexdigest()


def _next_timestamp_ns() -> int:
    global _last_timestamp_ns
    with _timestamp_lock:
        current = time.time_ns()
        _last_timestamp_ns = max(current, _last_timestamp_ns + 1)
        return _last_timestamp_ns


def build_tenant_claim_headers(
    *,
    signing_key: str,
    tenant_id: int,
    method: str,
    normalized_path: str,
    body: bytes = b"",
    timestamp_ns: int | None = None,
) -> dict[str, str]:
    issued_at = timestamp_ns if timestamp_ns is not None else _next_timestamp_ns()
    body_sha256 = hashlib.sha256(body).hexdigest()
    signature = sign_tenant_claim(
        signing_key,
        tenant_id,
        issued_at,
        method,
        normalized_path,
        body_sha256,
    )
    return {
        TENANT_VERSION_HEADER: CLAIM_VERSION,
        TENANT_ID_HEADER: str(tenant_id),
        TENANT_TIMESTAMP_HEADER: str(issued_at),
        TENANT_BODY_SHA256_HEADER: body_sha256,
        TENANT_SIGNATURE_HEADER: signature,
    }
