from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

import ai_brain.api.app as app_module
from ai_brain.clients.postgres_client import HistoryPage, HistoryRecord
from ai_brain.config import settings


def _ready_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(app_module.postgres_client, "ensure_schema", lambda: None)
    monkeypatch.setattr(app_module.postgres_client, "close", lambda: None)
    monkeypatch.setattr(app_module.postgres_client, "ping", lambda: True)

    async def initialize() -> None:
        app_module.brain_graph.graph = object()
        app_module.brain_graph.checkpointer = object()
        app_module.brain_graph.checkpoint_backend = "memory"

    async def close() -> None:
        app_module.brain_graph.graph = None
        app_module.brain_graph.checkpointer = None

    monkeypatch.setattr(app_module.brain_graph, "initialize", initialize)
    monkeypatch.setattr(app_module.brain_graph, "close", close)
    return TestClient(app_module.create_app())


def _headers() -> dict[str, str]:
    return {"X-API-Key": settings.API_KEY}


def test_lifecycle_health_and_auth_contract(monkeypatch) -> None:
    with _ready_client(monkeypatch) as client:
        live = client.get("/health")
        ready = client.get("/health/ready")
        unauthorized = client.post("/api/brain/answer", json={})

    assert live.status_code == 200
    assert live.headers["cache-control"] == "no-store"
    assert live.headers["x-content-type-options"] == "nosniff"
    assert ready.status_code == 200
    assert ready.json()["checkpoint_backend"] == "memory"
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "ApiKey"
    assert unauthorized.json()["error"]["code"] == "UNAUTHORIZED"


def test_answer_returns_typed_sanitized_response(monkeypatch) -> None:
    async def process(state, config=None):
        return {
            **state,
            "reply_text": "Готово",
            "used_agent": "barter",
            "route": "BARTER",
            "image_path": "/private/path/dashboard.png",
            "output_metadata": {
                "image_path": "/another/private/path/dashboard.png",
                "tools_used": 1,
            },
        }

    monkeypatch.setattr(app_module.brain_graph, "process", process)
    payload = {
        "saas_user_id": 1,
        "session_id": "api-test",
        "chat_id": 2,
        "user_id": 3,
        "message_text": "Подбери партнёров",
        "channel_username": "example",
    }

    with _ready_client(monkeypatch) as client:
        response = client.post(
            "/api/brain/answer",
            headers=_headers(),
            json=payload,
        )

    assert response.status_code == 200
    assert response.json() == {
        "reply_text": "Готово",
        "used_agent": "barter",
        "route": "BARTER",
        "metadata": {"image_filename": "dashboard.png", "tools_used": 1},
    }


def test_answer_hides_internal_processing_errors(monkeypatch) -> None:
    async def fail(*args, **kwargs):
        raise RuntimeError("database.internal:5432 secret")

    monkeypatch.setattr(app_module.brain_graph, "process", fail)
    payload = {
        "saas_user_id": 1,
        "session_id": "api-test",
        "chat_id": 2,
        "user_id": 3,
        "message_text": "Привет",
    }
    with _ready_client(monkeypatch) as client:
        response = client.post(
            "/api/brain/answer",
            headers=_headers(),
            json=payload,
        )

    assert response.status_code == 503
    assert "database.internal" not in response.text
    assert response.json()["error"]["code"] == "PROCESSING_UNAVAILABLE"


def test_history_sessions_and_artifacts_are_tenant_scoped(
    monkeypatch,
    tmp_path: Path,
) -> None:
    messages = [
        HumanMessage(
            content="Вопрос",
            additional_kwargs={"timestamp": "2026-01-01T00:00:00+00:00"},
        ),
        AIMessage(
            content="Ответ",
            additional_kwargs={"timestamp": "2026-01-01T00:00:01+00:00"},
        ),
    ]
    calls: list[tuple] = []

    def get_history(*args, **kwargs):
        calls.append((*args, kwargs))
        return HistoryPage(
            records=tuple(
                HistoryRecord(
                    id=100 + index,
                    message=message,
                    created_at=datetime(2026, 1, index, tzinfo=UTC),
                )
                for index, message in enumerate(messages, start=1)
            ),
            total=9,
        )

    def list_sessions(*args):
        calls.append(args)
        return [{"session_id": "owned"}]

    monkeypatch.setattr(app_module.postgres_client, "get_history", get_history)
    monkeypatch.setattr(app_module.postgres_client, "list_sessions", list_sessions)
    monkeypatch.setattr(settings, "ARTIFACTS_DIR", tmp_path)
    (tmp_path / "dashboard.png").write_bytes(b"png-fixture")

    with _ready_client(monkeypatch) as client:
        history = client.get(
            "/api/chat/history/owned?saas_user_id=7",
            headers=_headers(),
        )
        sessions = client.get(
            "/api/chat/sessions?saas_user_id=7&limit=25",
            headers=_headers(),
        )
        image = client.get(
            "/api/brain/image/dashboard.png",
            headers=_headers(),
        )
        invalid_image = client.get(
            "/api/brain/image/dashboard.txt",
            headers=_headers(),
        )

    assert history.status_code == 200
    assert history.json()["messages"][0]["is_own"] is True
    assert history.json()["messages"][1]["is_own"] is False
    assert [message["id"] for message in history.json()["messages"]] == ["101", "102"]
    assert history.json()["returned_count"] == 2
    assert history.json()["total"] == 9
    assert sessions.json()["sessions"] == [{"session_id": "owned"}]
    assert calls == [(7, "owned", {"limit": 100}), (7, 25)]
    assert image.content == b"png-fixture"
    assert invalid_image.status_code == 400


def test_history_rejects_control_character_session_before_storage(monkeypatch) -> None:
    storage_called = False

    def unexpected_storage_call(*args):
        nonlocal storage_called
        storage_called = True
        return []

    monkeypatch.setattr(
        app_module.postgres_client,
        "get_history",
        unexpected_storage_call,
    )

    with _ready_client(monkeypatch) as client:
        response = client.get(
            "/api/chat/history/safe%0D%0Aforged-log?saas_user_id=7",
            headers=_headers(),
        )

    assert response.status_code == 422
    assert storage_called is False
