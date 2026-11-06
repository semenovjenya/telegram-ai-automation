#!/usr/bin/env python3
"""Fail CI on reproducibility regressions visible in the repository tree."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml
from validate_release_tag import validate_version_manifest

ROOT = Path(__file__).resolve().parents[2]
SECRET_SCAN_CHUNK_BYTES = 1024 * 1024
SECRET_SCAN_OVERLAP_BYTES = 512

REQUIRED_PATHS = (
    ".github/scripts/validate_release_tag.py",
    "LICENSE",
    "ai_brain/Dockerfile",
    "ai_brain/requirements.lock",
    "auth-backend/Dockerfile",
    "auth-backend/app_version.py",
    "auth-backend/body_limit.py",
    "auth-backend/requirements.lock",
    "chatbot/README.md",
    "compose/api/nginx.conf",
    "compose/demo-data/channels_analysis_demo.csv",
    "compose/docker-compose.yml",
    "compose/telegram-mock/Dockerfile",
    "compose/telegram-mock/server.py",
    "docs/assets/ai-assistant-mobile.png",
    "docs/assets/dashboard-demo.png",
    "frontend-new/Dockerfile",
    "frontend-new/lib/server/request-body.ts",
    "frontend-new/package-lock.json",
    "parser_local/ML/requirements.lock",
    "parser_local/requirements.lock",
    "requirements-audit.lock",
    "requirements-audit.txt",
    "requirements-test.lock",
)

GENERATED_PATH_PATTERNS = (
    re.compile(r"(^|/)__pycache__(/|$)"),
    re.compile(r"(^|/)\.next(/|$)"),
    re.compile(r"(^|/)node_modules(/|$)"),
    re.compile(r"(^|/)\.pytest_cache(/|$)"),
    re.compile(r"(^|/)\.ruff_cache(/|$)"),
    re.compile(r"(^|/)htmlcov(/|$)"),
    re.compile(r"(^|/)\.coverage(?:\..*)?$"),
    re.compile(r"(^|/)coverage\.xml$"),
    re.compile(r"\.py[co]$"),
    re.compile(r"\.session(?:-journal)?$"),
    re.compile(r"\.pkl$"),
    re.compile(r"\.log$"),
    re.compile(r"(^|/)\.env$"),
    re.compile(r"\.(?:sqlite3?|db)$"),
)

SECRET_PATTERNS = (
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)
ACTION_SHA = re.compile(r"^[0-9a-f]{40}$")


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def tracked_and_worktree_files() -> list[str]:
    return sorted(set(git_lines("ls-files", "-co", "--exclude-standard")))


def validate_required_paths(errors: list[str]) -> None:
    for relative_path in REQUIRED_PATHS:
        if not (ROOT / relative_path).is_file():
            errors.append(f"required file is missing: {relative_path}")


def validate_release_versions(errors: list[str]) -> None:
    try:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        validate_version_manifest(ROOT, version)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        errors.append(f"release version manifest is inconsistent: {exc}")


def validate_git_tree(errors: list[str]) -> None:
    for entry in git_lines("ls-files", "-s"):
        mode, _, _, path = entry.split(maxsplit=3)
        if mode == "160000":
            errors.append(
                f"gitlink/submodule is not allowed in the public core tree: {path}"
            )

    for path in git_lines("ls-files"):
        if any(pattern.search(path) for pattern in GENERATED_PATH_PATTERNS):
            errors.append(f"generated artifact is tracked: {path}")


def validate_yaml(errors: list[str]) -> None:
    yaml_paths = sorted((ROOT / "docs" / "ci").glob("*.y*ml"))
    yaml_paths.extend(sorted((ROOT / "compose").glob("*.y*ml")))

    for path in yaml_paths:
        try:
            with path.open(encoding="utf-8-sig") as stream:
                yaml.safe_load(stream)
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"invalid YAML in {path.relative_to(ROOT)}: {exc}")


def validate_workflow_supply_chain(errors: list[str]) -> None:
    """Require immutable actions and the image vulnerability release gate."""

    workflow_paths = sorted((ROOT / "docs" / "ci").glob("*.y*ml"))
    for path in workflow_paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            errors.append(f"cannot read {path.relative_to(ROOT)}: {exc}")
            continue
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped.startswith("uses:"):
                continue
            reference = stripped.removeprefix("uses:").strip().split()[0]
            if reference.startswith("./"):
                continue
            _, separator, revision = reference.rpartition("@")
            if not separator or not ACTION_SHA.fullmatch(revision):
                errors.append(
                    f"external action is not SHA-pinned: "
                    f"{path.relative_to(ROOT)}:{line_number}"
                )

    ci_path = ROOT / "docs" / "ci" / "ci.yml"
    try:
        ci_text = ci_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read docs/ci/ci.yml: {exc}")
        return
    required_fragments = (
        "load: true",
        "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25",
        "scanners: vuln",
        "severity: HIGH,CRITICAL",
        "exit-code: 1",
    )
    for fragment in required_fragments:
        if fragment not in ci_text:
            errors.append(f"container vulnerability gate is missing: {fragment}")


def _volume_source(volume: object) -> str | None:
    if isinstance(volume, str):
        return volume.split(":", 1)[0]
    if isinstance(volume, dict):
        source = volume.get("source")
        return source if isinstance(source, str) else None
    return None


def validate_observability_boundary(errors: list[str]) -> None:
    """Keep Docker daemon access behind the least-privilege proxy."""
    compose_path = ROOT / "compose" / "docker-compose.yml"
    try:
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return

    services = compose.get("services", {}) if isinstance(compose, dict) else {}
    if not isinstance(services, dict):
        return

    socket_mount_owners: list[str] = []
    for service_name, service in services.items():
        if not isinstance(service, dict):
            continue
        for volume in service.get("volumes", []) or []:
            if _volume_source(volume) == "/var/run/docker.sock":
                socket_mount_owners.append(str(service_name))

    if socket_mount_owners != ["docker-socket-proxy"]:
        errors.append(
            "Docker socket must be mounted exactly once by docker-socket-proxy; "
            f"found owners: {socket_mount_owners or 'none'}"
        )

    proxy = services.get("docker-socket-proxy", {})
    if not isinstance(proxy, dict):
        errors.append("docker-socket-proxy service is missing")
    else:
        environment = proxy.get("environment", {})
        post_value = environment.get("POST") if isinstance(environment, dict) else None
        if str(post_value).casefold() not in {"0", "false"}:
            errors.append("docker-socket-proxy must deny POST requests")
        if proxy.get("read_only") is not True:
            errors.append("docker-socket-proxy filesystem must be read-only")

    networks = compose.get("networks", {}) if isinstance(compose, dict) else {}
    boundary_network = (
        networks.get("docker-observability", {}) if isinstance(networks, dict) else {}
    )
    if (
        not isinstance(boundary_network, dict)
        or boundary_network.get("internal") is not True
    ):
        errors.append("docker-observability network must remain internal")

    alloy_config_path = ROOT / "monitoring" / "config.alloy"
    try:
        alloy_config = alloy_config_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read monitoring/config.alloy: {exc}")
        return
    if "unix:///var/run/docker.sock" in alloy_config:
        errors.append("Alloy must not access the Docker socket directly")
    if "http://docker-socket-proxy:2375" not in alloy_config:
        errors.append("Alloy must use the isolated Docker socket proxy")


def scan_file_for_secret_names(path: Path) -> list[str]:
    """Stream-scan any file size, including matches crossing chunk boundaries."""

    found: list[str] = []
    pending_patterns = list(SECRET_PATTERNS)
    overlap = ""
    with path.open("rb") as stream:
        while pending_patterns:
            chunk = stream.read(SECRET_SCAN_CHUNK_BYTES)
            if not chunk:
                break
            # All guarded secret formats are ASCII. Latin-1 provides a lossless
            # one-byte mapping and safely scans binary/large files.
            content = overlap + chunk.decode("latin-1")
            remaining = []
            for secret_name, pattern in pending_patterns:
                if pattern.search(content):
                    found.append(secret_name)
                else:
                    remaining.append((secret_name, pattern))
            pending_patterns = remaining
            overlap = content[-SECRET_SCAN_OVERLAP_BYTES:]
    return found


def validate_secrets(errors: list[str]) -> None:
    secret_material_detected = False
    scan_failed = False
    for relative_path in tracked_and_worktree_files():
        path = ROOT / relative_path
        if not path.is_file():
            continue
        try:
            if scan_file_for_secret_names(path):
                secret_material_detected = True
        except OSError:
            scan_failed = True

    # Never echo a matching value, filename, or filesystem exception. Besides
    # preventing credential disclosure in CI logs, this keeps malicious
    # filenames and OS error strings from forging additional log entries.
    if secret_material_detected:
        errors.append("forbidden credential material detected")
    if scan_failed:
        errors.append("one or more repository files could not be scanned")


def main() -> int:
    errors: list[str] = []
    validate_required_paths(errors)
    validate_release_versions(errors)
    validate_git_tree(errors)
    validate_yaml(errors)
    validate_workflow_supply_chain(errors)
    validate_observability_boundary(errors)
    validate_secrets(errors)

    if errors:
        print("Repository guard failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Repository guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
