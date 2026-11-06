"""Streaming ASGI request-body limits for the public API gateway."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

LOGIN_BODY_LIMIT_BYTES = 8 * 1024
CHAT_MESSAGE_BODY_LIMIT_BYTES = 64 * 1024
DEFAULT_MUTATION_BODY_LIMIT_BYTES = 1024 * 1024

_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_CHAT_MESSAGE_PATH = re.compile(r"/api/chatbot/api/chats/[^/]+/messages\Z")

AsgiMessage = dict[str, Any]
Receive = Callable[[], Awaitable[AsgiMessage]]
Send = Callable[[AsgiMessage], Awaitable[None]]
AsgiApp = Callable[[dict[str, Any], Receive, Send], Awaitable[None]]


class RequestBodyTooLarge(Exception):
    """Raised as soon as a streamed request exceeds its route limit."""


def request_body_limit(scope: dict[str, Any]) -> int | None:
    """Return the route limit, or ``None`` for methods without request bodies."""

    method = str(scope.get("method", "")).upper()
    if method not in _MUTATION_METHODS:
        return None

    path = str(scope.get("path", ""))
    if path == "/api/auth/login":
        return LOGIN_BODY_LIMIT_BYTES
    if method == "POST" and _CHAT_MESSAGE_PATH.fullmatch(path):
        return CHAT_MESSAGE_BODY_LIMIT_BYTES
    return DEFAULT_MUTATION_BODY_LIMIT_BYTES


def _declared_content_length(scope: dict[str, Any]) -> int | None:
    values = [
        value.strip()
        for name, value in scope.get("headers", [])
        if name.lower() == b"content-length"
    ]
    if len(values) != 1 or not values[0].isdigit():
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


async def _send_too_large(send: Send) -> None:
    body = json.dumps(
        {"detail": "Request body is too large"},
        separators=(",", ":"),
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestBodyLimitMiddleware:
    """Bound request streams even when Content-Length is absent or forged."""

    def __init__(self, app: AsgiApp) -> None:
        self.app = app

    async def __call__(
        self, scope: dict[str, Any], receive: Receive, send: Send
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        limit = request_body_limit(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared_length = _declared_content_length(scope)
        if declared_length is not None and declared_length > limit:
            await _send_too_large(send)
            return

        total_bytes = 0
        response_started = False

        async def limited_receive() -> AsgiMessage:
            nonlocal total_bytes
            message = await receive()
            if message.get("type") == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > limit:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message: AsgiMessage) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if response_started:
                raise
            await _send_too_large(send)
