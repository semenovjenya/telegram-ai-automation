"""Regressions for fail-closed repository release checks."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_guard():
    path = ROOT / ".github" / "scripts" / "repository_guard.py"
    spec = importlib.util.spec_from_file_location("repository_guard_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_large_file_secret_scan_crosses_chunk_boundary(tmp_path) -> None:
    guard = _load_guard()
    prefix = (
        b"x" * (guard.SECRET_SCAN_CHUNK_BYTES - 3) + b" " + ("s" + "k").encode("ascii")
    )
    synthetic_key_tail = ("-" + "A" * 40).encode("ascii")
    path = tmp_path / "large.bin"
    path.write_bytes(prefix + synthetic_key_tail + b" tail")

    assert guard.scan_file_for_secret_names(path) == ["OpenAI API key"]


def test_secret_guard_reports_only_a_redacted_finding(monkeypatch, tmp_path) -> None:
    guard = _load_guard()
    path = tmp_path / "sensitive-name.env"
    path.write_bytes(("s" + "k-" + "A" * 40).encode("ascii"))
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(
        guard,
        "tracked_and_worktree_files",
        lambda: [path.name],
    )

    errors: list[str] = []
    guard.validate_secrets(errors)

    assert errors == ["forbidden credential material detected"]
    assert path.name not in errors[0]
