"""General-purpose conversational agent node."""

from __future__ import annotations

import logging

from ..prompts import get_general_system_prompt
from ..state import GraphState
from .agent_runtime import (
    build_messages,
    create_chat_model,
    demo_reply,
    extract_text,
    result_state,
)

logger = logging.getLogger(__name__)


async def process_general(state: GraphState) -> GraphState:
    if not state["message_text"].strip():
        raise ValueError("message_text cannot be blank")

    from ..config import settings

    if settings.LLM_PROVIDER == "mock":
        return result_state(
            state,
            agent="general",
            reply_text=demo_reply(state, "general"),
            metadata={"demo": True},
        )

    context = {
        "saas_user_id": state["saas_user_id"],
        "channel_username": state.get("channel_username"),
        "language": state.get("language"),
        "metadata": state.get("metadata"),
    }
    try:
        response = await create_chat_model().ainvoke(
            build_messages(get_general_system_prompt(context), state)
        )
        reply = extract_text(response)
        if not reply:
            raise RuntimeError("model returned an empty response")
    except Exception:
        logger.exception("General agent invocation failed")
        return result_state(
            state,
            agent="general",
            reply_text="Сервис генерации временно недоступен. Попробуйте ещё раз.",
            metadata={"degraded": True},
        )

    return result_state(state, agent="general", reply_text=reply)
