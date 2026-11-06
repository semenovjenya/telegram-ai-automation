"""LangGraph workflow and durable checkpointer lifecycle."""

from __future__ import annotations

import asyncio
import logging
from contextlib import AbstractAsyncContextManager
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from ..clients import tenant_session_uuid
from ..config import settings
from ..nodes import (
    load_memory,
    process_barter,
    process_general,
    process_sales,
    route_condition,
    route_message,
    save_ai_message,
    save_user_message,
)
from ..state import GraphState

logger = logging.getLogger(__name__)


def build_graph(checkpointer: Any) -> Any:
    """Build the production graph using an explicitly managed checkpointer."""

    workflow = StateGraph(GraphState)
    workflow.add_node("load_memory", load_memory)
    workflow.add_node("save_user_message", save_user_message)
    workflow.add_node("router_node", route_message)
    workflow.add_node("general_agent", process_general)
    workflow.add_node("sales_agent", process_sales)
    workflow.add_node("barter_agent", process_barter)
    workflow.add_node("save_ai_message", save_ai_message)

    workflow.set_entry_point("load_memory")
    workflow.add_edge("load_memory", "save_user_message")
    workflow.add_edge("save_user_message", "router_node")
    workflow.add_conditional_edges(
        "router_node",
        route_condition,
        {
            "GENERAL": "general_agent",
            "SALES": "sales_agent",
            "BARTER": "barter_agent",
        },
    )
    workflow.add_edge("general_agent", "save_ai_message")
    workflow.add_edge("sales_agent", "save_ai_message")
    workflow.add_edge("barter_agent", "save_ai_message")
    workflow.add_edge("save_ai_message", END)
    return workflow.compile(checkpointer=checkpointer)


class BrainGraph:
    """Own the graph and the full lifecycle of its checkpoint backend."""

    def __init__(self) -> None:
        self.graph: Any | None = None
        self.checkpointer: Any | None = None
        self.checkpoint_backend: str | None = None
        self._checkpointer_context: AbstractAsyncContextManager[Any] | None = None
        self._initialization_lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        return self.graph is not None and self.checkpointer is not None

    async def initialize(self) -> None:
        if self.is_ready:
            return
        async with self._initialization_lock:
            if self.is_ready:
                return

            if settings.CHECKPOINT_BACKEND == "memory":
                self.checkpointer = MemorySaver()
                self.checkpoint_backend = "memory"
            else:
                context: AbstractAsyncContextManager[Any] | None = None
                context_entered = False
                try:
                    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

                    context = AsyncPostgresSaver.from_conn_string(
                        settings.postgres_connection_string
                    )
                    checkpointer = await context.__aenter__()
                    context_entered = True
                    await checkpointer.setup()
                    self._checkpointer_context = context
                    self.checkpointer = checkpointer
                    self.checkpoint_backend = "postgres"
                except Exception:
                    if context is not None and context_entered:
                        await context.__aexit__(None, None, None)
                    if not settings.ALLOW_MEMORY_CHECKPOINT_FALLBACK:
                        logger.exception(
                            "PostgreSQL checkpointer initialization failed"
                        )
                        raise
                    logger.exception(
                        "PostgreSQL checkpointer unavailable; explicit memory fallback enabled"
                    )
                    self.checkpointer = MemorySaver()
                    self.checkpoint_backend = "memory-fallback"

            self.graph = build_graph(self.checkpointer)
            logger.info(
                "BrainGraph initialized with %s checkpointing",
                self.checkpoint_backend,
            )

    async def process(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> GraphState:
        if not self.is_ready:
            await self.initialize()
        assert self.graph is not None

        thread_id = tenant_session_uuid(
            int(state["saas_user_id"]),
            str(state["session_id"]),
        )
        invocation_config = dict(config or {})
        configurable = dict(invocation_config.get("configurable", {}))
        configurable["thread_id"] = thread_id
        configurable["checkpoint_ns"] = f"tenant:{state['saas_user_id']}"
        invocation_config["configurable"] = configurable

        logger.info(
            "Processing tenant=%s session=%s",
            state["saas_user_id"],
            state["session_id"],
        )
        return await self.graph.ainvoke(state, config=invocation_config)

    async def close(self) -> None:
        if self._checkpointer_context is not None:
            await self._checkpointer_context.__aexit__(None, None, None)
        self.graph = None
        self.checkpointer = None
        self.checkpoint_backend = None
        self._checkpointer_context = None


brain_graph = BrainGraph()
