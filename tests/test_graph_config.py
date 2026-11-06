import asyncio

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from ai_brain.clients import tenant_session_uuid
from ai_brain.config import settings
from ai_brain.graph.workflow import BrainGraph, build_graph


class FakeGraph:
    def __init__(self) -> None:
        self.config = None

    async def ainvoke(self, state, config):
        self.config = config
        return state


def test_graph_overrides_untrusted_thread_id() -> None:
    graph = BrainGraph()
    fake = FakeGraph()
    graph.graph = fake
    graph.checkpointer = object()
    state = {"saas_user_id": 7, "session_id": "shared"}

    asyncio.run(
        graph.process(
            state,
            config={"configurable": {"thread_id": "attacker-controlled"}},
        )
    )

    assert fake.config["configurable"]["thread_id"] == tenant_session_uuid(7, "shared")
    assert fake.config["configurable"]["checkpoint_ns"] == "tenant:7"


def test_graph_contains_every_declared_route() -> None:
    graph = build_graph(MemorySaver())
    node_names = set(graph.get_graph().nodes)
    assert {
        "load_memory",
        "save_user_message",
        "router_node",
        "general_agent",
        "sales_agent",
        "barter_agent",
        "save_ai_message",
    }.issubset(node_names)


def test_memory_checkpointer_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CHECKPOINT_BACKEND", "memory")
    graph = BrainGraph()
    asyncio.run(graph.initialize())
    assert graph.is_ready
    assert graph.checkpoint_backend == "memory"
    asyncio.run(graph.close())
    assert not graph.is_ready


def test_async_postgres_checkpointer_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class Saver(MemorySaver):
        async def setup(self) -> None:
            events.append("setup")

    class Context:
        async def __aenter__(self):
            events.append("enter")
            return Saver()

        async def __aexit__(self, *args):
            events.append("exit")

    monkeypatch.setattr(settings, "CHECKPOINT_BACKEND", "postgres")
    monkeypatch.setattr(
        AsyncPostgresSaver,
        "from_conn_string",
        lambda *args, **kwargs: Context(),
    )
    graph = BrainGraph()
    asyncio.run(graph.initialize())
    assert graph.checkpoint_backend == "postgres"
    asyncio.run(graph.close())
    assert events == ["enter", "setup", "exit"]


def test_postgres_failure_uses_only_explicit_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingContext:
        async def __aenter__(self):
            raise RuntimeError("postgres offline")

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(settings, "CHECKPOINT_BACKEND", "postgres")
    monkeypatch.setattr(
        AsyncPostgresSaver,
        "from_conn_string",
        lambda *args, **kwargs: FailingContext(),
    )
    monkeypatch.setattr(settings, "ALLOW_MEMORY_CHECKPOINT_FALLBACK", True)
    graph = BrainGraph()
    asyncio.run(graph.initialize())
    assert graph.checkpoint_backend == "memory-fallback"

    monkeypatch.setattr(settings, "ALLOW_MEMORY_CHECKPOINT_FALLBACK", False)
    fail_closed_graph = BrainGraph()
    with pytest.raises(RuntimeError, match="postgres offline"):
        asyncio.run(fail_closed_graph.initialize())
