#!/usr/bin/env python3
"""Exercise the zero-credential browser golden path through the Next.js BFF."""

from __future__ import annotations

import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

AI_BASE = os.getenv("SMOKE_AI_BASE", "http://127.0.0.1:8000").rstrip("/")
FRONTEND_BASE = os.getenv("SMOKE_FRONTEND_BASE", "http://localhost:7777").rstrip("/")
FRONTEND_ORIGIN = os.getenv("SMOKE_FRONTEND_ORIGIN", FRONTEND_BASE).rstrip("/")
SPOOFED_TENANT_ID = 999_999
SESSION_ID = "ci-smoke-session"
QUESTION = "Какие возможности есть у платформы?"

BROWSER_COOKIES = http.cookiejar.CookieJar()
BROWSER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(BROWSER_COOKIES)
)
BROWSER_MUTATION_HEADERS = {
    "Origin": FRONTEND_ORIGIN,
    "Sec-Fetch-Site": "same-origin",
}


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    attempts: int = 15,
) -> Any:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            open_request = opener.open if opener is not None else urllib.request.urlopen
            with open_request(request, timeout=10) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"{method} {url}: HTTP {exc.code}: {error_body}")
        except (OSError, ValueError) as exc:
            last_error = exc

        if attempt + 1 < attempts:
            time.sleep(2)

    raise RuntimeError(f"{method} {url} did not succeed") from last_error


def main() -> None:
    readiness = request_json("GET", f"{AI_BASE}/health/ready")
    assert readiness["status"] == "ready", readiness
    assert readiness["checkpoint_backend"] == "postgres", readiness

    anonymous_session = request_json(
        "GET",
        f"{FRONTEND_BASE}/api/auth/session",
        opener=BROWSER,
    )
    assert anonymous_session == {"authenticated": False}, anonymous_session

    login = request_json(
        "POST",
        f"{FRONTEND_BASE}/api/auth/login",
        opener=BROWSER,
        headers=BROWSER_MUTATION_HEADERS,
        payload={"username": "demo", "password": "demo-password-change-me"},
    )
    assert login["authenticated"] is True, login
    assert login["user"]["saas_user_id"] == 1, login
    assert "access_token" not in login, login
    assert any(
        cookie.name == "taap_session" and cookie.value for cookie in BROWSER_COOKIES
    ), "The frontend did not establish an HttpOnly-backed browser session"

    authenticated_session = request_json(
        "GET",
        f"{FRONTEND_BASE}/api/auth/session",
        opener=BROWSER,
    )
    assert authenticated_session["authenticated"] is True, authenticated_session
    assert authenticated_session["user"]["saas_user_id"] == 1, authenticated_session

    dashboard = request_json(
        "GET",
        f"{FRONTEND_BASE}/api/backend/dashboard",
        opener=BROWSER,
    )
    assert dashboard["data_source"] == "synthetic-demo", dashboard
    assert dashboard["profile"]["url"] == "t.me/demo_analytics_channel", dashboard
    assert dashboard["metrics"]["subscribers"]["value"] > 0, dashboard

    chats = request_json(
        "GET",
        f"{FRONTEND_BASE}/api/backend/chatbot/api/chats",
        opener=BROWSER,
    )
    assert chats["mode"] == "synthetic-read-only", chats
    assert isinstance(chats["chats"], list), chats

    answer = request_json(
        "POST",
        f"{FRONTEND_BASE}/api/backend/ai/brain/answer",
        opener=BROWSER,
        headers=BROWSER_MUTATION_HEADERS,
        payload={
            # The auth gateway must replace this attacker-controlled value
            # with the tenant identity from the HttpOnly-backed JWT session.
            "saas_user_id": SPOOFED_TENANT_ID,
            "session_id": SESSION_ID,
            "chat_id": "ci-smoke-chat",
            "user_id": "ci-smoke-user",
            "message_text": QUESTION,
            "channel_username": "demo_analytics_channel",
            "language": "ru",
        },
    )
    assert answer["reply_text"], answer
    assert answer["route"] in {"GENERAL", "SALES", "BARTER"}, answer

    spoofed_query = urllib.parse.urlencode(
        {"saas_user_id": SPOOFED_TENANT_ID, "limit": 100}
    )
    sessions = request_json(
        "GET",
        f"{FRONTEND_BASE}/api/backend/ai/chat/sessions?{spoofed_query}",
        opener=BROWSER,
    )
    assert any(
        session["session_id"] == SESSION_ID for session in sessions["sessions"]
    ), sessions

    history = request_json(
        "GET",
        f"{FRONTEND_BASE}/api/backend/ai/chat/history/{SESSION_ID}?{spoofed_query}",
        opener=BROWSER,
    )
    assert history["session_id"] == SESSION_ID, history
    assert history["total"] >= 2, history
    assert any(
        message["is_own"] and message["content"] == QUESTION
        for message in history["messages"]
    ), history
    assert any(
        not message["is_own"] and message["content"] == answer["reply_text"]
        for message in history["messages"]
    ), history

    print("Browser BFF Compose smoke test passed")


if __name__ == "__main__":
    main()
