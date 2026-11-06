"""Security regression tests for the two-phase repost workflow."""

import asyncio
import importlib.util
import json
import os
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIRMATION_SECRET = "repost-confirmation-secret-0123456789-ABCDEF"
TENANT_ID = 7


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "security_repost_tool",
        ROOT / "ai_brain" / "tools" / "repost_tool.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _value(result: str, name: str) -> str:
    prefix = f"{name}: "
    return next(
        line[len(prefix) :] for line in result.splitlines() if line.startswith(prefix)
    )


async def _execute(module, *, saas_user_id: int = TENANT_ID, **kwargs) -> str:
    return await module._execute_repost_impl(
        saas_user_id=saas_user_id,
        **kwargs,
    )


def _fixture_file(
    tmp_path: Path,
    monkeypatch,
    *,
    tenant_id: int = TENANT_ID,
    filename: str = "forward_post_fixture.json",
) -> Path:
    input_root = tmp_path / "repost-input"
    input_dir = input_root / str(tenant_id)
    input_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REPOST_INPUT_DIR", str(input_root))
    path = input_dir / filename
    path.write_text(
        json.dumps(
            {
                "forward_post": {
                    "source_channel": "@source",
                    "target_channel": "@target",
                    "message_id": 42,
                },
                "post_info": {"url": "https://t.me/source/42"},
            }
        ),
        encoding="utf-8",
    )
    return path


def _configure_strict_executor(
    module,
    tmp_path: Path,
    monkeypatch,
    *,
    tenant_id: int = TENANT_ID,
    include_idempotency_store: bool = True,
) -> Path:
    tool_path = tmp_path / "Repost_Tool.py"
    config_root = tmp_path / "repost-config"
    config_root.mkdir(exist_ok=True)
    config_path = config_root / f"{tenant_id}.json"
    tool_path.write_text("# operator-managed executor fixture\n", encoding="utf-8")
    config_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("REPOST_TOOL_PATH", str(tool_path))
    monkeypatch.setenv("REPOST_CONFIG_DIR", str(config_root))
    if include_idempotency_store:
        monkeypatch.setenv(
            "REPOST_IDEMPOTENCY_DB",
            str(tmp_path / "operations.sqlite3"),
        )
    monkeypatch.setattr(module, "REPOST_TOOL_PATH", tool_path.resolve())
    return config_path


def _install_fake_tool(module, monkeypatch, *, fail_live: bool = False):
    calls = []

    class FakeRepostTool:
        def __init__(self, *args, **kwargs):
            pass

        def load_forward_data(self, json_path):
            return json.loads(Path(json_path).read_text(encoding="utf-8"))

        async def run(self, **kwargs):
            calls.append(kwargs)
            if fail_live and kwargs["dry_run"] is False:
                raise RuntimeError("ambiguous network failure")

    monkeypatch.setattr(module, "RepostTool", FakeRepostTool)
    return calls


def test_repost_defaults_to_dry_run(tmp_path, monkeypatch) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    monkeypatch.setenv("REPOST_CONFIRMATION_SECRET", CONFIRMATION_SECRET)
    monkeypatch.setenv("REPOST_IDEMPOTENCY_DB", str(tmp_path / "operations.sqlite3"))

    result = asyncio.run(
        _execute(
            module,
            json_path=fixture.name,
            target_channel="@target",
        )
    )

    assert "DRY RUN" in result
    assert "confirmation_token:" in result
    assert "idempotency_key:" in result
    assert [call["dry_run"] for call in calls] == [True]


def test_live_repost_requires_explicit_confirmation(tmp_path, monkeypatch) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    monkeypatch.setenv("REPOST_CONFIRMATION_SECRET", CONFIRMATION_SECRET)

    result = asyncio.run(
        _execute(
            module,
            json_path=fixture.name,
            target_channel="@target",
            dry_run=False,
        )
    )

    assert "confirmed=true" in result
    assert calls == []


def test_confirmation_is_bound_and_execution_is_idempotent(
    tmp_path, monkeypatch
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    monkeypatch.setenv("REPOST_CONFIRMATION_SECRET", CONFIRMATION_SECRET)
    monkeypatch.setenv("REPOST_IDEMPOTENCY_DB", str(tmp_path / "operations.sqlite3"))

    preview = asyncio.run(
        _execute(
            module,
            json_path=fixture.name,
            target_channel="@target",
        )
    )
    confirmation_token = _value(preview, "confirmation_token")
    idempotency_key = _value(preview, "idempotency_key")

    live_arguments = {
        "json_path": fixture.name,
        "target_channel": "@target",
        "dry_run": False,
        "confirmed": True,
        "confirmation_token": confirmation_token,
        "idempotency_key": idempotency_key,
    }
    first = asyncio.run(_execute(module, **live_arguments))
    duplicate = asyncio.run(_execute(module, **live_arguments))

    assert "выполнен один раз" in first
    assert "повтор заблокирован" in duplicate
    assert [call["dry_run"] for call in calls] == [True, False]

    changed_target = asyncio.run(
        _execute(
            module,
            **{**live_arguments, "target_channel": "@somewhere_else"},
        )
    )
    assert "confirmation_token" in changed_target
    assert [call["dry_run"] for call in calls] == [True, False]


def test_confirmation_and_audit_record_are_bound_to_tenant(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    tenant_eight_fixture = _fixture_file(
        tmp_path,
        monkeypatch,
        tenant_id=8,
        filename=fixture.name,
    )
    database_path = tmp_path / "operations.sqlite3"
    monkeypatch.setenv("REPOST_CONFIRMATION_SECRET", CONFIRMATION_SECRET)
    monkeypatch.setenv("REPOST_IDEMPOTENCY_DB", str(database_path))

    tenant_seven_preview = asyncio.run(
        _execute(
            module, saas_user_id=7, json_path=fixture.name, target_channel="@target"
        )
    )
    tenant_eight_preview = asyncio.run(
        _execute(
            module,
            saas_user_id=8,
            json_path=tenant_eight_fixture.name,
            target_channel="@target",
        )
    )

    tenant_seven_token = _value(tenant_seven_preview, "confirmation_token")
    tenant_seven_key = _value(tenant_seven_preview, "idempotency_key")
    assert tenant_seven_token != _value(tenant_eight_preview, "confirmation_token")
    assert tenant_seven_key != _value(tenant_eight_preview, "idempotency_key")
    assert tenant_seven_key.startswith("repost:7:")
    assert _value(tenant_eight_preview, "idempotency_key").startswith("repost:8:")

    cross_tenant_attempt = asyncio.run(
        _execute(
            module,
            saas_user_id=8,
            json_path=tenant_eight_fixture.name,
            target_channel="@target",
            dry_run=False,
            confirmed=True,
            confirmation_token=tenant_seven_token,
            idempotency_key=tenant_seven_key,
        )
    )
    assert "confirmation_token" in cross_tenant_attempt

    authorized_execution = asyncio.run(
        _execute(
            module,
            saas_user_id=7,
            json_path=fixture.name,
            target_channel="@target",
            dry_run=False,
            confirmed=True,
            confirmation_token=tenant_seven_token,
            idempotency_key=tenant_seven_key,
        )
    )
    assert "выполнен один раз" in authorized_execution
    assert [call["dry_run"] for call in calls] == [True, True, False]

    with sqlite3.connect(database_path) as connection:
        audit_row = connection.execute(
            """
            SELECT saas_user_id, idempotency_key, source_channel, message_id,
                   target_channel, status
            FROM repost_operations_v2
            """
        ).fetchone()
    assert audit_row == (
        7,
        tenant_seven_key,
        "@source",
        42,
        "@target",
        "completed",
    )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_strict_environments_require_persistent_idempotency_store(
    tmp_path,
    monkeypatch,
    environment,
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    monkeypatch.setenv("REPOST_CONFIRMATION_SECRET", CONFIRMATION_SECRET)
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("REPOST_IDEMPOTENCY_DB", raising=False)
    _configure_strict_executor(
        module,
        tmp_path,
        monkeypatch,
        include_idempotency_store=False,
    )

    result = asyncio.run(
        _execute(
            module,
            json_path=fixture.name,
            target_channel="@target",
        )
    )

    assert module._idempotency_db_path() is None
    assert "staging/production repost executor не настроен" in result
    assert calls == []


def test_ambiguous_live_failure_is_not_automatically_retried(
    tmp_path, monkeypatch
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch, fail_live=True)
    fixture = _fixture_file(tmp_path, monkeypatch)
    monkeypatch.setenv("REPOST_CONFIRMATION_SECRET", CONFIRMATION_SECRET)
    monkeypatch.setenv("REPOST_IDEMPOTENCY_DB", str(tmp_path / "operations.sqlite3"))

    preview = asyncio.run(
        _execute(module, json_path=fixture.name, target_channel="@target")
    )
    arguments = {
        "json_path": fixture.name,
        "target_channel": "@target",
        "dry_run": False,
        "confirmed": True,
        "confirmation_token": _value(preview, "confirmation_token"),
        "idempotency_key": _value(preview, "idempotency_key"),
    }
    failed = asyncio.run(_execute(module, **arguments))
    retry = asyncio.run(_execute(module, **arguments))

    assert "ручной сверки" in failed
    assert "повтор заблокирован" in retry
    assert [call["dry_run"] for call in calls] == [True, False]


def test_explicit_json_cannot_override_requested_source_channel(
    tmp_path, monkeypatch
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)

    result = asyncio.run(
        _execute(
            module,
            json_path=fixture.name,
            channel_username="different_source",
            target_channel="@target",
        )
    )

    assert "не совпадает" in result
    assert calls == []


@pytest.mark.parametrize(
    "untrusted_path",
    [
        "ABSOLUTE",
        "../forward_post_escape.json",
        "forward_post_link.json",
        "payload.json",
    ],
)
def test_repost_json_is_confined_to_regular_named_input_file(
    tmp_path,
    monkeypatch,
    untrusted_path,
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)

    outside = tmp_path / "forward_post_escape.json"
    outside.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    link = fixture.parent / "forward_post_link.json"
    link.symlink_to(outside)
    wrong_name = fixture.parent / "payload.json"
    wrong_name.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    supplied = str(fixture) if untrusted_path == "ABSOLUTE" else untrusted_path
    result = asyncio.run(
        _execute(
            module,
            json_path=supplied,
            target_channel="@target",
        )
    )

    assert "не найден однозначный JSON" in result
    assert calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_channel", "bad-name"),
        ("target_channel", "@abc"),
        ("target_channel", "0"),
        ("target_channel", "123456789012345678901"),
        ("channel_username", "source\nforged"),
        ("channel_username", "@abc"),
    ],
)
def test_repost_rejects_noncanonical_channels(
    tmp_path,
    monkeypatch,
    field,
    value,
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    arguments = {"json_path": fixture.name, "target_channel": "@target"}
    arguments[field] = value

    result = asyncio.run(_execute(module, **arguments))

    assert "некорректный" in result
    assert calls == []


@pytest.mark.parametrize("chat_id", ["chat-id", "0", "-0", "9" * 21])
def test_repost_rejects_unbounded_or_non_numeric_chat_id(
    tmp_path,
    monkeypatch,
    chat_id,
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)

    result = asyncio.run(
        _execute(
            module,
            json_path=fixture.name,
            chat_id=chat_id,
        )
    )

    assert "некорректный chat_id" in result
    assert calls == []


def test_repost_accepts_bounded_signed_numeric_chat_id(tmp_path, monkeypatch) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)

    result = asyncio.run(
        _execute(
            module,
            json_path=fixture.name,
            chat_id="-1001234567890",
        )
    )

    assert "DRY RUN" in result
    assert calls[0]["target_channel"] == "-1001234567890"


def test_production_repost_executor_requires_explicit_tool_and_config(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("REPOST_TOOL_PATH", raising=False)
    monkeypatch.delenv("REPOST_CONFIG_DIR", raising=False)

    result = asyncio.run(
        _execute(
            module,
            json_path=fixture.name,
            target_channel="@target",
        )
    )

    assert "production repost executor не настроен" in result
    assert calls == []


def test_staging_repost_executor_requires_explicit_tool_and_config(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("REPOST_TOOL_PATH", raising=False)
    monkeypatch.delenv("REPOST_CONFIG_DIR", raising=False)
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)

    result = asyncio.run(
        _execute(module, json_path=fixture.name, target_channel="@target")
    )

    assert "staging/production repost executor не настроен" in result
    assert calls == []


def test_strict_executor_confines_input_and_config_to_current_tenant(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    fixture = _fixture_file(tmp_path, monkeypatch, tenant_id=7)
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("REPOST_CONFIRMATION_SECRET", CONFIRMATION_SECRET)
    tenant_seven_config = _configure_strict_executor(
        module,
        tmp_path,
        monkeypatch,
        tenant_id=7,
    )

    constructed_with = []
    runs = []

    class FakeRepostTool:
        def __init__(self, *, config_file):
            constructed_with.append(Path(config_file))

        def load_forward_data(self, json_path):
            return json.loads(Path(json_path).read_text(encoding="utf-8"))

        async def run(self, **kwargs):
            runs.append(kwargs)

    monkeypatch.setattr(module, "RepostTool", FakeRepostTool)

    tenant_seven_preview = asyncio.run(
        _execute(
            module,
            saas_user_id=7,
            json_path=fixture.name,
            target_channel="@target",
        )
    )
    assert "DRY RUN" in tenant_seven_preview
    assert constructed_with == [tenant_seven_config.resolve()]
    assert Path(runs[0]["json_path"]).parent.name == "7"

    input_root = Path(os.environ["REPOST_INPUT_DIR"])
    tenant_eight_input = input_root / "8"
    tenant_eight_input.symlink_to(input_root / "7", target_is_directory=True)
    tenant_eight_config = tenant_seven_config.parent / "8.json"
    tenant_eight_config.write_text("{}\n", encoding="utf-8")

    cross_tenant_input = asyncio.run(
        _execute(
            module,
            saas_user_id=8,
            json_path=fixture.name,
            target_channel="@target",
        )
    )
    assert "staging/production repost executor не настроен" in cross_tenant_input
    assert constructed_with == [tenant_seven_config.resolve()]
    assert len(runs) == 1

    tenant_eight_input.unlink()
    tenant_eight_input.mkdir()
    (tenant_eight_input / fixture.name).write_text(
        fixture.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    tenant_eight_config.unlink()
    tenant_eight_config.symlink_to(tenant_seven_config)

    cross_tenant_config = asyncio.run(
        _execute(
            module,
            saas_user_id=8,
            json_path=fixture.name,
            target_channel="@target",
        )
    )
    assert "staging/production repost executor не настроен" in cross_tenant_config
    assert constructed_with == [tenant_seven_config.resolve()]
    assert len(runs) == 1


def test_unknown_environment_fails_closed_at_import_and_invocation(
    tmp_path,
    monkeypatch,
) -> None:
    tool_path = tmp_path / "Repost_Tool.py"
    tool_path.write_text(
        "class RepostTool:\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENT", "preview")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("REPOST_TOOL_PATH", str(tool_path))

    module = _load_module()
    assert module.RepostTool is None
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    result = asyncio.run(
        _execute(module, json_path=fixture.name, target_channel="@target")
    )

    assert "неподдерживаемый ENVIRONMENT/APP_ENV" in result
    assert calls == []


@pytest.mark.parametrize("saas_user_id", [0, -1, True, 2**63, "7"])
def test_repost_rejects_invalid_tenant_id(
    tmp_path,
    monkeypatch,
    saas_user_id,
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)

    result = asyncio.run(
        _execute(
            module,
            saas_user_id=saas_user_id,
            json_path=fixture.name,
            target_channel="@target",
        )
    )

    assert "saas_user_id" in result
    assert calls == []


def test_langchain_tool_contract_requires_tenant_id() -> None:
    module = _load_module()

    schema = module.execute_repost.args_schema.model_json_schema()

    assert "saas_user_id" in schema["required"]


@pytest.mark.parametrize("message_id", [0, -1, True, "01", "1\n2", 2**31])
def test_repost_rejects_noncanonical_or_unbounded_message_id(
    tmp_path,
    monkeypatch,
    message_id,
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["forward_post"]["message_id"] = message_id
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    result = asyncio.run(
        _execute(
            module,
            json_path=fixture.name,
            target_channel="@target",
        )
    )

    assert "message_id" in result
    assert calls == []


@pytest.mark.parametrize(
    ("field", "value", "error_marker"),
    [
        ("confirmation_token", "a" * 65, "confirmation_token"),
        ("confirmation_token", "A" * 64, "confirmation_token"),
        ("idempotency_key", "repost:" + "a" * 65, "idempotency_key"),
        ("idempotency_key", "wrong:" + "a" * 64, "idempotency_key"),
    ],
)
def test_live_repost_rejects_noncanonical_capability_inputs(
    tmp_path,
    monkeypatch,
    field,
    value,
    error_marker,
) -> None:
    module = _load_module()
    calls = _install_fake_tool(module, monkeypatch)
    fixture = _fixture_file(tmp_path, monkeypatch)
    monkeypatch.setenv("REPOST_CONFIRMATION_SECRET", CONFIRMATION_SECRET)
    monkeypatch.setenv("REPOST_IDEMPOTENCY_DB", str(tmp_path / "operations.sqlite3"))
    preview = asyncio.run(
        _execute(module, json_path=fixture.name, target_channel="@target")
    )
    arguments = {
        "json_path": fixture.name,
        "target_channel": "@target",
        "dry_run": False,
        "confirmed": True,
        "confirmation_token": _value(preview, "confirmation_token"),
        "idempotency_key": _value(preview, "idempotency_key"),
    }
    arguments[field] = value

    result = asyncio.run(_execute(module, **arguments))

    assert error_marker in result
    assert [call["dry_run"] for call in calls] == [True]
