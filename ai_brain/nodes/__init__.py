"""Graph node exports without eager model or database initialization."""

from importlib import import_module
from typing import Any

__all__ = [
    "load_memory",
    "save_user_message",
    "save_ai_message",
    "route_message",
    "route_condition",
    "route_message_with_llm",
    "process_general",
    "process_sales",
    "process_barter",
]

_MODULE_BY_NAME = {
    "load_memory": ".memory_nodes",
    "save_user_message": ".memory_nodes",
    "save_ai_message": ".memory_nodes",
    "route_message": ".router_node",
    "route_condition": ".router_node",
    "route_message_with_llm": ".router_node",
    "process_general": ".general_node",
    "process_sales": ".sales_node",
    "process_barter": ".barter_node",
}


def __getattr__(name: str) -> Any:
    """Import only the node required by the caller."""
    module_name = _MODULE_BY_NAME.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(module_name, __name__), name)
