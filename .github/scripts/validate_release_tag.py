#!/usr/bin/env python3
"""Fail closed unless a release runs from the exact stable vVERSION tag."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from pathlib import Path

STABLE_SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
)
VERSION_CONSTANT = re.compile(
    r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$',
    re.MULTILINE,
)


def _python_version(path: Path) -> str:
    match = VERSION_CONSTANT.search(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"Missing __version__ in {path}")
    return match.group(1)


def validate_version_manifest(repository: Path, expected: str) -> None:
    """Require every published/runtime package to use the release version."""

    package = json.loads(
        (repository / "frontend-new" / "package.json").read_text(encoding="utf-8")
    )
    package_lock = json.loads(
        (repository / "frontend-new" / "package-lock.json").read_text(encoding="utf-8")
    )
    with (repository / "pyproject.toml").open("rb") as stream:
        pyproject = tomllib.load(stream)

    actual_versions = {
        "pyproject.toml": pyproject.get("project", {}).get("version"),
        "frontend-new/package.json": package.get("version"),
        "frontend-new/package-lock.json": package_lock.get("version"),
        "frontend-new/package-lock.json root package": package_lock.get("packages", {})
        .get("", {})
        .get("version"),
        "ai_brain/__init__.py": _python_version(
            repository / "ai_brain" / "__init__.py"
        ),
        "auth-backend/app_version.py": _python_version(
            repository / "auth-backend" / "app_version.py"
        ),
    }
    mismatches = [
        f"{source}={actual!r}"
        for source, actual in actual_versions.items()
        if actual != expected
    ]
    if mismatches:
        raise ValueError(
            "Release version sources must match VERSION: " + ", ".join(mismatches)
        )


def validate_release_ref(version_file: Path, ref_type: str, ref_name: str) -> str:
    """Return the validated version or raise a safe, actionable error."""

    raw_version = version_file.read_text(encoding="utf-8")
    version = raw_version.rstrip("\n")
    if raw_version not in {version, f"{version}\n"} or not STABLE_SEMVER.fullmatch(
        version
    ):
        raise ValueError(
            "VERSION must contain one stable SemVer value (for example 1.2.3)"
        )
    if ref_type != "tag":
        raise ValueError("Container publishing is allowed only from a Git tag")

    expected_ref_name = f"v{version}"
    if ref_name != expected_ref_name:
        raise ValueError(
            f"Release tag must exactly match VERSION: expected {expected_ref_name}"
        )
    return version


def validate_release_commit(
    repository: Path,
    commit: str,
    main_ref: str,
) -> None:
    """Require the exact tagged commit to be reachable from the protected branch."""

    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, main_ref],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 1:
        raise ValueError("Release commit must be an ancestor of origin/main")
    if result.returncode != 0:
        raise RuntimeError("Unable to verify release commit ancestry")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-file", type=Path, required=True)
    parser.add_argument("--ref-type", required=True)
    parser.add_argument("--ref-name", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--main-ref", required=True)
    args = parser.parse_args()

    try:
        version = validate_release_ref(
            args.version_file,
            args.ref_type,
            args.ref_name,
        )
        validate_version_manifest(
            args.version_file.resolve().parent,
            version,
        )
        validate_release_commit(
            args.version_file.resolve().parent,
            args.commit,
            args.main_ref,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Validated release tag v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
