"""Configuration module for the backend application."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_HARDENED_ENVIRONMENTS = {"staging", "production"}
_SECRET_PLACEHOLDERS = (
    "change-me",
    "changeme",
    "your-secret",
    "test-api-key",
    "example",
)


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or len(set(value)) < 8
        or any(marker in normalized for marker in _SECRET_PLACEHOLDERS)
    )


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "APP_ENV"),
    )

    @property
    def APP_ENV(self) -> str:
        """Backward-compatible view of the canonical ENVIRONMENT setting."""
        return self.ENVIRONMENT

    @property
    def runtime_environment(self) -> str:
        """Support the repository-wide ENVIRONMENT name and legacy APP_ENV."""
        return self.ENVIRONMENT.strip().lower()

    # JWT Configuration
    # Secrets intentionally have no code defaults. Authentication remains disabled
    # until operators provide them through the environment/secret manager.
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_HOURS: int = 24
    JWT_ISSUER: str = "telegram-ai-analytics-auth"
    JWT_AUDIENCE: str = "telegram-ai-analytics"

    # CORS Configuration - use string in env, convert to list
    CORS_ORIGINS: str | list[str] = (
        "http://localhost:3000,http://localhost:3001,http://localhost:5173,http://localhost:7777,http://localhost:8080,http://auth-frontend:80"
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS_ORIGINS from string (comma-separated) to list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Get CORS origins as list."""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        if isinstance(self.CORS_ORIGINS, str):
            return [
                origin.strip()
                for origin in self.CORS_ORIGINS.split(",")
                if origin.strip()
            ]
        return []

    # API Configuration
    API_V1_PREFIX: str = "/api"
    DASHBOARD_DATA_SOURCE: str = "live"

    # Bootstrap user credentials. In production only a PBKDF2 password hash is
    # accepted; plaintext is retained solely as an opt-in local-dev fallback.
    DEFAULT_USERNAME: str = ""
    DEFAULT_PASSWORD: str = ""
    DEFAULT_PASSWORD_HASH: str = ""
    DEFAULT_SAAS_USER_ID: int = 1

    # Credentials used by the authenticated gateway when proxying requests.
    AI_BRAIN_API_KEY: str = ""
    TELEGRAM_API_KEY: str = ""
    TELEGRAM_TENANT_SIGNING_KEY: str = ""
    LOGIN_CLIENT_SIGNING_KEY: str = ""

    # Per-process login limiter. Production must additionally enforce a
    # distributed limit at the edge so replicas share one abuse budget.
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    LOGIN_RATE_LIMIT_BLOCK_SECONDS: int = 900
    LOGIN_RATE_LIMIT_MAX_ENTRIES: int = 10_000
    LOGIN_CLIENT_CLAIM_MAX_AGE_SECONDS: int = 30
    LOGIN_CLIENT_CLAIM_FUTURE_SKEW_SECONDS: int = 5

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        """Pin JWT signing to one reviewed algorithm to prevent confusion attacks."""
        if value != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256")
        return value

    @field_validator("DASHBOARD_DATA_SOURCE")
    @classmethod
    def validate_dashboard_data_source(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"live", "synthetic-demo"}:
            raise ValueError("DASHBOARD_DATA_SOURCE must be live or synthetic-demo")
        return normalized

    @field_validator("JWT_ACCESS_TOKEN_EXPIRE_HOURS")
    @classmethod
    def validate_token_lifetime(cls, value: int) -> int:
        if not 1 <= value <= 24:
            raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_HOURS must be between 1 and 24")
        return value

    @field_validator("LOGIN_RATE_LIMIT_MAX_ATTEMPTS")
    @classmethod
    def validate_login_attempt_limit(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("LOGIN_RATE_LIMIT_MAX_ATTEMPTS must be between 1 and 100")
        return value

    @field_validator(
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
        "LOGIN_RATE_LIMIT_BLOCK_SECONDS",
    )
    @classmethod
    def validate_login_rate_limit_duration(cls, value: int) -> int:
        if not 1 <= value <= 86_400:
            raise ValueError("login rate-limit durations must be between 1 and 86400")
        return value

    @field_validator("LOGIN_RATE_LIMIT_MAX_ENTRIES")
    @classmethod
    def validate_login_rate_limit_capacity(cls, value: int) -> int:
        if not 2 <= value <= 1_000_000:
            raise ValueError(
                "LOGIN_RATE_LIMIT_MAX_ENTRIES must be between 2 and 1000000"
            )
        return value

    @field_validator("LOGIN_CLIENT_CLAIM_MAX_AGE_SECONDS")
    @classmethod
    def validate_login_client_claim_age(cls, value: int) -> int:
        if not 5 <= value <= 300:
            raise ValueError(
                "LOGIN_CLIENT_CLAIM_MAX_AGE_SECONDS must be between 5 and 300"
            )
        return value

    @field_validator("LOGIN_CLIENT_CLAIM_FUTURE_SKEW_SECONDS")
    @classmethod
    def validate_login_client_claim_skew(cls, value: int) -> int:
        if not 0 <= value <= 30:
            raise ValueError(
                "LOGIN_CLIENT_CLAIM_FUTURE_SKEW_SECONDS must be between 0 and 30"
            )
        return value

    @model_validator(mode="after")
    def validate_production_security(self):
        """Refuse to start production with missing, weak, or sample credentials."""
        if self.runtime_environment not in _HARDENED_ENVIRONMENTS:
            return self

        if len(self.JWT_SECRET_KEY) < 32 or _is_placeholder(self.JWT_SECRET_KEY):
            raise ValueError(
                "JWT_SECRET_KEY must be a non-placeholder secret of at least 32 characters"
            )

        if not self.DEFAULT_USERNAME.strip():
            raise ValueError("DEFAULT_USERNAME is required in production")
        if not self.DEFAULT_PASSWORD_HASH:
            raise ValueError("DEFAULT_PASSWORD_HASH is required in production")
        if self.DEFAULT_PASSWORD:
            raise ValueError("DEFAULT_PASSWORD must be empty in production")
        if self.DASHBOARD_DATA_SOURCE != "live":
            raise ValueError("DASHBOARD_DATA_SOURCE must be live in production")

        for field_name, secret in (
            ("AI_BRAIN_API_KEY", self.AI_BRAIN_API_KEY),
            ("TELEGRAM_API_KEY", self.TELEGRAM_API_KEY),
            ("TELEGRAM_TENANT_SIGNING_KEY", self.TELEGRAM_TENANT_SIGNING_KEY),
            ("LOGIN_CLIENT_SIGNING_KEY", self.LOGIN_CLIENT_SIGNING_KEY),
        ):
            if len(secret) < 32 or _is_placeholder(secret):
                raise ValueError(
                    f"{field_name} must be a non-placeholder secret of at least 32 characters"
                )

        production_secrets = (
            ("JWT_SECRET_KEY", self.JWT_SECRET_KEY),
            ("AI_BRAIN_API_KEY", self.AI_BRAIN_API_KEY),
            ("TELEGRAM_API_KEY", self.TELEGRAM_API_KEY),
            ("TELEGRAM_TENANT_SIGNING_KEY", self.TELEGRAM_TENANT_SIGNING_KEY),
            ("LOGIN_CLIENT_SIGNING_KEY", self.LOGIN_CLIENT_SIGNING_KEY),
        )
        secret_counts = {
            secret: sum(candidate == secret for _, candidate in production_secrets)
            for _, secret in production_secrets
        }
        reused_fields = [
            field_name
            for field_name, secret in production_secrets
            if secret_counts[secret] > 1
        ]
        if reused_fields:
            raise ValueError(
                f"{', '.join(reused_fields)} must be distinct production secrets"
            )

        if "*" in self.cors_origins_list:
            raise ValueError("Wildcard CORS origins are not allowed in production")
        for origin in self.cors_origins_list:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ORIGINS must contain only exact HTTPS origins in production"
                )

        return self


settings = Settings()
