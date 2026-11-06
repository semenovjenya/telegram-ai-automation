"""Regression tests for the fail-closed container release tag gate."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_release_guard():
    path = ROOT / ".github" / "scripts" / "validate_release_tag.py"
    spec = importlib.util.spec_from_file_location("validate_release_tag", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_ref_requires_exact_stable_vversion(tmp_path) -> None:
    release_guard = _load_release_guard()
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.3\n", encoding="utf-8")

    assert release_guard.validate_release_ref(version_file, "tag", "v1.2.3") == "1.2.3"

    for ref_type, ref_name in (
        ("branch", "main"),
        ("tag", "1.2.3"),
        ("tag", "v1.2.4"),
        ("tag", "v1.2.3-rc.1"),
    ):
        with pytest.raises(ValueError):
            release_guard.validate_release_ref(version_file, ref_type, ref_name)


@pytest.mark.parametrize(
    "version", ["01.2.3", "1.2", "1.2.3-rc.1", "1.2.3 ", "1.2.3\nextra"]
)
def test_release_ref_rejects_non_stable_or_ambiguous_version_files(
    tmp_path,
    version,
) -> None:
    release_guard = _load_release_guard()
    version_file = tmp_path / "VERSION"
    version_file.write_text(version, encoding="utf-8")

    with pytest.raises(ValueError, match="VERSION"):
        release_guard.validate_release_ref(version_file, "tag", f"v{version}")


def test_release_commit_must_be_reachable_from_main(monkeypatch, tmp_path) -> None:
    release_guard = _load_release_guard()
    calls = []

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return Result(0)

    monkeypatch.setattr(release_guard.subprocess, "run", run)
    release_guard.validate_release_commit(tmp_path, "tagged-sha", "origin/main")

    assert calls == [
        (
            [
                "git",
                "merge-base",
                "--is-ancestor",
                "tagged-sha",
                "origin/main",
            ],
            {
                "cwd": tmp_path,
                "check": False,
                "capture_output": True,
                "text": True,
            },
        )
    ]

    monkeypatch.setattr(
        release_guard.subprocess,
        "run",
        lambda *args, **kwargs: Result(1),
    )
    with pytest.raises(ValueError, match="ancestor of origin/main"):
        release_guard.validate_release_commit(
            tmp_path,
            "unmerged-sha",
            "origin/main",
        )

    monkeypatch.setattr(
        release_guard.subprocess,
        "run",
        lambda *args, **kwargs: Result(128),
    )
    with pytest.raises(RuntimeError, match="Unable to verify"):
        release_guard.validate_release_commit(
            tmp_path,
            "unknown-sha",
            "origin/main",
        )


def test_release_version_manifest_matches_every_runtime_package(tmp_path) -> None:
    release_guard = _load_release_guard()
    release_guard.validate_version_manifest(ROOT, "0.3.0")

    (tmp_path / "frontend-new").mkdir()
    (tmp_path / "ai_brain").mkdir()
    (tmp_path / "auth-backend").mkdir()
    (tmp_path / "frontend-new" / "package.json").write_text(
        json.dumps({"version": "1.2.3"}), encoding="utf-8"
    )
    (tmp_path / "frontend-new" / "package-lock.json").write_text(
        json.dumps({"version": "1.2.4", "packages": {"": {"version": "1.2.3"}}}),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "1.2.3"\n', encoding="utf-8"
    )
    (tmp_path / "ai_brain" / "__init__.py").write_text(
        '__version__ = "1.2.3"\n', encoding="utf-8"
    )
    (tmp_path / "auth-backend" / "app_version.py").write_text(
        '__version__ = "1.2.3"\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="package-lock.json"):
        release_guard.validate_version_manifest(tmp_path, "1.2.3")
