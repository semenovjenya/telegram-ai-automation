"""Typed HTTP client for the channel-search boundary."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger(__name__)
MAX_FORMATTED_RESULTS_CHARS = 6_000
MAX_RESULT_TEXT_CHARS = 1_200
MAX_RESULT_SOURCE_CHARS = 200
MAX_FORMATTED_RESULTS = 5


class ChannelSearchClient:
    """Query an optional channel-search service without leaking user content."""

    @property
    def base_url(self) -> str | None:
        return settings.CHANNEL_SEARCH_URL

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def search(
        self,
        query: str,
        channel: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        if not self.base_url:
            logger.info("Channel search is not configured")
            return []
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")

        headers: dict[str, str] = {}
        if settings.CHANNEL_SEARCH_API_KEY:
            headers["X-API-Key"] = settings.CHANNEL_SEARCH_API_KEY

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json={"query": query, "channel": channel, "top_k": top_k},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            logger.warning("Channel search timed out channel=%s", channel)
            return []
        except (httpx.HTTPError, ValueError, TypeError):
            logger.exception("Channel search request failed channel=%s", channel)
            return []

        if not isinstance(payload, list):
            logger.error("Channel search returned a non-list payload")
            return []

        results = [item for item in payload if isinstance(item, dict)][:top_k]
        logger.info(
            "Channel search returned %s results channel=%s",
            len(results),
            channel,
        )
        return results

    @staticmethod
    def format_results(results: list[dict[str, Any]] | None) -> str | None:
        if not results:
            return None

        lines = ["Найденная информация из каналов:", ""]
        for index, result in enumerate(results[:MAX_FORMATTED_RESULTS], 1):
            text = str(result.get("text", "")).strip()[:MAX_RESULT_TEXT_CHARS]
            source = str(result.get("source", "unknown")).strip()[
                :MAX_RESULT_SOURCE_CHARS
            ]
            candidate = [f"{index}. {text}", f"   Источник: {source}", ""]
            if len("\n".join([*lines, *candidate])) > MAX_FORMATTED_RESULTS_CHARS:
                break
            lines.extend(candidate)
        return "\n".join(lines).rstrip()


channel_search_client = ChannelSearchClient()
