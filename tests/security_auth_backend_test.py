"""Security regression tests for the JWT gateway configuration."""

import asyncio
import hashlib
import importlib.util
import json
import sys
import time
import types
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_gateway(monkeypatch):
    config = _load(ROOT / "auth-backend" / "config.py", "gateway_config")
    models = _load(ROOT / "auth-backend" / "models.py", "gateway_models")
    monkeypatch.setattr(config.settings, "AI_BRAIN_API_KEY", "a" * 48)
    monkeypatch.setattr(config.settings, "TELEGRAM_API_KEY", "t" * 48)
    monkeypatch.setattr(
        config.settings,
        "TELEGRAM_TENANT_SIGNING_KEY",
        "tenant-signing-key-0123456789-ABCDEF",
    )
    monkeypatch.setitem(sys.modules, "config", config)
    monkeypatch.setitem(sys.modules, "models", models)

    auth = types.ModuleType("auth")
    auth.login_user = lambda request: None
    auth.verify_token = lambda token: None
    middleware = types.ModuleType("middleware")

    async def get_current_user():
        return None

    middleware.get_current_user = get_current_user
    middleware.security = object()
    data_loader = types.ModuleType("data_loader")
    for name in (
        "get_dashboard_metrics",
        "get_publications",
        "get_profile",
        "get_ai_summary",
        "get_ai_recommendation",
        "get_notifications",
    ):
        setattr(data_loader, name, lambda *args, **kwargs: {})
    monkeypatch.setitem(sys.modules, "auth", auth)
    monkeypatch.setitem(sys.modules, "middleware", middleware)
    monkeypatch.setitem(sys.modules, "data_loader", data_loader)
    return _load(ROOT / "auth-backend" / "main.py", "security_auth_gateway")


def test_production_auth_settings_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    config = _load(ROOT / "auth-backend" / "config.py", "security_auth_config")

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        config.Settings(_env_file=None, ENVIRONMENT="production")

    settings = config.Settings(
        _env_file=None,
        ENVIRONMENT="production",
        JWT_SECRET_KEY="jwt-production-secret-0123456789-ABCDEF",
        DEFAULT_USERNAME="operator",
        DEFAULT_PASSWORD_HASH="pbkdf2_sha256$600000$c2FsdA==$ZGlnZXN0",
        AI_BRAIN_API_KEY="ai-brain-production-key-0123456789-ABCDEF",
        TELEGRAM_API_KEY="telegram-production-key-0123456789-ABCDEF",
        TELEGRAM_TENANT_SIGNING_KEY="tenant-production-key-0123456789-ABCDEF",
        LOGIN_CLIENT_SIGNING_KEY="login-client-production-key-0123456789-ABCDEF",
        CORS_ORIGINS="https://analytics.example.org",
    )
    assert settings.runtime_environment == "production"

    production_settings = {
        "ENVIRONMENT": "production",
        "JWT_SECRET_KEY": "jwt-production-secret-0123456789-ABCDEF",
        "DEFAULT_USERNAME": "operator",
        "DEFAULT_PASSWORD_HASH": "pbkdf2_sha256$600000$c2FsdA==$ZGlnZXN0",
        "AI_BRAIN_API_KEY": "ai-brain-production-key-0123456789-ABCDEF",
        "TELEGRAM_API_KEY": "telegram-production-key-0123456789-ABCDEF",
        "TELEGRAM_TENANT_SIGNING_KEY": ("tenant-production-key-0123456789-ABCDEF"),
        "LOGIN_CLIENT_SIGNING_KEY": ("login-client-production-key-0123456789-ABCDEF"),
        "CORS_ORIGINS": "https://analytics.example.org",
    }

    staging_settings = config.Settings(
        _env_file=None,
        **{**production_settings, "ENVIRONMENT": "staging"},
    )
    assert staging_settings.runtime_environment == "staging"

    for unknown_environment in ("prod", "developmnt", "local", ""):
        with pytest.raises(ValidationError, match="ENVIRONMENT"):
            config.Settings(_env_file=None, ENVIRONMENT=unknown_environment)

    with pytest.raises(ValueError, match="DASHBOARD_DATA_SOURCE.*live"):
        config.Settings(
            _env_file=None,
            **production_settings,
            DASHBOARD_DATA_SOURCE="synthetic-demo",
        )

    with pytest.raises(ValueError, match="DEFAULT_PASSWORD.*empty"):
        config.Settings(
            _env_file=None,
            **production_settings,
            DEFAULT_PASSWORD="plaintext-production-password",
        )

    with pytest.raises(ValueError, match="DEFAULT_PASSWORD.*empty"):
        config.Settings(
            _env_file=None,
            **{**production_settings, "ENVIRONMENT": "staging"},
            DEFAULT_PASSWORD="plaintext-staging-password",
        )

    with pytest.raises(ValueError, match="exact HTTPS origins"):
        config.Settings(
            _env_file=None,
            **{**production_settings, "CORS_ORIGINS": "http://analytics.example.org"},
        )

    with pytest.raises(ValueError, match="must be distinct"):
        config.Settings(
            _env_file=None,
            ENVIRONMENT="production",
            JWT_SECRET_KEY="jwt-production-secret-0123456789-ABCDEF",
            DEFAULT_USERNAME="operator",
            DEFAULT_PASSWORD_HASH="pbkdf2_sha256$600000$c2FsdA==$ZGlnZXN0",
            AI_BRAIN_API_KEY="ai-brain-production-key-0123456789-ABCDEF",
            TELEGRAM_API_KEY="shared-production-key-0123456789-ABCDEF",
            TELEGRAM_TENANT_SIGNING_KEY=("shared-production-key-0123456789-ABCDEF"),
            LOGIN_CLIENT_SIGNING_KEY=("login-client-production-key-0123456789-ABCDEF"),
            CORS_ORIGINS="https://analytics.example.org",
        )

    with pytest.raises(ValueError, match="LOGIN_CLIENT_SIGNING_KEY.*distinct"):
        config.Settings(
            _env_file=None,
            **{
                **production_settings,
                "LOGIN_CLIENT_SIGNING_KEY": production_settings["JWT_SECRET_KEY"],
            },
        )

    with pytest.raises(ValueError, match="LOGIN_CLIENT_SIGNING_KEY"):
        config.Settings(
            _env_file=None,
            **{**production_settings, "LOGIN_CLIENT_SIGNING_KEY": ""},
        )

    with pytest.raises(ValueError, match="DASHBOARD_DATA_SOURCE"):
        config.Settings(
            _env_file=None,
            DASHBOARD_DATA_SOURCE="unreviewed-source",
        )


@pytest.mark.parametrize(
    ("first_field", "second_field"),
    (
        ("JWT_SECRET_KEY", "AI_BRAIN_API_KEY"),
        ("AI_BRAIN_API_KEY", "TELEGRAM_API_KEY"),
    ),
)
def test_production_auth_settings_reject_any_reused_secret(
    monkeypatch,
    first_field: str,
    second_field: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    config = _load(ROOT / "auth-backend" / "config.py", "unique_secret_config")
    production_settings = {
        "ENVIRONMENT": "production",
        "JWT_SECRET_KEY": "jwt-production-secret-0123456789-ABCDEF",
        "DEFAULT_USERNAME": "operator",
        "DEFAULT_PASSWORD_HASH": "pbkdf2_sha256$600000$c2FsdA==$ZGlnZXN0",
        "AI_BRAIN_API_KEY": "ai-brain-production-key-0123456789-ABCDEF",
        "TELEGRAM_API_KEY": "telegram-production-key-0123456789-ABCDEF",
        "TELEGRAM_TENANT_SIGNING_KEY": "tenant-production-key-0123456789-ABCDEF",
        "LOGIN_CLIENT_SIGNING_KEY": "login-client-production-key-0123456789-ABCDEF",
        "CORS_ORIGINS": "https://analytics.example.org",
    }
    production_settings[second_field] = production_settings[first_field]

    with pytest.raises(
        ValueError,
        match=rf"{first_field}.*{second_field}.*must be distinct",
    ):
        config.Settings(_env_file=None, **production_settings)


def test_auth_models_bound_direct_input_and_require_positive_claim_ids() -> None:
    models = _load(ROOT / "auth-backend" / "models.py", "security_bounded_models")

    assert models.LoginRequest(username="operator", password="secret").username == (
        "operator"
    )
    for payload in (
        {"username": "", "password": "secret"},
        {"username": "operator\r\nforged", "password": "secret"},
        {"username": "x" * 129, "password": "secret"},
        {"username": "operator", "password": ""},
        {"username": "operator", "password": "x" * 1025},
    ):
        with pytest.raises(ValidationError):
            models.LoginRequest(**payload)

    for model, id_field in (
        (models.User, "id"),
        (models.UserResponse, "id"),
        (models.TokenData, "user_id"),
    ):
        payload = {id_field: 0, "username": "operator", "saas_user_id": 1}
        with pytest.raises(ValidationError):
            model(**payload)

    with pytest.raises(ValidationError):
        models.TokenData(user_id=1, username="operator", saas_user_id=0)


def test_passwords_are_hashed_and_plaintext_is_not_accepted_in_production(
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    config = _load(ROOT / "auth-backend" / "config.py", "config")
    models = _load(ROOT / "auth-backend" / "models.py", "models")
    monkeypatch.setitem(sys.modules, "config", config)
    monkeypatch.setitem(sys.modules, "models", models)

    jwt_module = types.ModuleType("jwt")

    class InvalidTokenError(Exception):
        pass

    jwt_module.InvalidTokenError = InvalidTokenError
    jwt_module.encode = lambda *args, **kwargs: "token"
    jwt_module.decode = lambda *args, **kwargs: {}
    monkeypatch.setitem(sys.modules, "jwt", jwt_module)
    auth = _load(ROOT / "auth-backend" / "auth.py", "security_auth")

    password_hash = auth.hash_password(
        "correct horse battery staple", iterations=310_000
    )
    assert auth.verify_password("correct horse battery staple", password_hash)
    assert not auth.verify_password("wrong", password_hash)

    monkeypatch.setattr(auth.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(auth.settings, "DEFAULT_USERNAME", "operator")
    monkeypatch.setattr(auth.settings, "DEFAULT_PASSWORD", "plaintext-is-not-allowed")
    monkeypatch.setattr(auth.settings, "DEFAULT_PASSWORD_HASH", "")
    assert auth.authenticate_user("operator", "plaintext-is-not-allowed") is None

    monkeypatch.setattr(auth.settings, "ENVIRONMENT", "staging")
    assert auth.authenticate_user("operator", "plaintext-is-not-allowed") is None

    monkeypatch.setattr(auth.settings, "ENVIRONMENT", "development")
    assert auth.authenticate_user("operator", "plaintext-is-not-allowed") is not None


def test_ai_proxy_overwrites_all_caller_controlled_tenant_values(monkeypatch) -> None:
    gateway = _load_gateway(monkeypatch)
    captured = []

    class FakeResponse:
        headers = {"content-type": "application/json"}
        status_code = 200
        content = b'{"ok": true}'

        @staticmethod
        def json():
            return {"ok": True}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, **kwargs):
            captured.append(kwargs)
            return FakeResponse()

    class FakeRequest:
        def __init__(self, method: str, body: bytes = b""):
            self.method = method
            self.query_params = {"saas_user_id": "999"}
            self.headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "x-request-id": " request-123 ",
                "traceparent": (
                    "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
                ),
                "authorization": "Bearer browser-jwt-must-not-be-forwarded",
                "cookie": "session=must-not-be-forwarded",
                "forwarded": "for=198.51.100.7;host=attacker.example",
                "x-forwarded-for": "198.51.100.7",
                "x-forwarded-host": "attacker.example",
                "x-forwarded-proto": "https",
                "x-real-ip": "198.51.100.7",
                "x-user-id": "999",
                "x-saas-user-id": "999",
                "x-tenant-id": "999",
                "x-unknown-metadata": "must-not-pass",
                "x-api-key": "attacker-service-key",
            }
            self._body = body

        async def body(self):
            return self._body

    token = types.SimpleNamespace(saas_user_id=7)
    monkeypatch.setattr(gateway, "AsyncClient", FakeAsyncClient)

    asyncio.run(
        gateway.proxy_ai_brain(
            "brain/answer",
            FakeRequest(
                "POST", json.dumps({"saas_user_id": 999, "message_text": "hi"}).encode()
            ),
            token,
        )
    )
    asyncio.run(
        gateway.proxy_ai_brain("chat/history/session-1", FakeRequest("GET"), token)
    )
    asyncio.run(gateway.proxy_ai_brain("chat/sessions", FakeRequest("GET"), token))

    assert len(captured) == 3
    assert all(call["params"]["saas_user_id"] == "7" for call in captured)
    assert json.loads(captured[0]["content"])["saas_user_id"] == 7
    expected_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Request-ID": "request-123",
        "traceparent": ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
        "X-API-Key": "a" * 48,
    }
    assert all(call["headers"] == expected_headers for call in captured)


def test_proxy_header_allowlist_rejects_malformed_correlation_metadata(
    monkeypatch,
) -> None:
    gateway = _load_gateway(monkeypatch)
    request = types.SimpleNamespace(
        headers={
            "accept": "a" * 513,
            "content-type": "application/json\r\nX-Forged: yes",
            "x-request-id": "../unsafe request id",
            "traceparent": "00-" + "0" * 32 + "-" + "0" * 16 + "-01",
            "tracestate": "vendor=private-identity",
            "baggage": "user.id=999",
            "x-forwarded-client-cert": "spoofed-certificate",
        }
    )
    assert gateway._filtered_proxy_headers(request) == {}


def test_ai_proxy_rejects_dot_segment_tenant_bypass(monkeypatch) -> None:
    gateway = _load_gateway(monkeypatch)

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, **kwargs):
            pytest.fail("Rejected proxy paths must never reach the upstream service")

    class FakeRequest:
        method = "GET"
        query_params = {"saas_user_id": "999"}
        headers = {}

        async def body(self):
            return b""

    monkeypatch.setattr(gateway, "AsyncClient", UnexpectedClient)
    token = types.SimpleNamespace(saas_user_id=7)

    for path in (
        "foo/../chat/sessions",
        "foo/%2e%2e/chat/sessions",
        "foo/%252e%252e/chat/sessions",
    ):
        with pytest.raises(HTTPException) as error:
            asyncio.run(gateway.proxy_ai_brain(path, FakeRequest(), token))
        assert error.value.status_code == 404


def test_ai_image_proxy_rejects_another_tenants_dashboard(monkeypatch) -> None:
    gateway = _load_gateway(monkeypatch)

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, **kwargs):
            pytest.fail("A cross-tenant image must never reach the upstream service")

    class FakeRequest:
        method = "GET"
        query_params = {}
        headers = {}

        async def body(self):
            return b""

    monkeypatch.setattr(gateway, "AsyncClient", UnexpectedClient)
    token = types.SimpleNamespace(saas_user_id=7)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            gateway.proxy_ai_brain(
                "brain/image/dashboard-8-secret.png",
                FakeRequest(),
                token,
            )
        )
    assert error.value.status_code == 404


def test_dashboard_aggregate_declares_allowlisted_data_source(monkeypatch) -> None:
    gateway = _load_gateway(monkeypatch)
    calls = []

    def capture_metrics(**kwargs):
        calls.append(kwargs)
        return {"views": 10}

    monkeypatch.setattr(gateway, "get_dashboard_metrics", capture_metrics)
    monkeypatch.setattr(gateway.settings, "DASHBOARD_DATA_SOURCE", "synthetic-demo")
    monkeypatch.setattr(gateway.settings, "DEFAULT_SAAS_USER_ID", 7)

    payload = asyncio.run(
        gateway.get_dashboard_data(types.SimpleNamespace(saas_user_id=7))
    )

    assert payload["data_source"] == "synthetic-demo"
    assert calls == [
        {
            "saas_user_id": 7,
            "data_source": "synthetic-demo",
            "default_saas_user_id": 7,
        }
    ]

    with pytest.raises(HTTPException) as error:
        asyncio.run(gateway.get_dashboard_data(types.SimpleNamespace(saas_user_id=8)))
    assert error.value.status_code == 404


def test_live_dashboard_files_are_isolated_by_verified_tenant(
    tmp_path,
    monkeypatch,
) -> None:
    loader = _load(ROOT / "auth-backend" / "data_loader.py", "tenant_data_loader")
    monkeypatch.setattr(loader, "PARSER_LOGS_DIR", str(tmp_path))

    for tenant_id, title, subscribers in (
        (7, "Tenant Seven", 700),
        (8, "Tenant Eight", 800),
    ):
        tenant_dir = tmp_path / str(tenant_id)
        tenant_dir.mkdir()
        (tenant_dir / "channels_analysis_current.csv").write_text(
            "subscribers\tengagement_rate_percent\tavg_reach_72h\t"
            "posting_posts_per_day\ttitle\tusername\n"
            f"{subscribers}\t10\t100\t2\t{title}\ttenant_{tenant_id}\n",
            encoding="utf-8",
        )
        (tenant_dir / "top_posts_current.json").write_text(
            json.dumps({"posts": [{"views": tenant_id * 100}]}),
            encoding="utf-8",
        )

    common = {"data_source": "live", "default_saas_user_id": 1}
    tenant_seven = loader.get_dashboard_metrics(7, **common)
    tenant_eight = loader.get_dashboard_metrics(8, **common)

    assert tenant_seven["subscribers"]["value"] == 700
    assert tenant_eight["subscribers"]["value"] == 800
    assert loader.get_profile(7, **common)["username"] == "Tenant Seven"
    assert loader.get_profile(8, **common)["username"] == "Tenant Eight"

    with pytest.raises(PermissionError, match="unavailable"):
        loader.get_dashboard_metrics(
            8,
            data_source="synthetic-demo",
            default_saas_user_id=7,
        )


def test_login_endpoint_returns_retry_after_and_preserves_client_budget(
    monkeypatch,
) -> None:
    gateway = _load_gateway(monkeypatch)
    limiter = gateway.LoginRateLimiter(
        max_attempts=2,
        window_seconds=30,
        block_seconds=60,
        max_entries=30,
    )
    monkeypatch.setattr(gateway, "login_rate_limiter", limiter)
    request = types.SimpleNamespace(client=types.SimpleNamespace(host="203.0.113.7"))
    credentials = gateway.LoginRequest(username="operator", password="secret")
    outcomes = iter(
        (
            HTTPException(status_code=401, detail="invalid"),
            {"access_token": "valid"},
        )
    )

    def authenticate(_credentials):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(gateway, "login_user", authenticate)

    with pytest.raises(HTTPException) as first_error:
        asyncio.run(gateway.login(credentials, request))
    assert first_error.value.status_code == 401

    assert asyncio.run(gateway.login(credentials, request)) == {"access_token": "valid"}
    assert limiter.entry_count == 1

    def reject(_credentials):
        raise HTTPException(status_code=401, detail="invalid")

    monkeypatch.setattr(gateway, "login_user", reject)
    with pytest.raises(HTTPException) as login_error:
        asyncio.run(gateway.login(credentials, request))
    assert login_error.value.status_code == 401

    with pytest.raises(HTTPException) as blocked_error:
        asyncio.run(gateway.login(credentials, request))
    assert blocked_error.value.status_code == 429
    assert blocked_error.value.headers == {"Retry-After": "60"}


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_hardened_environment_login_requires_fresh_signed_bff_claim(
    monkeypatch,
    caplog,
    environment,
) -> None:
    gateway = _load_gateway(monkeypatch)
    claims = _load(
        ROOT / "auth-backend" / "login_client_claims.py",
        "security_endpoint_login_client_claims",
    )
    signing_key = "login-client-production-key-0123456789-ABCDEF"
    client_id = "C" * 43
    username = "operator"
    timestamp = int(time.time())
    signature = claims.build_login_client_signature(
        signing_key=signing_key,
        timestamp=timestamp,
        client_id=client_id,
        username=username,
    )
    headers = {
        claims.VERSION_HEADER: claims.CLAIM_VERSION,
        claims.TIMESTAMP_HEADER: str(timestamp),
        claims.CLIENT_ID_HEADER: client_id,
        claims.SIGNATURE_HEADER: signature,
    }
    credentials = gateway.LoginRequest(username=username, password="secret")
    monkeypatch.setattr(gateway.settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(gateway.settings, "LOGIN_CLIENT_SIGNING_KEY", signing_key)
    monkeypatch.setattr(
        gateway,
        "login_rate_limiter",
        gateway.LoginRateLimiter(
            max_attempts=2,
            window_seconds=30,
            block_seconds=60,
            max_entries=20,
        ),
    )
    monkeypatch.setattr(
        gateway,
        "login_user",
        lambda _credentials: {"access_token": "valid"},
    )

    valid_request = types.SimpleNamespace(
        headers=headers,
        client=types.SimpleNamespace(host="auth-bff"),
    )
    assert asyncio.run(gateway.login(credentials, valid_request)) == {
        "access_token": "valid"
    }

    for invalid_headers in (
        {},
        {**headers, claims.SIGNATURE_HEADER: "0" * 64},
        {
            **headers,
            claims.TIMESTAMP_HEADER: str(timestamp - 31),
            claims.SIGNATURE_HEADER: claims.build_login_client_signature(
                signing_key=signing_key,
                timestamp=timestamp - 31,
                client_id=client_id,
                username=username,
            ),
        },
    ):
        request = types.SimpleNamespace(
            headers=invalid_headers,
            client=types.SimpleNamespace(host="auth-bff"),
        )
        with pytest.raises(HTTPException) as error:
            asyncio.run(gateway.login(credentials, request))
        assert error.value.status_code == 503
        assert error.value.detail == "Authentication is temporarily unavailable"

    assert client_id not in caplog.text


def test_telegram_proxy_replaces_spoofed_tenant_claims_and_binds_signature(
    monkeypatch,
) -> None:
    gateway = _load_gateway(monkeypatch)
    claims = _load(
        ROOT / "auth-backend" / "tenant_claims.py",
        "security_gateway_tenant_claims",
    )
    captured = []

    class FakeResponse:
        headers = {"content-type": "application/json"}
        status_code = 200
        content = b'{"ok": true}'

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, **kwargs):
            captured.append(kwargs)
            return FakeResponse()

    class FakeRequest:
        def __init__(self, method: str):
            self.method = method
            self.query_params = {}
            self.headers = {
                "X-Tenant-ID": "999",
                "X-Tenant-Signature": "attacker",
                "X-SaaS-User-ID": "999",
            }

        async def body(self):
            return b""

    monkeypatch.setattr(gateway, "AsyncClient", FakeAsyncClient)
    key = gateway.settings.TELEGRAM_TENANT_SIGNING_KEY
    asyncio.run(
        gateway.proxy_chatbot(
            "api/chats",
            FakeRequest("GET"),
            types.SimpleNamespace(saas_user_id=7),
        )
    )
    asyncio.run(
        gateway.proxy_chatbot(
            "api/chats/chat-1/messages",
            FakeRequest("GET"),
            types.SimpleNamespace(saas_user_id=8),
        )
    )
    asyncio.run(
        gateway.proxy_chatbot(
            "api/channel-search",
            FakeRequest("POST"),
            types.SimpleNamespace(saas_user_id=7),
        )
    )

    first_headers = captured[0]["headers"]
    second_headers = captured[1]["headers"]
    assert first_headers["X-Tenant-ID"] == "7"
    assert second_headers["X-Tenant-ID"] == "8"
    assert "X-SaaS-User-ID" not in first_headers
    assert first_headers["X-Tenant-Signature"] != second_headers["X-Tenant-Signature"]
    assert first_headers["X-Tenant-Signature"] == claims.sign_tenant_claim(
        key,
        7,
        int(first_headers["X-Tenant-Timestamp"]),
        "GET",
        "api/chats",
        first_headers["X-Tenant-Body-SHA256"],
    )
    assert captured[2]["headers"] == {"X-API-Key": "t" * 48}


def test_telegram_message_proxy_requires_body_only_json_contract(monkeypatch) -> None:
    gateway = _load_gateway(monkeypatch)
    captured = []

    class FakeResponse:
        headers = {"content-type": "application/json"}
        status_code = 405
        content = b'{"detail": "read-only"}'

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, **kwargs):
            captured.append(kwargs)
            return FakeResponse()

    class FakeRequest:
        method = "POST"

        def __init__(self, body: bytes, query_params=None, content_type=None):
            self.query_params = query_params or {}
            self.headers = {
                "content-type": content_type or "application/json; charset=utf-8"
            }
            self._body = body

        async def body(self):
            return self._body

    monkeypatch.setattr(gateway, "AsyncClient", FakeAsyncClient)
    token = types.SimpleNamespace(saas_user_id=7)
    sensitive_text = "token=private-value&next=/billing?admin=true"

    response = asyncio.run(
        gateway.proxy_chatbot(
            "api/chats/chat-1/messages",
            FakeRequest(json.dumps({"text": sensitive_text}).encode()),
            token,
        )
    )

    assert response.status_code == 405
    assert len(captured) == 1
    assert captured[0]["url"].endswith("/api/chats/chat-1/messages")
    assert sensitive_text not in captured[0]["url"]
    assert captured[0]["params"] == {}
    assert json.loads(captured[0]["content"]) == {"text": sensitive_text}
    assert (
        captured[0]["headers"]["X-Tenant-Body-SHA256"]
        == hashlib.sha256(captured[0]["content"]).hexdigest()
    )

    with pytest.raises(HTTPException) as query_error:
        asyncio.run(
            gateway.proxy_chatbot(
                "api/chats/chat-1/messages",
                FakeRequest(b"{}", {"text": sensitive_text}),
                token,
            )
        )
    assert query_error.value.status_code == 400
    assert len(captured) == 1

    with pytest.raises(HTTPException) as media_type_error:
        asyncio.run(
            gateway.proxy_chatbot(
                "api/chats/chat-1/messages",
                FakeRequest(b'{"text":"hello"}', content_type="text/plain"),
                token,
            )
        )
    assert media_type_error.value.status_code == 415
    assert len(captured) == 1


def test_proxies_preserve_upstream_http_status(monkeypatch) -> None:
    gateway = _load_gateway(monkeypatch)

    class MissingResponse:
        headers = {"content-type": "application/json"}
        status_code = 404
        content = b'{"detail":"not found"}'

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, **kwargs):
            return MissingResponse()

    class FakeRequest:
        method = "GET"
        query_params = {}
        headers = {}

        async def body(self):
            return b""

    monkeypatch.setattr(gateway, "AsyncClient", FakeAsyncClient)
    token = types.SimpleNamespace(saas_user_id=7)

    ai_response = asyncio.run(
        gateway.proxy_ai_brain("chat/sessions", FakeRequest(), token)
    )
    telegram_response = asyncio.run(
        gateway.proxy_chatbot("api/chats", FakeRequest(), token)
    )
    assert ai_response.status_code == 404
    assert telegram_response.status_code == 404


def test_proxy_errors_are_generic_to_callers(monkeypatch, caplog) -> None:
    gateway = _load_gateway(monkeypatch)

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, **kwargs):
            raise RuntimeError("private-host.internal:5432 secret diagnostics")

    class FakeRequest:
        method = "GET"
        query_params = {}
        headers = {}

        async def body(self):
            return b""

    monkeypatch.setattr(gateway, "AsyncClient", FailingAsyncClient)
    token = types.SimpleNamespace(saas_user_id=7)

    with pytest.raises(HTTPException) as ai_error:
        asyncio.run(gateway.proxy_ai_brain("chat/sessions", FakeRequest(), token))
    assert ai_error.value.status_code == 502
    assert "private-host" not in str(ai_error.value.detail)

    with pytest.raises(HTTPException) as telegram_error:
        asyncio.run(gateway.proxy_chatbot("api/chats", FakeRequest(), token))
    assert telegram_error.value.status_code == 502
    assert "private-host" not in str(telegram_error.value.detail)
    assert "private-host" not in caplog.text
