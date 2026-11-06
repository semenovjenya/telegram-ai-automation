"""Streaming request-body limit regressions for the public gateway."""

import asyncio
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_body_limit():
    path = ROOT / "auth-backend" / "body_limit.py"
    spec = importlib.util.spec_from_file_location("security_body_limit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_request(scope, chunks):
    body_limit = _load_body_limit()
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    sent = []
    reached_app = False

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    async def consume_body(_scope, receive_body, send_response):
        nonlocal reached_app
        while True:
            message = await receive_body()
            if not message.get("more_body", False):
                break
        reached_app = True
        await send_response(
            {"type": "http.response.start", "status": 204, "headers": []}
        )
        await send_response({"type": "http.response.body", "body": b""})

    middleware = body_limit.RequestBodyLimitMiddleware(consume_body)
    asyncio.run(middleware(scope, receive, send))
    return body_limit, sent, reached_app


def test_streamed_login_body_is_rejected_without_content_length() -> None:
    body_limit, sent, reached_app = _run_request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [(b"content-type", b"application/json")],
        },
        [b"x" * 4096, b"y" * 4097],
    )

    assert body_limit.LOGIN_BODY_LIMIT_BYTES == 8192
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"]) == {"detail": "Request body is too large"}
    assert reached_app is False


def test_declared_oversized_body_is_rejected_before_receive() -> None:
    body_limit = _load_body_limit()
    sent = []
    receive_called = False
    app_called = False

    async def receive():
        nonlocal receive_called
        receive_called = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    async def app(_scope, _receive, _send):
        nonlocal app_called
        app_called = True

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/chatbot/api/chats/chat-1/messages",
        "headers": [(b"content-length", b"65537")],
    }
    asyncio.run(body_limit.RequestBodyLimitMiddleware(app)(scope, receive, send))

    assert sent[0]["status"] == 413
    assert receive_called is False
    assert app_called is False


def test_malformed_content_length_cannot_bypass_stream_counting() -> None:
    _, sent, reached_app = _run_request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/ai/brain/answer",
            "headers": [(b"content-length", b"not-a-number")],
        },
        [b"x" * (1024 * 1024), b"y"],
    )

    assert sent[0]["status"] == 413
    assert reached_app is False


def test_safe_methods_bypass_body_reader() -> None:
    _, sent, reached_app = _run_request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/dashboard",
            "headers": [(b"content-length", b"999999999")],
        },
        [b""],
    )

    assert sent[0]["status"] == 204
    assert reached_app is True
