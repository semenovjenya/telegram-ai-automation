import asyncio

from langchain_core.messages import AIMessage, HumanMessage

from ai_brain.config import settings
from ai_brain.nodes import agent_runtime, general_node
from ai_brain.nodes.agent_runtime import build_messages, history_before_current
from ai_brain.nodes.general_node import process_general
from ai_brain.nodes.sales_node import process_sales


def state(message: str, channel: str | None = None) -> dict:
    return {
        "saas_user_id": 9,
        "session_id": "agent-test",
        "chat_id": 10,
        "user_id": 11,
        "message_text": message,
        "channel_username": channel,
        "language": "ru",
        "metadata": {},
        "history": [],
    }


def test_general_agent_has_zero_credential_demo_mode() -> None:
    result = asyncio.run(process_general(state("Привет")))
    assert result["used_agent"] == "general"
    assert result["output_metadata"]["demo"] is True
    assert "Демо-режим" in result["reply_text"]


def test_chat_model_receives_configured_output_limit(monkeypatch) -> None:
    captured: dict = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agent_runtime, "ChatOpenAI", fake_chat_openai)
    monkeypatch.setattr(settings, "MAX_OUTPUT_TOKENS", 777)

    model = agent_runtime.create_chat_model()

    assert model is not None
    assert captured["max_tokens"] == 777


def test_sales_demo_keeps_channel_context() -> None:
    result = asyncio.run(process_sales(state("Сколько стоит реклама?", "example")))
    assert result["used_agent"] == "sales"
    assert "@example" in result["reply_text"]
    assert result["output_metadata"]["tools_used"] == 0


def test_model_messages_include_current_user_message_once() -> None:
    current = state("Повтори")
    current["history"] = [
        HumanMessage(content="Раньше"),
        AIMessage(content="Ответ"),
        HumanMessage(content="Повтори"),
    ]

    messages = build_messages("system", current)

    assert [message.content for message in messages] == [
        "system",
        "Раньше",
        "Ответ",
        "Повтори",
    ]
    assert [message.content for message in messages].count("Повтори") == 1


def test_current_only_history_is_the_first_message() -> None:
    current = state("Первый вопрос")
    current["history"] = [HumanMessage(content="Первый вопрос")]

    assert history_before_current(current) == []


def test_general_agent_passes_current_channel_to_model_prompt(monkeypatch) -> None:
    captured_messages = []

    class FakeModel:
        async def ainvoke(self, messages):
            captured_messages.extend(messages)
            return AIMessage(content="tenant-safe reply")

    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(general_node, "create_chat_model", lambda: FakeModel())

    result = asyncio.run(
        general_node.process_general(state("Расскажи о канале", "tenant_channel"))
    )

    assert result["reply_text"] == "tenant-safe reply"
    assert "@tenant_channel" in captured_messages[0].content
