from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_brain.config.settings import Settings

BASE_SETTINGS = {
    "API_KEY": "a-secure-internal-api-key-value",
    "OPENAI_API_KEY": "a-secure-openai-key-value",
    "POSTGRES_PASSWORD": "a-secure-database-password",
}

VALID_LIVE_SETTINGS = {
    "ENVIRONMENT": "production",
    "LLM_PROVIDER": "openai",
    "API_KEY": "u7Rk9Qm2Vx5Nz8Lp4Tc6Hy3Bw1Fd0SaE",
    "POSTGRES_PASSWORD": "Db9!qL2@vN5#xR8$kT1%hY4&wP7*zC0U",
    "OPENAI_API_KEY": "provider-token-live-aB3dE5gH7jK9mN2pQ4sT",
    "CHANNEL_SEARCH_URL": "http://channel-search.default.svc.cluster.local:8080/search",
    "CHANNEL_SEARCH_API_KEY": "Cs4vG8nK2qM6tR9xB3dF7hJ1pL5wY0zA",
    "TELEGRAM_API_URL": "https://telegram-api.company.tld",
    "TELEGRAM_API_KEY": "Tg8mQ2wE6rY0uI4oP9aS3dF7gH1jK5lZ",
}


def live_settings(**overrides: object) -> dict[str, object]:
    return {**VALID_LIVE_SETTINGS, **overrides}


def test_production_rejects_placeholder_credentials() -> None:
    with pytest.raises(ValueError, match="API_KEY.*placeholder"):
        Settings(
            _env_file=None,
            **live_settings(API_KEY="change-me-this-is-not-secure-at-all"),
        )


def test_production_rejects_compose_openai_placeholder() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY.*placeholder"):
        Settings(
            _env_file=None,
            **live_settings(OPENAI_API_KEY="local-openai-key-not-configured"),
        )


@pytest.mark.parametrize(
    ("name", "weak_value"),
    [
        ("API_KEY", "aB3dE5gH7jK9mN2p"),
        ("POSTGRES_PASSWORD", "bC4eF6hJ8kL0mN2q"),
        ("OPENAI_API_KEY", "provider-token-cD5fG7jK"),
        ("CHANNEL_SEARCH_API_KEY", "dE6gH8kL0nQ2sU4w"),
        ("TELEGRAM_API_KEY", "eF7hJ9mP1rT3vX5z"),
    ],
)
def test_production_rejects_live_secrets_shorter_than_32_characters(
    name: str,
    weak_value: str,
) -> None:
    with pytest.raises(ValueError, match=rf"{name}.*at least 32"):
        Settings(_env_file=None, **live_settings(**{name: weak_value}))


def test_production_rejects_low_diversity_secret() -> None:
    with pytest.raises(ValueError, match="API_KEY.*diversity"):
        Settings(_env_file=None, **live_settings(API_KEY="a" * 32))


def test_production_requires_all_live_integrations() -> None:
    with pytest.raises(ValueError, match="CHANNEL_SEARCH_API_KEY"):
        Settings(_env_file=None, **live_settings(CHANNEL_SEARCH_API_KEY=None))


def test_staging_uses_the_same_strict_validation_as_production() -> None:
    with pytest.raises(ValueError, match="TELEGRAM_API_URL.*mock"):
        Settings(
            _env_file=None,
            **live_settings(
                ENVIRONMENT="staging",
                TELEGRAM_API_URL="http://telegram-mock:8010",
            ),
        )


@pytest.mark.parametrize(
    ("name", "url", "message"),
    [
        ("CHANNEL_SEARCH_URL", "telegram-mock:8010/search", "absolute HTTP"),
        ("CHANNEL_SEARCH_URL", "https://channel.example.com/search", "mock, demo"),
        ("CHANNEL_SEARCH_URL", "https://demo.company.tld/search", "mock, demo"),
        ("CHANNEL_SEARCH_URL", "https://api-demo.company.tld/search", "mock, demo"),
        ("CHANNEL_SEARCH_URL", "http://public.company.tld/search", "HTTPS"),
        ("TELEGRAM_API_URL", "http://localhost:8010", "mock, demo"),
        ("TELEGRAM_API_URL", "https://localhost.localdomain:8010", "mock, demo"),
        ("TELEGRAM_API_URL", "https://127.0.0.1:8010", "loopback"),
        ("TELEGRAM_API_URL", "https://[::1]:8010", "loopback"),
        ("TELEGRAM_API_URL", "https://[::ffff:127.0.0.1]:8010", "loopback"),
        ("TELEGRAM_API_URL", "https://api.company.tld:99999", "well-formed"),
        ("TELEGRAM_API_URL", "https://api.company.tld:", "absolute HTTP"),
        ("TELEGRAM_API_URL", "https://api.company.tld/%not-hex", "well-formed"),
    ],
)
def test_production_rejects_unsafe_or_malformed_integration_urls(
    name: str,
    url: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=rf"{name}.*{message}"):
        Settings(_env_file=None, **live_settings(**{name: url}))


def test_production_rejects_reused_live_credentials() -> None:
    with pytest.raises(ValueError, match="credentials must be distinct"):
        Settings(
            _env_file=None,
            **live_settings(
                CHANNEL_SEARCH_API_KEY=VALID_LIVE_SETTINGS["TELEGRAM_API_KEY"]
            ),
        )


def test_valid_production_accepts_internal_http_and_external_https() -> None:
    config = Settings(_env_file=None, **VALID_LIVE_SETTINGS)

    assert config.ENVIRONMENT == "production"
    assert config.CHANNEL_SEARCH_URL == VALID_LIVE_SETTINGS["CHANNEL_SEARCH_URL"]
    assert config.TELEGRAM_API_URL == VALID_LIVE_SETTINGS["TELEGRAM_API_URL"]


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ENVIRONMENT"):
        Settings(
            _env_file=None,
            **live_settings(ENVIRONMENT="prod"),
        )


def test_database_credentials_are_url_encoded() -> None:
    values = {
        **BASE_SETTINGS,
        "POSTGRES_USER": "user@example.com",
        "POSTGRES_PASSWORD": "pass/word with spaces",
    }
    config = Settings(
        _env_file=None,
        **values,
    )
    assert "user%40example.com" in config.postgres_connection_string
    assert "pass%2Fword+with+spaces" in config.postgres_connection_string


def test_pool_minimum_cannot_exceed_maximum() -> None:
    with pytest.raises(ValueError, match="DB_POOL_MIN_SIZE"):
        Settings(
            _env_file=None,
            **BASE_SETTINGS,
            DB_POOL_MIN_SIZE=8,
            DB_POOL_MAX_SIZE=4,
        )


def test_model_history_limit_cannot_exceed_api_storage_bound() -> None:
    with pytest.raises(ValueError, match="MODEL_HISTORY_LIMIT"):
        Settings(
            _env_file=None,
            **BASE_SETTINGS,
            MODEL_HISTORY_LIMIT=101,
            API_HISTORY_MAX_LIMIT=100,
        )


def test_max_output_tokens_has_bounded_default() -> None:
    config = Settings(_env_file=None, **BASE_SETTINGS)

    assert config.MAX_OUTPUT_TOKENS == 1200
    for invalid_value in (63, 8193):
        with pytest.raises(ValidationError, match="MAX_OUTPUT_TOKENS"):
            Settings(
                _env_file=None,
                **BASE_SETTINGS,
                MAX_OUTPUT_TOKENS=invalid_value,
            )


def test_compose_forwards_max_output_tokens() -> None:
    compose_file = Path(__file__).parents[1] / "compose" / "docker-compose.yml"

    assert "MAX_OUTPUT_TOKENS: ${MAX_OUTPUT_TOKENS:-1200}" in compose_file.read_text(
        encoding="utf-8"
    )


def test_mock_provider_does_not_require_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY")
    values = {
        key: value for key, value in BASE_SETTINGS.items() if key != "OPENAI_API_KEY"
    }
    config = Settings(
        _env_file=None,
        **values,
        ENVIRONMENT="development",
        LLM_PROVIDER="mock",
    )
    assert config.OPENAI_API_KEY is None
