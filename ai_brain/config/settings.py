"""Typed, environment-driven configuration for the AI-BRAIN service."""

from __future__ import annotations

import re
from ipaddress import ip_address
from pathlib import Path
from typing import Literal, Self
from urllib.parse import quote_plus, urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_STRICT_ENVIRONMENTS = frozenset({"staging", "production"})
_MIN_LIVE_SECRET_LENGTH = 32
_MIN_LIVE_SECRET_UNIQUE_CHARACTERS = 8
_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "default",
    "demo",
    "dummy",
    "example",
    "insecure",
    "local-",
    "not-configured",
    "password",
    "placeholder",
    "test-api-key",
    "test_api_key",
    "your-secret",
)
_FORBIDDEN_TARGET_TOKENS = frozenset({"demo", "example", "localhost", "mock"})
_FORBIDDEN_TARGET_SUFFIXES = (
    ".example",
    ".example.com",
    ".example.net",
    ".example.org",
    ".invalid",
    ".localhost",
    ".test",
)
_INTERNAL_HTTP_SUFFIXES = (".internal", ".local", ".svc", ".svc.cluster.local")
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")


def _validate_live_secret(name: str, value: str) -> None:
    """Reject credentials that are unsafe to deploy outside local demos."""

    normalized = value.strip().lower()
    if any(marker in normalized for marker in _PLACEHOLDER_MARKERS):
        raise ValueError(f"{name} contains a placeholder and is forbidden")
    if value != value.strip() or len(value) < _MIN_LIVE_SECRET_LENGTH:
        raise ValueError(
            f"{name} must contain at least {_MIN_LIVE_SECRET_LENGTH} characters"
        )
    if len(set(value)) < _MIN_LIVE_SECRET_UNIQUE_CHARACTERS:
        raise ValueError(f"{name} has insufficient character diversity")


def _validate_service_url(name: str, value: str) -> None:
    """Reject malformed, demo, and unsafe integration targets."""

    if (
        value != value.strip()
        or any(character.isspace() for character in value)
        or "\\" in value
        or _INVALID_PERCENT_ESCAPE.search(value)
    ):
        raise ValueError(f"{name} must be a well-formed HTTP(S) URL")

    try:
        parsed = urlsplit(value)
        # Accessing port forces urllib to reject malformed/out-of-range ports.
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"{name} must be a well-formed HTTP(S) URL") from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.netloc.endswith(":")
    ):
        raise ValueError(
            f"{name} must be an absolute HTTP(S) URL without credentials or fragments"
        )

    hostname = parsed.hostname.rstrip(".").lower()
    try:
        parsed_ip_address = ip_address(hostname)
    except ValueError:
        parsed_ip_address = None
        labels = hostname.split(".")
        if not all(_DNS_LABEL.fullmatch(label) for label in labels):
            raise ValueError(f"{name} contains an invalid hostname") from None

    hostname_tokens = re.split(r"[.-]", hostname)
    if any(token in _FORBIDDEN_TARGET_TOKENS for token in hostname_tokens):
        raise ValueError(f"{name} points to a mock, demo, or reserved target")
    if any(hostname.endswith(suffix) for suffix in _FORBIDDEN_TARGET_SUFFIXES):
        raise ValueError(f"{name} points to a mock, demo, or reserved target")
    mapped_ipv4 = getattr(parsed_ip_address, "ipv4_mapped", None)
    if parsed_ip_address is not None and (
        parsed_ip_address.is_loopback
        or parsed_ip_address.is_unspecified
        or (mapped_ipv4 is not None and mapped_ipv4.is_loopback)
    ):
        raise ValueError(f"{name} points to a loopback or unspecified address")

    if parsed.scheme == "http":
        is_internal_hostname = parsed_ip_address is None and (
            "." not in hostname
            or any(hostname.endswith(suffix) for suffix in _INTERNAL_HTTP_SUFFIXES)
        )
        if not is_internal_hostname:
            raise ValueError(
                f"{name} must use HTTPS unless it targets a reviewed internal service hostname"
            )


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables.

    Production deliberately fails closed when placeholder credentials are used.
    Local development uses the same validation by setting real values in ``.env``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: Literal["development", "test", "staging", "production"] = "development"

    # HTTP API
    API_KEY: str = Field(..., min_length=16, repr=False)
    HOST: str = "0.0.0.0"
    PORT: int = Field(default=8000, ge=1, le=65535)

    # PostgreSQL for chat history and LangGraph checkpoints
    POSTGRES_HOST: str = "postgres-vectors"
    POSTGRES_PORT: int = Field(default=5432, ge=1, le=65535)
    POSTGRES_DB: str = "chat_history"
    POSTGRES_USER: str = "chatbot"
    POSTGRES_PASSWORD: str = Field(..., min_length=8, repr=False)
    DB_POOL_MIN_SIZE: int = Field(default=1, ge=1, le=20)
    DB_POOL_MAX_SIZE: int = Field(default=10, ge=1, le=100)
    MODEL_HISTORY_LIMIT: int = Field(default=50, ge=1, le=500)
    API_HISTORY_MAX_LIMIT: int = Field(default=1000, ge=1, le=5000)

    # OpenAI
    LLM_PROVIDER: Literal["openai", "mock"] = "openai"
    OPENAI_API_KEY: str | None = Field(default=None, min_length=16, repr=False)
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=2.0)
    MAX_OUTPUT_TOKENS: int = Field(default=1200, ge=64, le=8192)

    # External services
    CHANNEL_SEARCH_URL: str | None = None
    CHANNEL_SEARCH_API_KEY: str | None = Field(default=None, repr=False)
    TELEGRAM_API_URL: str = "http://telegram-mock:8010"
    TELEGRAM_API_KEY: str | None = Field(default=None, repr=False)
    ARTIFACTS_DIR: Path = Path("/tmp/ai-brain-artifacts")

    # LangGraph durability
    CHECKPOINT_BACKEND: Literal["memory", "postgres"] = "postgres"
    ALLOW_MEMORY_CHECKPOINT_FALLBACK: bool = False

    # Observability
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def validate_runtime_configuration(self) -> Self:
        if self.DB_POOL_MIN_SIZE > self.DB_POOL_MAX_SIZE:
            raise ValueError("DB_POOL_MIN_SIZE cannot exceed DB_POOL_MAX_SIZE")

        if self.MODEL_HISTORY_LIMIT > self.API_HISTORY_MAX_LIMIT:
            raise ValueError("MODEL_HISTORY_LIMIT cannot exceed API_HISTORY_MAX_LIMIT")

        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

        if self.ENVIRONMENT in _STRICT_ENVIRONMENTS:
            if self.LLM_PROVIDER != "openai":
                raise ValueError("production and staging require LLM_PROVIDER=openai")

            required_integrations = {
                "CHANNEL_SEARCH_URL": self.CHANNEL_SEARCH_URL,
                "CHANNEL_SEARCH_API_KEY": self.CHANNEL_SEARCH_API_KEY,
                "TELEGRAM_API_URL": self.TELEGRAM_API_URL,
                "TELEGRAM_API_KEY": self.TELEGRAM_API_KEY,
            }
            missing = [
                name
                for name, value in required_integrations.items()
                if value is None or not value.strip()
            ]
            if missing:
                raise ValueError(
                    "staging and production require explicit live integrations: "
                    + ", ".join(sorted(missing))
                )

            sensitive_values = {
                "API_KEY": self.API_KEY,
                "POSTGRES_PASSWORD": self.POSTGRES_PASSWORD,
                "OPENAI_API_KEY": self.OPENAI_API_KEY or "",
                "CHANNEL_SEARCH_API_KEY": self.CHANNEL_SEARCH_API_KEY or "",
                "TELEGRAM_API_KEY": self.TELEGRAM_API_KEY or "",
            }
            for name, value in sensitive_values.items():
                _validate_live_secret(name, value)

            by_value: dict[str, list[str]] = {}
            for name, value in sensitive_values.items():
                by_value.setdefault(value, []).append(name)
            reused_names = [names for names in by_value.values() if len(names) > 1]
            if reused_names:
                names = ", ".join(sorted(reused_names[0]))
                raise ValueError(
                    f"live credentials must be distinct; reused by {names}"
                )

            _validate_service_url("CHANNEL_SEARCH_URL", self.CHANNEL_SEARCH_URL or "")
            _validate_service_url("TELEGRAM_API_URL", self.TELEGRAM_API_URL)
        return self

    @property
    def postgres_connection_string(self) -> str:
        """Return a URL-safe PostgreSQL connection string."""

        user = quote_plus(self.POSTGRES_USER)
        password = quote_plus(self.POSTGRES_PASSWORD)
        database = quote_plus(self.POSTGRES_DB)
        return (
            f"postgresql://{user}:{password}@{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/{database}"
        )


settings = Settings()
