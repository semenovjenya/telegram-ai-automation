import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from ai_brain.nodes import memory_nodes


def state() -> dict:
    return {
        "saas_user_id": 7,
        "session_id": "memory-test",
        "chat_id": 10,
        "user_id": 11,
        "message_text": "Вопрос",
        "channel_username": "example",
        "language": "ru",
        "metadata": {},
        "history": [],
        "reply_text": "Ответ",
    }


def test_memory_nodes_load_and_persist_in_order(monkeypatch) -> None:
    calls: list[tuple] = []

    def get_messages(*args, **kwargs):
        calls.append(("get", *args, kwargs))
        return [HumanMessage(content="Ранее")]

    def add_user_message(*args, **kwargs):
        calls.append(("user", *args, kwargs))

    def add_ai_message(*args, **kwargs):
        calls.append(("assistant", *args, kwargs))

    monkeypatch.setattr(memory_nodes.postgres_client, "get_messages", get_messages)
    monkeypatch.setattr(
        memory_nodes.postgres_client,
        "add_user_message",
        add_user_message,
    )
    monkeypatch.setattr(
        memory_nodes.postgres_client,
        "add_ai_message",
        add_ai_message,
    )

    loaded = asyncio.run(memory_nodes.load_memory(state()))
    with_user = asyncio.run(memory_nodes.save_user_message(loaded))
    completed = asyncio.run(memory_nodes.save_ai_message(with_user))

    assert [message.content for message in completed["history"]] == [
        "Ранее",
        "Вопрос",
        "Ответ",
    ]
    assert isinstance(completed["history"][-1], AIMessage)
    assert [call[0] for call in calls] == ["get", "user", "assistant"]
    assert calls[0] == (
        "get",
        7,
        "memory-test",
        {"limit": memory_nodes.settings.MODEL_HISTORY_LIMIT},
    )
    assert calls[1][-1]["channel_username"] == "example"


@pytest.mark.parametrize(
    ("node", "method"),
    [
        (memory_nodes.load_memory, "get_messages"),
        (memory_nodes.save_user_message, "add_user_message"),
        (memory_nodes.save_ai_message, "add_ai_message"),
    ],
)
def test_storage_failures_propagate(monkeypatch, node, method) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("storage offline")

    monkeypatch.setattr(memory_nodes.postgres_client, method, fail)
    with pytest.raises(RuntimeError, match="storage offline"):
        asyncio.run(node(state()))
