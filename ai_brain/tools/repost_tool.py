"""LangChain tool for a confirmed, idempotent Telegram repost workflow."""

import hashlib
import hmac
import importlib.util
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent.parent
logger = logging.getLogger(__name__)

_SUPPORTED_ENVIRONMENTS = {"development", "test", "staging", "production"}
_STRICT_ENVIRONMENTS = {"staging", "production"}
_SECRET_PLACEHOLDERS = ("change-me", "changeme", "your-secret", "test", "example")
_CHANNEL_USERNAME = re.compile(r"^[A-Za-z0-9_]{5,64}$")
_SIGNED_CHAT_ID = re.compile(r"^-?[1-9][0-9]{0,19}$")
_REPOST_FILENAME = re.compile(r"^forward_post_.+\.json$")
_MESSAGE_ID = re.compile(r"^[1-9][0-9]{0,9}$")
_CONFIRMATION_TOKEN = re.compile(r"^[0-9a-f]{64}$")
_IDEMPOTENCY_KEY = re.compile(r"^repost:[1-9][0-9]{0,18}:[0-9a-f]{64}$")
_MIN_CHAT_ID = -(2**63)
_MAX_CHAT_ID = 2**63 - 1
_MAX_MESSAGE_ID = 2**31 - 1


def _runtime_environment() -> str | None:
    """Return a supported deployment environment or fail closed with ``None``."""

    value = (
        (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV", "development"))
        .strip()
        .lower()
    )
    return value if value in _SUPPORTED_ENVIRONMENTS else None


def _normalize_tenant_id(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= _MAX_CHAT_ID else None


def _explicit_regular_file(variable: str, suffix: str) -> Path | None:
    """Resolve an operator-provided absolute, regular, non-symlink file."""

    configured = os.getenv(variable, "").strip()
    if not configured:
        return None
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute() or candidate.is_symlink():
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    if resolved.suffix.casefold() != suffix or not resolved.is_file():
        return None
    return resolved


def _explicit_directory(variable: str) -> Path | None:
    """Resolve an operator-provided absolute, non-symlink directory."""

    configured = os.getenv(variable, "").strip()
    if not configured:
        return None
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute() or candidate.is_symlink():
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_dir() else None


# RepostTool lives in a legacy module that is not present in every checkout.
# Staging deliberately has the same explicit integration boundary as production.
_IMPORT_ENVIRONMENT = _runtime_environment()
if _IMPORT_ENVIRONMENT in {*_STRICT_ENVIRONMENTS, "test"}:
    configured_tool_path = _explicit_regular_file("REPOST_TOOL_PATH", ".py")
    possible_paths = [configured_tool_path] if configured_tool_path else []
elif _IMPORT_ENVIRONMENT == "development":
    configured_tool_path = _explicit_regular_file("REPOST_TOOL_PATH", ".py")
    possible_paths = [
        configured_tool_path,
        BASE_DIR / "Чат бот" / "Repost_Tool.py",
        BASE_DIR / "chatbot" / "Repost_Tool.py",
        BASE_DIR / "Repost_Tool.py",
        Path("/app") / "Repost_Tool.py",
        Path("/app") / "chatbot" / "Repost_Tool.py",
    ]
else:
    # An unknown environment must not load even an explicitly supplied executor.
    possible_paths = []

RepostTool = None
REPOST_TOOL_PATH = None
for path in possible_paths:
    if path is None or path.is_symlink() or not path.is_file():
        continue
    REPOST_TOOL_PATH = path.resolve()
    sys.path.insert(0, str(path.parent))
    try:
        specification = importlib.util.spec_from_file_location(
            "_configured_repost_executor",
            REPOST_TOOL_PATH,
        )
        if specification is None or specification.loader is None:
            raise ImportError("Unable to create RepostTool module specification")
        repost_module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(repost_module)
        RepostTool = repost_module.RepostTool

        logger.info("RepostTool loaded")
        break
    except (AttributeError, ImportError):
        logger.warning("Unable to import RepostTool from an available module")

if RepostTool is None:
    logger.warning("RepostTool is unavailable; repost operations are disabled")


def _normalize_channel(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if not normalized.startswith("@") and normalized.lstrip("-").isdigit():
        if _SIGNED_CHAT_ID.fullmatch(normalized):
            numeric_id = int(normalized)
            if _MIN_CHAT_ID <= numeric_id <= _MAX_CHAT_ID:
                return str(numeric_id)
        return None
    username = normalized.removeprefix("@")
    if _CHANNEL_USERNAME.fullmatch(username):
        return f"@{username.casefold()}"
    return None


def _normalize_message_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1 <= value <= _MAX_MESSAGE_ID else None
    if not isinstance(value, str) or not _MESSAGE_ID.fullmatch(value):
        return None
    message_id = int(value)
    return message_id if message_id <= _MAX_MESSAGE_ID else None


def _operation_fingerprint(
    saas_user_id: int,
    source_channel: str,
    message_id: Any,
    target_channel: str,
) -> str:
    """Create a stable identity for the exact Telegram side effect."""
    payload = json.dumps(
        {
            "saas_user_id": saas_user_id,
            "source_channel": str(source_channel),
            "message_id": str(message_id),
            "target_channel": str(target_channel),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _confirmation_secret() -> str | None:
    secret = os.getenv("REPOST_CONFIRMATION_SECRET", "").strip()
    lowered = secret.lower()
    if (
        len(secret) < 32
        or len(set(secret)) < 8
        or any(marker in lowered for marker in _SECRET_PLACEHOLDERS)
    ):
        return None
    return secret


def _confirmation_token(
    saas_user_id: int,
    fingerprint: str,
    secret: str,
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        f"confirm-repost:v2:{saas_user_id}:{fingerprint}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _deterministic_idempotency_key(
    saas_user_id: int,
    fingerprint: str,
) -> str:
    return f"repost:{saas_user_id}:{fingerprint}"


def _idempotency_db_path() -> Path | None:
    configured = os.getenv("REPOST_IDEMPOTENCY_DB", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if (
            not candidate.is_absolute()
            or candidate.is_symlink()
            or candidate.parent.is_symlink()
        ):
            return None
        try:
            parent = candidate.parent.resolve(strict=True)
        except OSError:
            return None
        if not parent.is_dir():
            return None
        resolved = parent / candidate.name
        if resolved.exists() and not resolved.is_file():
            return None
        return resolved
    environment = _runtime_environment()
    if environment is None or environment in _STRICT_ENVIRONMENTS:
        return None
    return Path("/tmp/telegram-ai-repost-idempotency.sqlite3")


def _open_idempotency_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS repost_operations_v2 (
            saas_user_id INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            source_channel TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            target_channel TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('inflight', 'completed')),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (saas_user_id, idempotency_key)
        )
        """
    )
    connection.commit()
    return connection


def _reserve_operation(
    path: Path,
    *,
    saas_user_id: int,
    idempotency_key: str,
    fingerprint: str,
    source_channel: str,
    message_id: int,
    target_channel: str,
) -> tuple[bool, str]:
    """Atomically reserve an operation across processes and service restarts."""
    now = datetime.now(UTC).isoformat()
    with _open_idempotency_db(path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO repost_operations_v2
                    (saas_user_id, idempotency_key, fingerprint, source_channel,
                     message_id, target_channel, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'inflight', ?)
                """,
                (
                    saas_user_id,
                    idempotency_key,
                    fingerprint,
                    source_channel,
                    message_id,
                    target_channel,
                    now,
                ),
            )
            connection.commit()
            return True, "reserved"
        except sqlite3.IntegrityError:
            row = connection.execute(
                """
                SELECT status, fingerprint
                FROM repost_operations_v2
                WHERE saas_user_id = ? AND idempotency_key = ?
                """,
                (saas_user_id, idempotency_key),
            ).fetchone()
            if row and row[1] == fingerprint:
                return False, row[0]
            return False, "conflict"


def _complete_operation(
    path: Path,
    saas_user_id: int,
    idempotency_key: str,
) -> None:
    with _open_idempotency_db(path) as connection:
        connection.execute(
            """
            UPDATE repost_operations_v2
            SET status = 'completed', updated_at = ?
            WHERE saas_user_id = ? AND idempotency_key = ?
            """,
            (datetime.now(UTC).isoformat(), saas_user_id, idempotency_key),
        )
        connection.commit()


def _tenant_config_path(saas_user_id: int) -> Path | None:
    """Resolve only the current tenant's executor configuration."""

    configured = os.getenv("REPOST_CONFIG_DIR", "").strip()
    config_root = _explicit_directory("REPOST_CONFIG_DIR")
    if configured and config_root is None:
        return None
    if config_root is not None:
        candidate = config_root / f"{saas_user_id}.json"
        if candidate.is_symlink():
            return None
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if resolved.parent != config_root or not resolved.is_file():
            return None
        return resolved

    # Legacy single-config lookup is development-only. Staging, production,
    # and test fixtures must use the tenant-scoped directory contract above.
    if _runtime_environment() != "development":
        return None
    for path in (
        BASE_DIR / "Чат бот" / "config.json",
        BASE_DIR / "chatbot" / "config.json",
        BASE_DIR / "api" / "config.json",
        Path("/app") / "config.json",
        Path("/app") / "chatbot" / "config.json",
    ):
        if path.is_symlink() or not path.is_file():
            continue
        return path.resolve()
    return None


def _strict_executor_is_configured(saas_user_id: int) -> bool:
    environment = _runtime_environment()
    if environment is None:
        return False
    if environment not in _STRICT_ENVIRONMENTS:
        return True
    configured_tool = _explicit_regular_file("REPOST_TOOL_PATH", ".py")
    configured_input_root = _explicit_directory("REPOST_INPUT_DIR")
    configured_config_root = _explicit_directory("REPOST_CONFIG_DIR")
    configured_input_dir = _repost_input_dir(saas_user_id)
    configured_config = _tenant_config_path(saas_user_id)
    idempotency_path = _idempotency_db_path()
    return bool(
        configured_tool
        and configured_input_root
        and configured_config_root
        and configured_config
        and configured_input_dir
        and idempotency_path
        and _confirmation_secret()
        and REPOST_TOOL_PATH
        and configured_tool == REPOST_TOOL_PATH.resolve()
    )


def _repost_input_root() -> Path | None:
    configured = os.getenv("REPOST_INPUT_DIR", "").strip()
    configured_root = _explicit_directory("REPOST_INPUT_DIR")
    if configured and configured_root is None:
        return None
    if configured_root is not None:
        return configured_root
    if _runtime_environment() != "development":
        return None
    candidate = BASE_DIR / "parser_local" / "Logs"
    if candidate.is_symlink():
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_dir() else None


def _repost_input_dir(saas_user_id: int) -> Path | None:
    """Resolve the current tenant's input directory without cross-tenant fallback."""

    input_root = _repost_input_root()
    if input_root is None:
        return None
    candidate = input_root / str(saas_user_id)
    if not candidate.is_symlink():
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            resolved = None
        if resolved and resolved.parent == input_root and resolved.is_dir():
            return resolved

    # Preserve the historical flat parser directory only for an unconfigured
    # local development checkout. Explicit roots are always tenant-scoped.
    if (
        _runtime_environment() == "development"
        and not os.getenv("REPOST_INPUT_DIR", "").strip()
    ):
        return input_root
    return None


def _is_allowed_repost_file(candidate: Path, input_dir: Path) -> bool:
    if candidate.name != str(candidate) or not _REPOST_FILENAME.fullmatch(
        candidate.name
    ):
        return False
    confined = input_dir / candidate.name
    if confined.is_symlink():
        return False
    try:
        resolved = confined.resolve(strict=True)
    except OSError:
        return False
    return resolved.parent == input_dir and resolved.is_file()


def _resolve_json_path(
    saas_user_id: int,
    json_path: str | None,
    source_channel: str | None,
) -> Path | None:
    parser_logs_dir = _repost_input_dir(saas_user_id)
    if parser_logs_dir is None:
        return None

    if json_path:
        candidate = Path(json_path)
        if candidate.is_absolute() or not _is_allowed_repost_file(
            candidate, parser_logs_dir
        ):
            return None
        return (parser_logs_dir / candidate.name).resolve()

    candidates = sorted(
        (
            candidate
            for candidate in parser_logs_dir.glob("forward_post_*.json")
            if _is_allowed_repost_file(Path(candidate.name), parser_logs_dir)
        ),
        key=lambda candidate: (candidate.stat().st_mtime_ns, candidate.name),
        reverse=True,
    )
    if not source_channel:
        return candidates[0].resolve() if candidates else None

    expected = source_channel.lstrip("@").casefold()
    for candidate in candidates:
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            actual = str(data.get("forward_post", {}).get("source_channel", ""))
            if actual.lstrip("@").casefold() == expected:
                return candidate.resolve()
        except (OSError, ValueError, TypeError):
            continue
    # Never silently choose a post from a different channel.
    return None


async def _execute_repost_impl(
    saas_user_id: int,
    json_path: str | None = None,
    target_channel: str | None = None,
    dry_run: bool = True,
    chat_id: str | None = None,
    channel_username: str | None = None,
    confirmed: bool = False,
    confirmation_token: str | None = None,
    idempotency_key: str | None = None,
) -> str:
    """Preview a repost by default; execute only after structured confirmation."""
    tenant_id = _normalize_tenant_id(saas_user_id)
    if tenant_id is None:
        return "Ошибка: некорректный saas_user_id; операция не выполнена."
    if _runtime_environment() is None:
        return "Ошибка: неподдерживаемый ENVIRONMENT/APP_ENV; операция не выполнена."
    if not _strict_executor_is_configured(tenant_id):
        return (
            "Ошибка: staging/production repost executor не настроен; "
            "операция не выполнена."
        )
    if RepostTool is None:
        return "Ошибка: RepostTool недоступен; операция не выполнена."

    try:
        logger.info(
            "Repost tool invoked tenant=%s dry_run=%s confirmed=%s",
            tenant_id,
            dry_run,
            confirmed,
        )
        source_channel = _normalize_channel(channel_username)
        if channel_username is not None and source_channel is None:
            return "Ошибка: некорректный channel_username; операция не выполнена."

        chat_id_text = str(chat_id).strip() if chat_id is not None else None
        normalized_chat_id = _normalize_channel(chat_id_text)
        if not source_channel and chat_id_text and chat_id_text.startswith("@"):
            source_channel = normalized_chat_id

        effective_target = _normalize_channel(target_channel)
        if target_channel is not None and effective_target is None:
            return "Ошибка: некорректный target_channel; операция не выполнена."
        if effective_target is None:
            effective_target = normalized_chat_id
        if target_channel is None and chat_id is not None and effective_target is None:
            return "Ошибка: некорректный chat_id; операция не выполнена."

        json_file_path = _resolve_json_path(tenant_id, json_path, source_channel)
        if json_file_path is None or not json_file_path.is_file():
            return (
                "Ошибка: не найден однозначный JSON для указанного канала; "
                "операция не выполнена."
            )

        # Resolve tenant-owned input and config before constructing the private
        # executor. No other tenant's filesystem objects reach this boundary.
        config_path = _tenant_config_path(tenant_id)
        try:
            if config_path is not None:
                tool_instance = RepostTool(config_file=str(config_path))
            else:
                tool_instance = RepostTool()
        except Exception:
            logger.error("Ошибка инициализации RepostTool", exc_info=True)
            return "Ошибка инициализации RepostTool; операция не выполнена."

        try:
            forward_data = tool_instance.load_forward_data(json_file_path)
            forward_post = forward_data.get("forward_post", {})
            post_info = forward_data.get("post_info", {})
            if effective_target:
                forward_post["target_channel"] = effective_target

            source_channel_final = _normalize_channel(
                forward_post.get("source_channel")
                or forward_post.get("source_channel_id")
            )
            message_id = _normalize_message_id(forward_post.get("message_id"))
            effective_target = _normalize_channel(
                effective_target or forward_post.get("target_channel")
            )
        except Exception:
            logger.error("Ошибка загрузки repost JSON", exc_info=True)
            return "Ошибка загрузки repost JSON; операция не выполнена."

        if not source_channel_final or message_id is None or not effective_target:
            return (
                "Ошибка: source_channel, message_id и target_channel обязательны; "
                "операция не выполнена."
            )
        if source_channel and (
            source_channel.lstrip("@").casefold()
            != source_channel_final.lstrip("@").casefold()
        ):
            return (
                "Отказ: канал-источник в JSON не совпадает с запрошенным; "
                "операция не выполнена."
            )

        fingerprint = _operation_fingerprint(
            tenant_id,
            source_channel_final,
            message_id,
            effective_target,
        )
        expected_idempotency_key = _deterministic_idempotency_key(
            tenant_id,
            fingerprint,
        )
        secret = _confirmation_secret()
        expected_confirmation = (
            _confirmation_token(tenant_id, fingerprint, secret) if secret else None
        )

        if dry_run:
            await tool_instance.run(
                json_path=json_file_path,
                target_channel=effective_target,
                dry_run=True,
            )
            lines = [
                "✅ DRY RUN: проверка выполнена, Telegram не изменён.",
                f"Tenant ID: {tenant_id}",
                f"Из: {source_channel_final}",
                f"В: {effective_target}",
                f"Message ID: {message_id}",
                f"URL: {post_info.get('url', 'N/A')}",
                f"idempotency_key: {expected_idempotency_key}",
            ]
            if expected_confirmation:
                lines.extend(
                    (
                        f"confirmation_token: {expected_confirmation}",
                        "Для реального репоста нужно отдельно передать dry_run=false, "
                        "confirmed=true и оба точных значения выше.",
                    )
                )
            else:
                lines.append(
                    "Реальный репост отключён: REPOST_CONFIRMATION_SECRET не настроен."
                )
            return "\n".join(lines)

        if not confirmed:
            return "Отказ: требуется явное confirmed=true после dry run."
        if not secret or not expected_confirmation:
            return (
                "Отказ: боевой repost отключён до настройки REPOST_CONFIRMATION_SECRET."
            )
        if (
            not isinstance(confirmation_token, str)
            or not _CONFIRMATION_TOKEN.fullmatch(confirmation_token)
            or not hmac.compare_digest(confirmation_token, expected_confirmation)
        ):
            return "Отказ: confirmation_token не соответствует dry-run операции."
        if (
            not isinstance(idempotency_key, str)
            or not _IDEMPOTENCY_KEY.fullmatch(idempotency_key)
            or not hmac.compare_digest(idempotency_key, expected_idempotency_key)
        ):
            return "Отказ: требуется точный idempotency_key из dry run."

        idempotency_path = _idempotency_db_path()
        if idempotency_path is None:
            return (
                "Отказ: в staging/production требуется постоянный "
                "REPOST_IDEMPOTENCY_DB."
            )
        reserved, existing_status = _reserve_operation(
            idempotency_path,
            saas_user_id=tenant_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            source_channel=source_channel_final,
            message_id=message_id,
            target_channel=effective_target,
        )
        if not reserved:
            return (
                "Отказ: repost-операция уже зарезервирована или выполнена "
                f"(status={existing_status}); повтор заблокирован."
            )
        try:
            await tool_instance.run(
                json_path=json_file_path,
                target_channel=effective_target,
                dry_run=False,
            )
            _complete_operation(idempotency_path, tenant_id, idempotency_key)
            logger.info(
                "Confirmed repost completed tenant=%s operation=%s",
                tenant_id,
                fingerprint[:12],
            )
            return (
                "✅ Репост выполнен один раз.\n"
                f"Пост {message_id}: {source_channel_final} -> {effective_target}\n"
                f"idempotency_key: {idempotency_key}"
            )
        except Exception:
            logger.error("Ошибка выполнения confirmed repost", exc_info=True)
            return (
                "Ошибка или неопределённый результ репоста; "
                "автоматический повтор заблокирован до ручной сверки."
            )

    except Exception:
        logger.error("Критическая ошибка в execute_repost", exc_info=True)
        return "Критическая ошибка repost workflow; операция остановлена."


@tool
async def execute_repost(
    saas_user_id: int,
    json_path: str | None = None,
    target_channel: str | None = None,
    dry_run: bool = True,
    chat_id: str | None = None,
    channel_username: str | None = None,
    confirmed: bool = False,
    confirmation_token: str | None = None,
    idempotency_key: str | None = None,
) -> str:
    """Safely preview or execute a Telegram repost.

    ``saas_user_id`` must come from the authenticated tenant context. The
    default is always a dry run. A real repost requires a second call with
    ``dry_run=false``, ``confirmed=true``, and the exact confirmation token and
    idempotency key returned by the matching dry run. Conversational phrases are
    never confirmation.
    """
    return await _execute_repost_impl(
        saas_user_id=saas_user_id,
        json_path=json_path,
        target_channel=target_channel,
        dry_run=dry_run,
        chat_id=chat_id,
        channel_username=channel_username,
        confirmed=confirmed,
        confirmation_token=confirmation_token,
        idempotency_key=idempotency_key,
    )
