"""Real graph, deterministic mock agents and explicit in-memory persistence.

This tests routing and history without PostgreSQL, Telegram or LLM requests.
It does not test browser authentication, persistent restart recovery or live tools.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from unittest.mock import patch

from examples.demo_environment import configure_demo

configure_demo()

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from ai_brain.clients import postgres_client  # noqa: E402
from ai_brain.graph.workflow import BrainGraph  # noqa: E402


async def run_demo() -> dict:
    store: dict[tuple, list] = defaultdict(list)

    def get_messages(tenant, session, *, limit):
        return list(store[(tenant, session)][-limit:])

    def save_user(tenant, session, message, **kwargs):
        store[(tenant, session)].append(HumanMessage(content=message))

    def save_ai(tenant, session, message, **kwargs):
        store[(tenant, session)].append(AIMessage(content=message))

    cases = [
        ("general", "Привет"),
        ("sales", "Сколько стоит размещение рекламы?"),
        ("barter", "Предложи бартер и похожие каналы"),
    ]
    results = []
    graph = BrainGraph()
    await graph.initialize()
    try:
        with (
            patch.object(postgres_client, "get_messages", get_messages),
            patch.object(postgres_client, "add_user_message", save_user),
            patch.object(postgres_client, "add_ai_message", save_ai),
        ):
            for route, question in cases:
                state = dict(
                    saas_user_id=1,
                    session_id=route,
                    chat_id="demo",
                    user_id="demo",
                    message_text=question,
                    channel_username="demo_analytics_channel",
                    language="ru",
                    metadata={},
                    history=[],
                )
                result = await graph.process(state)
                assert result["used_agent"] == route
                assert len(store[(1, route)]) == 2
                results.append(
                    {
                        "route": result["route"],
                        "agent": result["used_agent"],
                        "reply": result["reply_text"],
                        "stored_messages": len(store[(1, route)]),
                    }
                )
    finally:
        await graph.close()
    return {
        "mode": "mock agents + in-memory history/checkpoints",
        "external_calls": 0,
        "scenarios": results,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_demo()), ensure_ascii=False, indent=2))
