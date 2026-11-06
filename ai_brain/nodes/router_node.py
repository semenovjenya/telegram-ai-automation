"""Deterministic intent router for the AI-BRAIN graph."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from langchain_core.messages import BaseMessage

from ..state import GraphState

logger = logging.getLogger(__name__)

SALES_KEYWORDS = frozenset(
    {
        "реклама",
        "размещение",
        "размещения",
        "стоимость",
        "цена",
        "цену",
        "купить",
        "заказать",
        "прайс",
        "медиакит",
        "advertising",
        "price",
        "cost",
        "buy",
    }
)

BARTER_KEYWORDS = frozenset(
    {
        "бартер",
        "партнерство",
        "партнёрство",
        "взаимное продвижение",
        "взаимный репост",
        "коллаборация",
        "похожие каналы",
        "найди каналы",
        "поиск каналов",
        "аналитика канала",
        "статистика канала",
        "дашборд",
        "конкуренты",
        "smm",
        "barter",
        "collaboration",
        "partnership",
        "similar channels",
        "dashboard",
    }
)


def _recent_text(history: Iterable[BaseMessage], limit: int = 4) -> str:
    recent = list(history)[-limit:]
    return " ".join(
        str(message.content) for message in recent if getattr(message, "content", None)
    ).casefold()


def classify_route(message: str, history: Iterable[BaseMessage] = ()) -> str:
    """Classify a request into a stable, testable route."""

    text = f"{_recent_text(history)} {message}".casefold()
    if any(keyword in text for keyword in BARTER_KEYWORDS):
        return "BARTER"
    if any(keyword in text for keyword in SALES_KEYWORDS):
        return "SALES"
    return "GENERAL"


async def route_message(state: GraphState) -> GraphState:
    route = classify_route(state["message_text"], state.get("history", []))
    logger.info(
        "Routed tenant=%s session=%s to %s",
        state["saas_user_id"],
        state["session_id"],
        route,
    )
    return {**state, "route": route}


def route_condition(state: GraphState) -> str:
    route = state.get("route", "GENERAL")
    if route not in {"GENERAL", "SALES", "BARTER"}:
        logger.error("Unexpected route %r; using GENERAL", route)
        return "GENERAL"
    return route


# Backwards-compatible alias for older integrations.
route_message_with_llm = route_message
