"""Public API package without import-time application side effects."""

from importlib import import_module
from typing import Any

__all__ = [
    "app",
    "create_app",
    "router",
    "BrainRequest",
    "BrainResponse",
    "ErrorDetail",
    "ErrorResponse",
]


def __getattr__(name: str) -> Any:
    """Load the FastAPI app and schemas only when a caller requests them."""
    if name in {"app", "create_app"}:
        return getattr(import_module(".app", __name__), name)
    if name == "router":
        return getattr(import_module(".routes", __name__), name)
    if name in {"BrainRequest", "BrainResponse", "ErrorDetail", "ErrorResponse"}:
        return getattr(import_module(".schemas", __name__), name)
    raise AttributeError(name)
