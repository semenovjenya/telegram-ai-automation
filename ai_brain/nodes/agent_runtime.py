"""Shared, testable runtime helpers for AI agent nodes."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config import settings
from ..state import GraphState

AgentName = Literal["general", "sales", "barter"]
MAX_HISTORY_MESSAGES = 30


def create_chat_model() -> ChatOpenAI:
    """Create the configured production model without import-time clients."""

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=settings.OPENAI_TEMPERATURE,
        max_tokens=settings.MAX_OUTPUT_TOKENS,
        api_key=settings.OPENAI_API_KEY,
        timeout=45.0,
        max_retries=2,
    )


def build_messages(system_prompt: str, state: GraphState) -> list[BaseMessage]:
    history = history_before_current(state)[-MAX_HISTORY_MESSAGES:]
    return [
        SystemMessage(content=system_prompt),
        *history,
        HumanMessage(content=state["message_text"]),
    ]


def history_before_current(state: GraphState) -> list[BaseMessage]:
    """Return conversation history without this invocation's saved message.

    ``save_user_message`` deliberately persists and appends the current user
    message before routing to an agent. Agents still append that message to the
    model request, so the trailing in-memory copy must be removed first.
    """

    history = list(state.get("history", []))
    if (
        history
        and isinstance(history[-1], HumanMessage)
        and history[-1].content == state["message_text"]
    ):
        return history[:-1]
    return history


def extract_text(response: AIMessage | BaseMessage) -> str:
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def demo_reply(state: GraphState, agent: AgentName) -> str:
    """Return a deterministic local response for the zero-credential demo stack."""

    channel = state.get("channel_username")
    subject = f" для @{channel}" if channel else ""
    if agent == "sales":
        return (
            f"Демо-режим: подготовлю медиаплан и оценку размещения{subject}. "
            "Подключите OpenAI и источник метрик, чтобы получить расчёт по данным."
        )
    if agent == "barter":
        return (
            f"Демо-режим: сценарий подбора партнёров{subject} готов. "
            "Любой репост остаётся dry-run до отдельного подтверждения."
        )
    return (
        "Демо-режим AI-BRAIN работает: маршрутизация, tenant-safe история и "
        "API доступны. Для LLM-ответов переключите LLM_PROVIDER на openai."
    )


def result_state(
    state: GraphState,
    *,
    agent: AgentName,
    reply_text: str,
    metadata: dict | None = None,
) -> GraphState:
    return {
        **state,
        "reply_text": reply_text,
        "used_agent": agent,
        "output_metadata": {
            "agent_type": agent,
            "llm_provider": settings.LLM_PROVIDER,
            **(metadata or {}),
        },
    }
