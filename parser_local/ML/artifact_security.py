"""Trust-boundary checks for locally generated ML artifacts."""

from fnmatch import fnmatch
from pathlib import Path

MODEL_ARTIFACT_VERSION = 2
MODEL_FEATURE_POLICY = "prepublication-v1"
TRUSTED_MODEL_PATTERN = "viral_predictor_*.pkl"


def resolve_trusted_model_path(filepath: Path, trusted_dir: Path) -> Path:
    """Allow model artifacts only from the dedicated local model directory."""
    trusted_dir = trusted_dir.resolve(strict=True)
    requested_path = Path(filepath)
    if requested_path.is_symlink():
        raise ValueError("Symlinked model artifacts are not allowed")

    resolved_path = requested_path.resolve(strict=True)
    try:
        resolved_path.relative_to(trusted_dir)
    except ValueError as exc:
        raise ValueError(
            f"Model artifact must be stored inside trusted directory: {trusted_dir}"
        ) from exc

    if not resolved_path.is_file() or not fnmatch(
        resolved_path.name,
        TRUSTED_MODEL_PATTERN,
    ):
        raise ValueError(f"Model artifact must match {TRUSTED_MODEL_PATTERN}")
    return resolved_path
