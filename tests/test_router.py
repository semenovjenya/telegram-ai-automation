import asyncio

from langchain_core.messages import HumanMessage

from ai_brain.nodes.router_node import classify_route, route_condition, route_message


def test_router_covers_all_agent_routes() -> None:
    assert classify_route("Покажи цену размещения") == "SALES"
    assert classify_route("Найди похожие каналы для бартера") == "BARTER"
    assert classify_route("Привет, чем ты можешь помочь?") == "GENERAL"


def test_router_uses_recent_context() -> None:
    history = [HumanMessage(content="Обсуждаем взаимное продвижение")]
    assert classify_route("Продолжай", history) == "BARTER"


def test_route_node_updates_state() -> None:
    state = {
        "saas_user_id": 1,
        "session_id": "s1",
        "message_text": "Сколько стоит реклама?",
        "history": [],
    }
    result = asyncio.run(route_message(state))
    assert result["route"] == "SALES"


def test_invalid_route_fails_safe_to_general() -> None:
    assert route_condition({"route": "UNKNOWN"}) == "GENERAL"
