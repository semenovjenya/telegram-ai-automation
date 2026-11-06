"""LangChain tool for retrieval over channel analytics."""

from __future__ import annotations

import logging
import re

from langchain_core.tools import tool

from ..clients import channel_search_client

logger = logging.getLogger(__name__)
CHANNEL_USERNAME = re.compile(r"^[A-Za-z0-9_]{5,64}$")


@tool
async def search_channel_vectors(query: str, channel_username: str) -> str:
    """Search analytics and semantic context for one Telegram channel.

    Use this for audience, content, metrics, advertising fit, and similar-channel
    questions. Always pass the channel username from the current user context.
    """

    normalized_query = query.strip()
    normalized_channel = channel_username.strip().lstrip("@")
    if not normalized_query or len(normalized_query) > 2_000:
        return "Поисковый запрос пустой или слишком длинный."
    if not CHANNEL_USERNAME.fullmatch(normalized_channel):
        return "Некорректный username Telegram-канала."
    if not channel_search_client.is_configured:
        return "Сервис поиска по каналам сейчас недоступен."

    results = await channel_search_client.search(
        query=normalized_query,
        channel=normalized_channel,
        top_k=5,
    )
    if not results:
        logger.info("No channel-search results channel=%s", normalized_channel)
        return "Релевантные данные по каналу не найдены."
    return channel_search_client.format_results(results) or "Данные не найдены."
