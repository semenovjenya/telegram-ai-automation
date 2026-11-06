"""Read-only Telegram adapter used by the public demo stack."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8010"))
MAX_BODY_BYTES = 64 * 1024
MAX_CHAT_MESSAGE_TEXT_LENGTH = 12_000
API_KEY = os.getenv("API_KEY", "").strip()
TENANT_SIGNING_KEY = os.getenv("TELEGRAM_TENANT_SIGNING_KEY", "").strip()

CLAIM_VERSION = "2"
TENANT_ID_HEADER = "X-Tenant-ID"
TENANT_TIMESTAMP_HEADER = "X-Tenant-Timestamp"
TENANT_SIGNATURE_HEADER = "X-Tenant-Signature"
TENANT_VERSION_HEADER = "X-Tenant-Claim-Version"
TENANT_BODY_SHA256_HEADER = "X-Tenant-Body-SHA256"
NANOSECONDS_PER_SECOND = 1_000_000_000


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


CLAIM_MAX_AGE_SECONDS = _bounded_env_int(
    "TELEGRAM_TENANT_CLAIM_MAX_AGE_SECONDS", 30, 1, 300
)
CLAIM_FUTURE_SKEW_SECONDS = _bounded_env_int(
    "TELEGRAM_TENANT_CLAIM_FUTURE_SKEW_SECONDS", 5, 0, 60
)
CLAIM_REPLAY_MAX_ENTRIES = _bounded_env_int(
    "TELEGRAM_TENANT_REPLAY_MAX_ENTRIES", 10_000, 1, 1_000_000
)
_seen_claims: dict[str, int] = {}
_seen_claims_lock = threading.Lock()


class TenantClaimError(Exception):
    def __init__(self, status: HTTPStatus, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _header(headers: Mapping[str, str], name: str) -> str:
    value = headers.get(name)
    if value is not None:
        return value.strip()
    expected = name.casefold()
    for header_name, header_value in headers.items():
        if header_name.casefold() == expected:
            return header_value.strip()
    return ""


def _canonical_tenant_claim(
    tenant_id: int,
    timestamp_ns: int,
    method: str,
    normalized_path: str,
    body_sha256: str,
) -> bytes:
    path = normalized_path.strip().lstrip("/")
    return (
        f"v{CLAIM_VERSION}\n{tenant_id}\n{timestamp_ns}\n"
        f"{method.strip().upper()}\n{path}\n{body_sha256}"
    ).encode()


def _tenant_signature(
    signing_key: str,
    tenant_id: int,
    timestamp_ns: int,
    method: str,
    normalized_path: str,
    body_sha256: str,
) -> str:
    return hmac.new(
        signing_key.encode("utf-8"),
        _canonical_tenant_claim(
            tenant_id,
            timestamp_ns,
            method,
            normalized_path,
            body_sha256,
        ),
        hashlib.sha256,
    ).hexdigest()


def verify_tenant_claim(
    headers: Mapping[str, str],
    method: str,
    normalized_path: str,
    body: bytes = b"",
    *,
    now_ns: int | None = None,
) -> int:
    """Verify freshness/signature and consume a claim exactly once."""

    if not TENANT_SIGNING_KEY:
        raise TenantClaimError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "Tenant claim verification is not configured",
        )

    version = _header(headers, TENANT_VERSION_HEADER)
    tenant_text = _header(headers, TENANT_ID_HEADER)
    timestamp_text = _header(headers, TENANT_TIMESTAMP_HEADER)
    provided_body_sha256 = _header(headers, TENANT_BODY_SHA256_HEADER)
    provided_signature = _header(headers, TENANT_SIGNATURE_HEADER)
    try:
        tenant_id = int(tenant_text)
        timestamp_ns = int(timestamp_text)
    except ValueError:
        raise TenantClaimError(
            HTTPStatus.UNAUTHORIZED, "Invalid tenant claim"
        ) from None

    if (
        version != CLAIM_VERSION
        or tenant_id <= 0
        or timestamp_ns <= 0
        or len(provided_body_sha256) != 64
        or not provided_signature
    ):
        raise TenantClaimError(HTTPStatus.UNAUTHORIZED, "Invalid tenant claim")

    current_ns = time.time_ns() if now_ns is None else now_ns
    oldest = current_ns - CLAIM_MAX_AGE_SECONDS * NANOSECONDS_PER_SECOND
    newest = current_ns + CLAIM_FUTURE_SKEW_SECONDS * NANOSECONDS_PER_SECOND
    if timestamp_ns < oldest or timestamp_ns > newest:
        raise TenantClaimError(HTTPStatus.UNAUTHORIZED, "Expired tenant claim")

    expected_body_sha256 = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(provided_body_sha256, expected_body_sha256):
        raise TenantClaimError(HTTPStatus.UNAUTHORIZED, "Invalid tenant claim")

    expected_signature = _tenant_signature(
        TENANT_SIGNING_KEY,
        tenant_id,
        timestamp_ns,
        method,
        normalized_path,
        provided_body_sha256,
    )
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise TenantClaimError(HTTPStatus.UNAUTHORIZED, "Invalid tenant claim")

    expires_at = timestamp_ns + CLAIM_MAX_AGE_SECONDS * NANOSECONDS_PER_SECOND
    with _seen_claims_lock:
        expired = [
            signature
            for signature, expiry in _seen_claims.items()
            if expiry < current_ns
        ]
        for signature in expired:
            del _seen_claims[signature]

        if provided_signature in _seen_claims:
            raise TenantClaimError(HTTPStatus.CONFLICT, "Tenant claim replayed")
        if len(_seen_claims) >= CLAIM_REPLAY_MAX_ENTRIES:
            raise TenantClaimError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Tenant replay protection is at capacity",
            )
        _seen_claims[provided_signature] = expires_at

    return tenant_id


def _is_messages_path(path: str) -> bool:
    segments = path.strip("/").split("/")
    return (
        len(segments) == 4
        and segments[:2] == ["api", "chats"]
        and segments[3] == "messages"
    )


def _api_key_matches(provided: str) -> bool:
    return bool(API_KEY and provided and hmac.compare_digest(provided, API_KEY))


def _validated_chat_message_payload(payload: object) -> str:
    """Validate the body-only message contract shared with a live adapter."""

    if not isinstance(payload, dict) or set(payload) != {"text"}:
        raise ValueError("Chat message body must contain only text")
    message_text = payload["text"]
    if (
        not isinstance(message_text, str)
        or not message_text.strip()
        or len(message_text) > MAX_CHAT_MESSAGE_TEXT_LENGTH
    ):
        raise ValueError(
            "Chat message text must contain between 1 and 12000 characters"
        )
    return message_text


DEMO_CHANNEL = {
    "username": "demo_analytics_channel",
    "title": "Демо-канал аналитики",
    "subscribers": 12840,
    "engagement_rate_percent": 18.7,
    "avg_reach_24h": 4100,
    "avg_reach_48h": 5300,
    "avg_reach_72h": 6100,
    "channel_topic": "Lifestyle and creator economy",
    "data_source": "synthetic-demo",
}

DEMO_DOCUMENTS = (
    {
        "text": "The demo audience is most active around practical creator-economy content.",
        "source": "demo://demo_analytics_channel/audience",
    },
    {
        "text": "Short case studies and clear calls to action have the strongest synthetic engagement.",
        "source": "demo://demo_analytics_channel/content-patterns",
    },
    {
        "text": "This result is synthetic and exists only to exercise the public RAG integration path.",
        "source": "demo://demo_analytics_channel/disclaimer",
    },
)


class TelegramMockHandler(BaseHTTPRequestHandler):
    server_version = "telegram-adapter-demo/1.0"

    def _write_json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None

        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            return None

        return self.rfile.read(content_length)

    def _read_json(self, body: bytes | None = None) -> dict[str, object] | None:
        raw_body = self._read_body() if body is None else body
        if raw_body is None:
            return None
        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        return payload if isinstance(payload, dict) else None

    def _require_authentication(self) -> bool:
        provided = self.headers.get("X-API-Key", "")
        if _api_key_matches(provided):
            return True
        self._write_json(HTTPStatus.UNAUTHORIZED, {"detail": "Unauthorized"})
        return False

    def _require_tenant_claim(
        self,
        method: str,
        path: str,
        body: bytes = b"",
    ) -> int | None:
        try:
            return verify_tenant_claim(
                self.headers,
                method,
                path.lstrip("/"),
                body,
            )
        except TenantClaimError as exc:
            self._write_json(exc.status, {"detail": exc.detail})
            return None

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path

        if path == "/health":
            self._write_json(
                HTTPStatus.OK,
                {"status": "healthy", "mode": "synthetic-read-only"},
            )
            return

        if not self._require_authentication():
            return

        if path == "/api/chats":
            if self._require_tenant_claim("GET", path) is None:
                return
            self._write_json(
                HTTPStatus.OK, {"chats": [], "mode": "synthetic-read-only"}
            )
            return

        if _is_messages_path(path):
            if self._require_tenant_claim("GET", path) is None:
                return
            self._write_json(
                HTTPStatus.OK,
                {"messages": [], "mode": "synthetic-read-only"},
            )
            return

        channel_prefix = "/api/channels/"
        if path.startswith(channel_prefix):
            username = unquote(path.removeprefix(channel_prefix)).lstrip("@").lower()
            if username == DEMO_CHANNEL["username"]:
                self._write_json(
                    HTTPStatus.OK,
                    {"channel": DEMO_CHANNEL, "mode": "synthetic-read-only"},
                )
            else:
                self._write_json(
                    HTTPStatus.NOT_FOUND,
                    {"detail": "Channel is not part of the synthetic demo fixture"},
                )
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self._require_authentication():
            return
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if _is_messages_path(path):
            if parsed_url.query:
                self._write_json(
                    HTTPStatus.BAD_REQUEST,
                    {"detail": "Chat message POST does not accept query parameters"},
                )
                return
            media_type = self.headers.get("Content-Type", "").partition(";")[0]
            if media_type.strip().casefold() != "application/json":
                self._write_json(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    {"detail": "Chat messages must use application/json"},
                )
                return
            body = self._read_body()
            if body is None:
                self._write_json(
                    HTTPStatus.BAD_REQUEST,
                    {"detail": "Expected a JSON object"},
                )
                return
            if self._require_tenant_claim("POST", path, body) is None:
                return
            payload = self._read_json(body)
            try:
                _validated_chat_message_payload(payload)
            except ValueError as exc:
                self._write_json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    {"detail": str(exc)},
                )
                return
            self._write_json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"detail": "Read-only demo adapter"},
            )
            return

        if path != "/api/channel-search":
            self._write_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return

        payload = self._read_json()
        if payload is None:
            self._write_json(
                HTTPStatus.BAD_REQUEST, {"detail": "Expected a JSON object"}
            )
            return

        query = payload.get("query")
        channel = payload.get("channel")
        top_k = payload.get("top_k", 3)
        if not isinstance(query, str) or not query.strip():
            self._write_json(
                HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "query is required"}
            )
            return
        if not isinstance(channel, str) or not channel.strip():
            self._write_json(
                HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": "channel is required"}
            )
            return
        if (
            not isinstance(top_k, int)
            or isinstance(top_k, bool)
            or not 1 <= top_k <= 20
        ):
            self._write_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"detail": "top_k must be an integer between 1 and 20"},
            )
            return

        normalized_channel = channel.lstrip("@").lower()
        results = (
            list(DEMO_DOCUMENTS[:top_k])
            if normalized_channel == DEMO_CHANNEL["username"]
            else []
        )
        self._write_json(HTTPStatus.OK, results)

    def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self._require_authentication():
            return
        path = urlparse(self.path).path
        if (
            path == "/api/chats" or _is_messages_path(path)
        ) and self._require_tenant_claim(
            self.command,
            path,
        ) is None:
            return
        self._write_json(
            HTTPStatus.METHOD_NOT_ALLOWED, {"detail": "Read-only demo adapter"}
        )

    do_PATCH = do_PUT
    do_DELETE = do_PUT

    def log_request(self, code: object = "-", size: object = "-") -> None:
        """Log only the URL path so query data can never reach access logs."""

        safe_request_line = (
            f"{self.command} {urlparse(self.path).path} {self.request_version}"
        )
        self.log_message('"%s" %s %s', safe_request_line, code, size)

    def log_message(self, format: str, *args: object) -> None:
        print(f"telegram-mock: {format % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), TelegramMockHandler)
    print(f"telegram-mock listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()
