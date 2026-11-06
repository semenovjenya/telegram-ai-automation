"""Durable, tenant-safe memory nodes for the LangGraph workflow."""

from __future__ import annotations

import asyncio
import logging

from langchain_core.messages import AIMessage, HumanMessage

from ..clients import postgres_client
from ..config import settings
from ..state import GraphState

logger = logging.getLogger(__name__)


async def load_memory(state: GraphState) -> GraphState:
    """Load the canonical conversation history without blocking the event loop."""

    try:
        history = await asyncio.to_thread(
            postgres_client.get_messages,
            state["saas_user_id"],
            state["session_id"],
            limit=settings.MODEL_HISTORY_LIMIT,
        )
    except Exception:
        logger.exception(
            "Failed to load memory for tenant=%s session=%s",
            state["saas_user_id"],
            state["session_id"],
        )
        raise
    return {**state, "history": history}


async def save_user_message(state: GraphState) -> GraphState:
    """Persist the user message before any model or side-effect execution."""

    try:
        await asyncio.to_thread(
            postgres_client.add_user_message,
            state["saas_user_id"],
            state["session_id"],
            state["message_text"],
            chat_id=state.get("chat_id"),
            channel_username=state.get("channel_username"),
        )
    except Exception:
        logger.exception(
            "Failed to persist user message for tenant=%s session=%s",
            state["saas_user_id"],
            state["session_id"],
        )
        raise
    # The router sees the persisted message through this invocation state. The
    # database copy carries its canonical timestamp for future invocations.
    return {
        **state,
        "history": [
            *state.get("history", []),
            HumanMessage(content=state["message_text"]),
        ],
    }


async def save_ai_message(state: GraphState) -> GraphState:
    """Persist the final assistant response before returning it to callers."""

    try:
        await asyncio.to_thread(
            postgres_client.add_ai_message,
            state["saas_user_id"],
            state["session_id"],
            state["reply_text"],
            chat_id=state.get("chat_id"),
            channel_username=state.get("channel_username"),
        )
    except Exception:
        logger.exception(
            "Failed to persist assistant message for tenant=%s session=%s",
            state["saas_user_id"],
            state["session_id"],
        )
        raise
    return {
        **state,
        "history": [*state.get("history", []), AIMessage(content=state["reply_text"])],
    }
