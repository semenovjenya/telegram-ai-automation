"""Sales and advertising agent with bounded RAG context."""

from __future__ import annotations

import logging

from ..prompts import get_sales_system_prompt
from ..state import GraphState
from ..tools.rag_tool import retrieve_rag_context
from .agent_runtime import (
    build_messages,
    create_chat_model,
    demo_reply,
    extract_text,
    result_state,
)

logger = logging.getLogger(__name__)


async def process_sales(state: GraphState) -> GraphState:
    from ..config import settings

    if settings.LLM_PROVIDER == "mock":
        return result_state(
            state,
            agent="sales",
            reply_text=demo_reply(state, "sales"),
            metadata={"demo": True, "tools_used": 0},
        )

    channel = state.get("channel_username")
    rag_context = await retrieve_rag_context(
        state["message_text"],
        channel_username=channel,
        top_k=3,
    )
    context = {
        "saas_user_id": state["saas_user_id"],
        "channel_username": channel,
        "language": state.get("language"),
        "metadata": state.get("metadata"),
    }
    try:
        response = await create_chat_model().ainvoke(
            build_messages(get_sales_system_prompt(context, rag_context), state)
        )
        reply = extract_text(response)
        if not reply:
            raise RuntimeError("model returned an empty response")
    except Exception:
        logger.exception("Sales agent invocation failed")
        return result_state(
            state,
            agent="sales",
            reply_text="Сервис генерации временно недоступен. Попробуйте ещё раз.",
            metadata={"degraded": True, "tools_used": int(bool(rag_context))},
        )

    return result_state(
        state,
        agent="sales",
        reply_text=reply,
        metadata={"tools_used": int(bool(rag_context))},
    )
