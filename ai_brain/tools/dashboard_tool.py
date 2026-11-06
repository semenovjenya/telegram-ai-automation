"""LangChain tool for generating a tenant-scoped channel dashboard image."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from ..config import settings
from ..utils.dashboard_generator import generate_channel_dashboard_image

logger = logging.getLogger(__name__)
CHANNEL_USERNAME = re.compile(r"^[A-Za-z0-9_]{5,64}$")


async def get_channel_info_from_api(
    channel_username: str,
    api_url: str | None = None,
) -> dict[str, Any] | None:
    normalized = channel_username.strip().lstrip("@")
    if not CHANNEL_USERNAME.fullmatch(normalized):
        return None

    headers: dict[str, str] = {}
    if settings.TELEGRAM_API_KEY:
        headers["X-API-Key"] = settings.TELEGRAM_API_KEY
    url = f"{(api_url or settings.TELEGRAM_API_URL).rstrip('/')}/api/channels/{quote(normalized)}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        logger.exception("Channel metadata lookup failed channel=%s", normalized)
        return None

    channel = payload.get("channel") if isinstance(payload, dict) else None
    if not isinstance(channel, dict):
        return None

    # The public adapter and production sources use slightly different names;
    # normalize them once at the integration boundary.
    return {
        **channel,
        "channel_username": channel.get("channel_username")
        or channel.get("username")
        or normalized,
        "channel_title": channel.get("channel_title")
        or channel.get("title")
        or normalized,
        "engagement_rate": channel.get("engagement_rate")
        or channel.get("engagement_rate_percent")
        or 0,
    }


@tool
async def generate_channel_dashboard(
    channel_username: str,
    saas_user_id: int,
) -> str:
    """Generate a PNG dashboard for a channel from the current tenant context."""

    normalized = channel_username.strip().lstrip("@")
    if saas_user_id <= 0 or not CHANNEL_USERNAME.fullmatch(normalized):
        return "Некорректный tenant или username Telegram-канала."

    channel_data = await get_channel_info_from_api(normalized)
    if not channel_data:
        return "Данные канала для дашборда сейчас недоступны."

    artifacts_dir = settings.ARTIFACTS_DIR.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path = artifacts_dir / (
        f"dashboard-{saas_user_id}-{normalized}-{uuid.uuid4().hex[:12]}.png"
    )
    try:
        dashboard_path = await asyncio.to_thread(
            generate_channel_dashboard_image,
            channel_data,
            saas_user_id,
            str(output_path),
        )
    except Exception:
        logger.exception(
            "Dashboard generation failed tenant=%s channel=%s",
            saas_user_id,
            normalized,
        )
        return "Не удалось сгенерировать дашборд."

    resolved = output_path.resolve()
    if Path(dashboard_path).resolve() != resolved or not resolved.is_file():
        logger.error("Dashboard generator returned an unexpected output path")
        return "Не удалось проверить сгенерированный дашборд."
    return f"image_path:{resolved}"
