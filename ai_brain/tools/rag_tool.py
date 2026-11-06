"""Convenience helpers for retrieval-augmented agent context."""

from __future__ import annotations

import logging
from typing import Any

from ..clients import channel_search_client

logger = logging.getLogger(__name__)


async def retrieve_rag_context(
    query: str,
    channel_username: str | None,
    top_k: int = 3,
) -> str | None:
    if not channel_search_client.is_configured or not channel_username:
        return None

    normalized_channel = channel_username.strip().lstrip("@")
    results = await channel_search_client.search(
        query=query.strip(),
        channel=normalized_channel,
        top_k=top_k,
    )
    if not results:
        logger.info("No RAG results channel=%s", normalized_channel)
        return None
    return channel_search_client.format_results(results)


async def retrieve_rag_context_from_state(
    message: str,
    context: dict[str, Any],
) -> str | None:
    return await retrieve_rag_context(
        query=message,
        channel_username=context.get("channel_username"),
    )
