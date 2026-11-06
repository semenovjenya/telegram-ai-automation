"""Shared, environment-only configuration for offline parser scripts."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PARSER_DIR = Path(__file__).resolve().parent
DEFAULT_SESSION_FILENAME = "telegram.session"


def load_parser_environment(parser_dir: Path = PARSER_DIR) -> None:
    """Load optional local env files without overriding process environment."""
    parser_dir = parser_dir.resolve()
    load_dotenv(parser_dir / ".env", override=False)
    load_dotenv(parser_dir.parent / ".env", override=False)


def resolve_session_path(
    configured_path: str | None,
    parser_dir: Path = PARSER_DIR,
) -> Path:
    """Resolve a Telegram session stored strictly inside ``parser_local``."""
    parser_dir = parser_dir.resolve()
    relative_path = Path(configured_path or DEFAULT_SESSION_FILENAME)
    if relative_path.is_absolute():
        raise RuntimeError(
            "TELEGRAM_SESSION must be a relative path inside parser_local"
        )

    session_path = (parser_dir / relative_path).resolve()
    try:
        session_path.relative_to(parser_dir)
    except ValueError as exc:
        raise RuntimeError(
            "TELEGRAM_SESSION must not escape the parser_local directory"
        ) from exc

    if not session_path.is_file():
        raise FileNotFoundError(
            f"Telegram session file not found: {session_path}. "
            "Copy a trusted session into parser_local and set TELEGRAM_SESSION "
            f"(default: {DEFAULT_SESSION_FILENAME})."
        )
    return session_path


def resolve_channels_csv_path(
    csv_path: Path,
    project_root: Path = PARSER_DIR.parent,
) -> Path:
    """Resolve a supplied CSV or its basename under repository vector_search."""
    if csv_path.exists():
        return csv_path.resolve()

    return (project_root / "vector_search" / csv_path.name).resolve()


def load_telegram_config(parser_dir: Path = PARSER_DIR) -> dict[str, object]:
    """Load Telegram credentials exclusively from environment variables."""
    load_parser_environment(parser_dir)
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    missing = [
        name
        for name, value in (
            ("TELEGRAM_API_ID", api_id),
            ("TELEGRAM_API_HASH", api_hash),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required parser environment variables: " + ", ".join(missing)
        )

    try:
        numeric_api_id = int(api_id)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("TELEGRAM_API_ID must be an integer") from exc

    return {
        "api_id": numeric_api_id,
        "api_hash": api_hash,
        "session_path": resolve_session_path(
            os.getenv("TELEGRAM_SESSION"),
            parser_dir,
        ),
    }


def load_openai_config(parser_dir: Path = PARSER_DIR) -> dict[str, str]:
    """Load the optional LLM configuration exclusively from environment."""
    load_parser_environment(parser_dir)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing required parser environment variable: OPENAI_API_KEY"
        )

    return {
        "openai_api_key": api_key,
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o"),
    }
