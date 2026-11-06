"""Synthetic process configuration for standalone examples; never live Telegram."""

import os


def configure_demo() -> None:
    os.environ.update(
        {
            "ENVIRONMENT": "test",
            "API_KEY": "portfolio-local-service-key-only",
            "POSTGRES_PASSWORD": "portfolio-local-password-only",
            "LLM_PROVIDER": "mock",
            "CHECKPOINT_BACKEND": "memory",
        }
    )
