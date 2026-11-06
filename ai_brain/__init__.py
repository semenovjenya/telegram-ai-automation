"""AI-BRAIN package.

The package intentionally avoids importing the application at module import time;
configuration, database connections and model clients are initialized explicitly by
the FastAPI lifespan instead.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.3.0"
__all__ = [
    "settings",
    "GraphState",
    "brain_graph",
    "BrainGraph",
    "app",
    "BrainRequest",
    "BrainResponse",
]


def __getattr__(name: str) -> Any:
    if name == "settings":
        from .config import settings

        return settings
    if name == "GraphState":
        from .state import GraphState

        return GraphState
    if name in {"brain_graph", "BrainGraph"}:
        from .graph import BrainGraph, brain_graph

        return {"brain_graph": brain_graph, "BrainGraph": BrainGraph}[name]
    if name in {"app", "BrainRequest", "BrainResponse"}:
        from .api import BrainRequest, BrainResponse, app

        return {
            "app": app,
            "BrainRequest": BrainRequest,
            "BrainResponse": BrainResponse,
        }[name]
    raise AttributeError(name)
