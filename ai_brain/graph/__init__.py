"""Lazy public exports for the LangGraph workflow."""

from importlib import import_module
from typing import Any

__all__ = ["build_graph", "BrainGraph", "brain_graph"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    return getattr(import_module(".workflow", __name__), name)
