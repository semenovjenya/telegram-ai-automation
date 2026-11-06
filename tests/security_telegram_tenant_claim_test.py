"""Cross-service tests for service-signed Telegram tenant claims."""

import importlib.util
import time
from http import HTTPStatus
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SIGNING_KEY = "telegram-tenant-signing-key-0123456789-ABCDEF"
API_KEY = "telegram-service-api-key-0123456789-ABCDEF"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_mock(monkeypatch):
    monkeypatch.setenv("API_KEY", API_KEY)
    monkeypatch.setenv("TELEGRAM_TENANT_SIGNING_KEY", SIGNING_KEY)
    return _load(
        ROOT / "compose" / "telegram-mock" / "server.py",
        "security_telegram_mock",
    )


def test_mock_requires_api_key_and_rejects_tenant_spoof_and_replay(monkeypatch) -> None:
    claims = _load(
        ROOT / "auth-backend" / "tenant_claims.py",
        "security_tenant_claims",
    )
    telegram_mock = _load_mock(monkeypatch)
    now_ns = time.time_ns()
    headers = claims.build_tenant_claim_headers(
        signing_key=SIGNING_KEY,
        tenant_id=7,
        method="GET",
        normalized_path="api/chats",
        timestamp_ns=now_ns,
    )

    assert telegram_mock._api_key_matches(API_KEY)
    assert not telegram_mock._api_key_matches("")
    assert not telegram_mock._api_key_matches("wrong-key")

    spoofed = {**headers, "X-Tenant-ID": "8"}
    with pytest.raises(telegram_mock.TenantClaimError) as spoof_error:
        telegram_mock.verify_tenant_claim(
            spoofed,
            "GET",
            "api/chats",
            now_ns=now_ns,
        )
    assert spoof_error.value.status == HTTPStatus.UNAUTHORIZED

    assert (
        telegram_mock.verify_tenant_claim(
            headers,
            "GET",
            "api/chats",
            now_ns=now_ns,
        )
        == 7
    )
    with pytest.raises(telegram_mock.TenantClaimError) as replay_error:
        telegram_mock.verify_tenant_claim(
            headers,
            "GET",
            "api/chats",
            now_ns=now_ns,
        )
    assert replay_error.value.status == HTTPStatus.CONFLICT


def test_mock_rejects_expired_and_path_bound_claims(monkeypatch) -> None:
    claims = _load(
        ROOT / "auth-backend" / "tenant_claims.py",
        "security_tenant_claims_expired",
    )
    telegram_mock = _load_mock(monkeypatch)
    now_ns = time.time_ns()
    expired_ns = (
        now_ns
        - (telegram_mock.CLAIM_MAX_AGE_SECONDS + 1)
        * telegram_mock.NANOSECONDS_PER_SECOND
    )
    expired = claims.build_tenant_claim_headers(
        signing_key=SIGNING_KEY,
        tenant_id=7,
        method="GET",
        normalized_path="api/chats",
        timestamp_ns=expired_ns,
    )
    with pytest.raises(telegram_mock.TenantClaimError) as expired_error:
        telegram_mock.verify_tenant_claim(
            expired,
            "GET",
            "api/chats",
            now_ns=now_ns,
        )
    assert expired_error.value.status == HTTPStatus.UNAUTHORIZED

    fresh = claims.build_tenant_claim_headers(
        signing_key=SIGNING_KEY,
        tenant_id=7,
        method="GET",
        normalized_path="api/chats",
        timestamp_ns=now_ns,
    )
    with pytest.raises(telegram_mock.TenantClaimError) as path_error:
        telegram_mock.verify_tenant_claim(
            fresh,
            "GET",
            "api/chats/other/messages",
            now_ns=now_ns,
        )
    assert path_error.value.status == HTTPStatus.UNAUTHORIZED


def test_mock_message_contract_accepts_only_bounded_text_json(monkeypatch) -> None:
    telegram_mock = _load_mock(monkeypatch)

    assert telegram_mock._validated_chat_message_payload({"text": "hello"}) == "hello"

    for invalid_payload in (
        None,
        {},
        {"text": ""},
        {"text": "   "},
        {"text": 123},
        {"text": "hello", "chat_id": "other"},
        {"text": "x" * (telegram_mock.MAX_CHAT_MESSAGE_TEXT_LENGTH + 1)},
    ):
        with pytest.raises(ValueError):
            telegram_mock._validated_chat_message_payload(invalid_payload)


def test_message_claim_rejects_body_tampering_before_consumption(monkeypatch) -> None:
    claims = _load(
        ROOT / "auth-backend" / "tenant_claims.py",
        "security_tenant_claims_body",
    )
    telegram_mock = _load_mock(monkeypatch)
    now_ns = time.time_ns()
    original_body = b'{"text":"approved"}'
    tampered_body = b'{"text":"attacker changed this"}'
    headers = claims.build_tenant_claim_headers(
        signing_key=SIGNING_KEY,
        tenant_id=7,
        method="POST",
        normalized_path="api/chats/chat-1/messages",
        body=original_body,
        timestamp_ns=now_ns,
    )

    with pytest.raises(telegram_mock.TenantClaimError) as tamper_error:
        telegram_mock.verify_tenant_claim(
            headers,
            "POST",
            "api/chats/chat-1/messages",
            tampered_body,
            now_ns=now_ns,
        )
    assert tamper_error.value.status == HTTPStatus.UNAUTHORIZED

    assert (
        telegram_mock.verify_tenant_claim(
            headers,
            "POST",
            "api/chats/chat-1/messages",
            original_body,
            now_ns=now_ns,
        )
        == 7
    )


def test_mock_access_log_drops_query_string(monkeypatch) -> None:
    telegram_mock = _load_mock(monkeypatch)
    log_entries = []
    handler = object.__new__(telegram_mock.TelegramMockHandler)
    handler.command = "POST"
    handler.path = "/api/chats/chat-1/messages?text=sentinel-private-message"
    handler.request_version = "HTTP/1.1"
    handler.log_message = lambda format, *args: log_entries.append(format % args)

    handler.log_request(405, 20)

    assert log_entries == ['"POST /api/chats/chat-1/messages HTTP/1.1" 405 20']
    assert "sentinel-private-message" not in log_entries[0]
