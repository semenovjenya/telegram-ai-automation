"""Tenant-safe PostgreSQL persistence for AI-BRAIN conversations."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    message_to_dict,
    messages_from_dict,
)
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ..config import settings

logger = logging.getLogger(__name__)

HISTORY_TABLE = "chat_message_history"
SESSIONS_TABLE = "ai_brain_sessions"


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    """One persisted history row with storage-owned identity and timestamp."""

    id: int
    message: BaseMessage
    created_at: datetime


@dataclass(frozen=True, slots=True)
class HistoryPage:
    """A bounded recent history slice plus the full session row count."""

    records: tuple[HistoryRecord, ...]
    total: int

    @property
    def returned_count(self) -> int:
        return len(self.records)


def string_to_uuid(text: str) -> str:
    """Convert arbitrary text to a stable UUID5 string."""

    return str(uuid.uuid5(uuid.NAMESPACE_URL, text))


def tenant_session_uuid(saas_user_id: int, session_id: str) -> str:
    """Return a storage key namespaced by tenant.

    The same public session id used by two tenants must never address the same
    database history or LangGraph thread.
    """

    if saas_user_id <= 0:
        raise ValueError("saas_user_id must be positive")
    normalized_session_id = session_id.strip()
    if not normalized_session_id:
        raise ValueError("session_id cannot be empty")
    return string_to_uuid(f"tenant:{saas_user_id}:session:{normalized_session_id}")


class PostgresClient:
    """Pooled, tenant-safe persistence for LangChain-compatible messages."""

    def __init__(
        self,
        connection_string: str | None = None,
        *,
        min_size: int | None = None,
        max_size: int | None = None,
    ) -> None:
        self.connection_string = (
            connection_string or settings.postgres_connection_string
        )
        self._min_size = min_size or settings.DB_POOL_MIN_SIZE
        self._max_size = max_size or settings.DB_POOL_MAX_SIZE
        self._pool: ConnectionPool | None = None
        self._pool_lock = threading.Lock()
        self._schema_lock = threading.Lock()
        self._schema_ready = False

    def _get_pool(self) -> ConnectionPool:
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:
                    self._pool = ConnectionPool(
                        self.connection_string,
                        min_size=self._min_size,
                        max_size=self._max_size,
                        kwargs={"autocommit": True},
                        open=False,
                        name="ai-brain-history",
                    )
                    self._pool.open(wait=True)
        return self._pool

    def ensure_schema(self) -> None:
        """Create library and application-owned tables exactly once."""

        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with self._get_pool().connection() as conn:
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
                        id BIGSERIAL PRIMARY KEY,
                        session_id UUID NOT NULL,
                        message JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                conn.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{HISTORY_TABLE}_session_id
                    ON {HISTORY_TABLE} (session_id, id)
                    """
                )
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {SESSIONS_TABLE} (
                        saas_user_id BIGINT NOT NULL,
                        session_id TEXT NOT NULL,
                        storage_session_id UUID NOT NULL UNIQUE,
                        chat_id TEXT,
                        channel_username TEXT,
                        last_message TEXT,
                        last_message_role TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (saas_user_id, session_id)
                    )
                    """
                )
                conn.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{SESSIONS_TABLE}_tenant_updated
                    ON {SESSIONS_TABLE} (saas_user_id, updated_at DESC)
                    """
                )
            self._schema_ready = True
            logger.info("AI-BRAIN persistence schema is ready")

    @staticmethod
    def _storage_session_id(saas_user_id: int, session_id: str) -> uuid.UUID:
        return uuid.UUID(tenant_session_uuid(saas_user_id, session_id))

    def _add_message(
        self,
        conn: Any,
        saas_user_id: int,
        session_id: str,
        message: BaseMessage,
    ) -> None:
        conn.execute(
            f"INSERT INTO {HISTORY_TABLE} (session_id, message) VALUES (%s, %s)",
            (
                self._storage_session_id(saas_user_id, session_id),
                Jsonb(message_to_dict(message)),
            ),
        )

    def _upsert_session(
        self,
        conn: Any,
        *,
        saas_user_id: int,
        session_id: str,
        message: str,
        role: str,
        chat_id: str | int | None = None,
        channel_username: str | None = None,
    ) -> None:
        conn.execute(
            f"""
            INSERT INTO {SESSIONS_TABLE} (
                saas_user_id,
                session_id,
                storage_session_id,
                chat_id,
                channel_username,
                last_message,
                last_message_role
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (saas_user_id, session_id) DO UPDATE SET
                chat_id = COALESCE(EXCLUDED.chat_id, {SESSIONS_TABLE}.chat_id),
                channel_username = COALESCE(
                    EXCLUDED.channel_username,
                    {SESSIONS_TABLE}.channel_username
                ),
                last_message = EXCLUDED.last_message,
                last_message_role = EXCLUDED.last_message_role,
                updated_at = NOW()
            """,
            (
                saas_user_id,
                session_id,
                tenant_session_uuid(saas_user_id, session_id),
                str(chat_id) if chat_id is not None else None,
                channel_username,
                message[:2000],
                role,
            ),
        )

    def get_history(
        self,
        saas_user_id: int,
        session_id: str,
        *,
        limit: int,
    ) -> HistoryPage:
        """Return recent persisted records in chronological order.

        The window count and bounded rows come from one PostgreSQL statement,
        so ``total`` describes the same snapshot as the returned records.
        """

        if not 1 <= limit <= settings.API_HISTORY_MAX_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {settings.API_HISTORY_MAX_LIMIT}"
            )
        self.ensure_schema()
        with self._get_pool().connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    recent.id,
                    recent.message,
                    recent.created_at,
                    recent.total
                FROM (
                    SELECT
                        id,
                        message,
                        created_at,
                        COUNT(*) OVER () AS total
                    FROM {HISTORY_TABLE}
                    WHERE session_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                ) AS recent
                ORDER BY recent.id ASC
                """,
                (self._storage_session_id(saas_user_id, session_id), limit),
            ).fetchall()
        messages = messages_from_dict([row[1] for row in rows])
        records = tuple(
            HistoryRecord(id=row[0], message=message, created_at=row[2])
            for row, message in zip(rows, messages, strict=True)
        )
        page = HistoryPage(records=records, total=int(rows[0][3]) if rows else 0)
        logger.info(
            "Retrieved %s of %s messages for tenant=%s session=%s",
            page.returned_count,
            page.total,
            saas_user_id,
            session_id,
        )
        return page

    def get_messages(
        self,
        saas_user_id: int,
        session_id: str,
        *,
        limit: int,
    ) -> list[BaseMessage]:
        """Return LangChain messages for model memory without DB metadata."""

        return [
            record.message
            for record in self.get_history(
                saas_user_id,
                session_id,
                limit=limit,
            ).records
        ]

    def add_user_message(
        self,
        saas_user_id: int,
        session_id: str,
        message: str,
        *,
        chat_id: str | int | None = None,
        channel_username: str | None = None,
    ) -> None:
        self.ensure_schema()
        with self._get_pool().connection() as conn:
            with conn.transaction():
                self._add_message(
                    conn,
                    saas_user_id,
                    session_id,
                    HumanMessage(
                        content=message,
                        additional_kwargs={"timestamp": datetime.now(UTC).isoformat()},
                    ),
                )
                self._upsert_session(
                    conn,
                    saas_user_id=saas_user_id,
                    session_id=session_id,
                    message=message,
                    role="user",
                    chat_id=chat_id,
                    channel_username=channel_username,
                )

    def add_ai_message(
        self,
        saas_user_id: int,
        session_id: str,
        message: str,
        *,
        chat_id: str | int | None = None,
        channel_username: str | None = None,
    ) -> None:
        self.ensure_schema()
        with self._get_pool().connection() as conn:
            with conn.transaction():
                self._add_message(
                    conn,
                    saas_user_id,
                    session_id,
                    AIMessage(
                        content=message,
                        additional_kwargs={"timestamp": datetime.now(UTC).isoformat()},
                    ),
                )
                self._upsert_session(
                    conn,
                    saas_user_id=saas_user_id,
                    session_id=session_id,
                    message=message,
                    role="assistant",
                    chat_id=chat_id,
                    channel_username=channel_username,
                )

    def list_sessions(
        self, saas_user_id: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._get_pool().connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    session_id,
                    chat_id,
                    channel_username,
                    last_message,
                    last_message_role,
                    created_at,
                    updated_at
                FROM {SESSIONS_TABLE}
                WHERE saas_user_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (saas_user_id, limit),
            ).fetchall()
        return [
            {
                "session_id": row[0],
                "chat_id": row[1],
                "channel_username": row[2],
                "last_message": row[3],
                "last_message_role": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
            for row in rows
        ]

    def ping(self) -> bool:
        try:
            with self._get_pool().connection() as conn:
                return conn.execute("SELECT 1").fetchone() == (1,)
        except Exception:
            logger.exception("PostgreSQL readiness check failed")
            return False

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None
            self._schema_ready = False


postgres_client = PostgresClient()
