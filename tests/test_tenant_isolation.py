from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from langchain_core.messages import AIMessage, HumanMessage, message_to_dict

from ai_brain.clients.postgres_client import PostgresClient, tenant_session_uuid
from ai_brain.config import settings


def test_same_session_is_isolated_between_tenants() -> None:
    assert tenant_session_uuid(1, "shared") != tenant_session_uuid(2, "shared")


def test_storage_key_is_stable() -> None:
    assert tenant_session_uuid(42, "session-a") == tenant_session_uuid(42, "session-a")


@pytest.mark.parametrize("tenant_id", [0, -1])
def test_invalid_tenant_is_rejected(tenant_id: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        tenant_session_uuid(tenant_id, "session")


def test_blank_session_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        tenant_session_uuid(1, "  ")


def test_history_query_is_bounded_in_sql_and_restores_chronological_order() -> None:
    older_at = datetime(2026, 1, 1, tzinfo=UTC)
    newer_at = datetime(2026, 1, 2, tzinfo=UTC)

    class FakeConnection:
        def __init__(self) -> None:
            self.query = ""
            self.params = ()

        def execute(self, query, params):
            self.query = str(query)
            self.params = params
            return self

        def fetchall(self):
            return [
                (41, message_to_dict(HumanMessage(content="older")), older_at, 7),
                (42, message_to_dict(AIMessage(content="newer")), newer_at, 7),
            ]

    class FakePool:
        def __init__(self) -> None:
            self.connection_value = FakeConnection()

        @contextmanager
        def connection(self):
            yield self.connection_value

    client = PostgresClient("postgresql://unused")
    pool = FakePool()
    client._pool = pool  # type: ignore[assignment]
    client._schema_ready = True

    page = client.get_history(7, "bounded", limit=2)

    normalized_query = " ".join(pool.connection_value.query.split())
    assert "COUNT(*) OVER () AS total" in normalized_query
    assert "ORDER BY id DESC LIMIT %s" in normalized_query
    assert "ORDER BY recent.id ASC" in normalized_query
    assert pool.connection_value.params[0] == client._storage_session_id(7, "bounded")
    assert pool.connection_value.params[1] == 2
    assert [record.id for record in page.records] == [41, 42]
    assert [record.created_at for record in page.records] == [older_at, newer_at]
    assert [record.message.content for record in page.records] == ["older", "newer"]
    assert page.returned_count == 2
    assert page.total == 7


def test_persisted_message_id_is_stable_across_different_limits() -> None:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    stored_rows = [
        (
            row_id,
            message_to_dict(HumanMessage(content=f"message-{row_id}")),
            created_at,
            3,
        )
        for row_id in (101, 102, 103)
    ]

    class FakeConnection:
        def __init__(self) -> None:
            self.params_seen: list[tuple] = []
            self.limit = 0

        def execute(self, _query, params):
            self.params_seen.append(params)
            self.limit = params[1]
            return self

        def fetchall(self):
            return stored_rows[-self.limit :]

    class FakePool:
        def __init__(self) -> None:
            self.connection_value = FakeConnection()

        @contextmanager
        def connection(self):
            yield self.connection_value

    client = PostgresClient("postgresql://unused")
    pool = FakePool()
    client._pool = pool  # type: ignore[assignment]
    client._schema_ready = True

    one_message = client.get_history(19, "stable", limit=1)
    two_messages = client.get_history(19, "stable", limit=2)

    assert one_message.records[0].id == 103
    assert two_messages.records[-1].id == 103
    expected_storage_id = client._storage_session_id(19, "stable")
    assert all(
        params[0] == expected_storage_id for params in pool.connection_value.params_seen
    )


@pytest.mark.parametrize("limit", [0, -1, settings.API_HISTORY_MAX_LIMIT + 1])
def test_history_query_rejects_unbounded_limits(limit: int) -> None:
    client = PostgresClient("postgresql://unused")

    with pytest.raises(ValueError, match="limit must be between"):
        client.get_history(7, "bounded", limit=limit)
