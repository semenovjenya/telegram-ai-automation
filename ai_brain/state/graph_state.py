"""Typed state contract shared by every LangGraph node."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from langchain_core.messages import BaseMessage


class GraphState(TypedDict):
    """Per-invocation state; PostgreSQL remains the conversation source of truth."""

    saas_user_id: int
    session_id: str
    chat_id: str | int
    user_id: str | int
    message_text: str
    channel_username: str | None
    language: str | None
    metadata: dict[str, Any] | None
    history: list[BaseMessage]
    route: NotRequired[str]
    reply_text: NotRequired[str]
    used_agent: NotRequired[str]
    output_metadata: NotRequired[dict[str, Any]]
    image_path: NotRequired[str | None]
