"""Regression tests for the standalone parser and its experimental ML module."""

from pathlib import Path

import pandas as pd
import pytest

from parser_local.csv_safety import neutralize_csv_cell, neutralize_csv_row
from parser_local.ML.artifact_security import resolve_trusted_model_path
from parser_local.ML.data_loader import DataLoader
from parser_local.ML.feature_engineering import (
    POST_PUBLICATION_FEATURES,
    FeatureEngineer,
)
from parser_local.runtime_config import (
    resolve_channels_csv_path,
    resolve_session_path,
)


def test_prepublication_features_exclude_observed_outcomes() -> None:
    raw = pd.DataFrame(
        {
            "post_id": [1, 2],
            "date": ["2026-01-01T10:00:00Z", "2026-01-02T18:00:00Z"],
            "text_length": [120, 240],
            "has_photo": [True, False],
            "has_video": [False, True],
            "has_audio": [False, False],
            "has_voice": [False, False],
            "has_document": [False, False],
            "has_round_video": [False, False],
            "has_poll": [False, True],
            "channel_subscribers": [10_000, 12_000],
            "views": [2_000, 3_500],
            "forwards": [20, 70],
            "replies": [4, 8],
            "reactions": [100, 160],
            "engagement_rate": [20.0, 29.2],
        }
    )

    engineer = FeatureEngineer()
    prepared = DataLoader().prepare_features(raw)
    enriched = engineer.create_all_features(prepared)
    _, selected = engineer.select_features(enriched, target_col="forwards")

    assert {
        "forwards_to_views",
        "total_engagement",
        "views_to_subscribers_ratio",
    } <= set(enriched.columns)
    assert POST_PUBLICATION_FEATURES.isdisjoint(selected)
    assert {"hour", "has_photo", "channel_subscribers"} <= set(selected)


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_csv_formula_prefixes_are_neutralized(prefix: str) -> None:
    assert neutralize_csv_cell(f"{prefix}SUM(A1:A2)") == f"'{prefix}SUM(A1:A2)"


def test_csv_neutralizer_preserves_unicode_and_numeric_cells() -> None:
    row = {
        "telegram_text": "Привет, мир 🌍",
        "count": -42,
        "ratio": 3.14,
        "enabled": True,
        "missing": None,
    }

    assert neutralize_csv_row(row) == row
    assert neutralize_csv_row(row) is not row


def test_session_path_must_stay_inside_parser_directory(tmp_path: Path) -> None:
    parser_dir = tmp_path / "parser_local"
    parser_dir.mkdir()
    session = parser_dir / "telegram.session"
    session.touch()

    assert resolve_session_path("telegram.session", parser_dir) == session.resolve()

    outside = tmp_path / "outside.session"
    outside.touch()
    with pytest.raises(RuntimeError, match="must not escape"):
        resolve_session_path("../outside.session", parser_dir)
    with pytest.raises(RuntimeError, match="must be a relative path"):
        resolve_session_path(str(outside), parser_dir)
    with pytest.raises(FileNotFoundError, match="session file not found"):
        resolve_session_path("missing.session", parser_dir)


def test_model_artifacts_are_confined_to_trusted_directory(tmp_path: Path) -> None:
    trusted_dir = tmp_path / "models"
    trusted_dir.mkdir()
    trusted_model = trusted_dir / "viral_predictor_random_forest_test.pkl"
    trusted_model.touch()

    assert (
        resolve_trusted_model_path(trusted_model, trusted_dir)
        == trusted_model.resolve()
    )

    outside_model = tmp_path / "viral_predictor_outside.pkl"
    outside_model.touch()
    with pytest.raises(ValueError, match="inside trusted directory"):
        resolve_trusted_model_path(outside_model, trusted_dir)

    symlinked_model = trusted_dir / "viral_predictor_symlink.pkl"
    symlinked_model.symlink_to(outside_model)
    with pytest.raises(ValueError, match="Symlinked"):
        resolve_trusted_model_path(symlinked_model, trusted_dir)


def test_batch_csv_fallback_uses_repository_vector_search(tmp_path: Path) -> None:
    project_root = tmp_path / "repository"
    fallback = project_root / "vector_search" / "channels.csv"

    assert (
        resolve_channels_csv_path(tmp_path / "missing" / "channels.csv", project_root)
        == fallback.resolve()
    )

    supplied = tmp_path / "uploads" / "channels.csv"
    supplied.parent.mkdir()
    supplied.touch()
    assert resolve_channels_csv_path(supplied, project_root) == supplied.resolve()


def test_parser_has_no_legacy_secret_or_session_fallbacks() -> None:
    parser_dir = Path(__file__).parents[1] / "parser_local"
    sources = "\n".join(
        (parser_dir / name).read_text(encoding="utf-8")
        for name in (
            "README.md",
            "local_parser.py",
            "top_posts_analyzer.py",
            "top_posts_analyzer_L2.py",
        )
    )

    assert "config" + ".json" not in sources
    assert "998" + "999325220" not in sources
    assert "Чат" + " бот" not in sources


@pytest.mark.parametrize("compare_all", [False, True])
def test_training_cli_forwards_explicit_input_files(
    monkeypatch,
    compare_all: bool,
) -> None:
    import sys
    import types

    optional_models = types.ModuleType("ML.models")
    optional_models.ModelComparator = type("ModelComparator", (), {})
    optional_models.ViralPostPredictor = type("ViralPostPredictor", (), {})
    monkeypatch.setitem(sys.modules, "ML.models", optional_models)

    from parser_local.ML import train_model

    captured = {}

    class FakeDataLoader:
        def __init__(self, *, base_dir):
            self.base_dir = base_dir

    class FakeFeatureEngineer:
        pass

    class FakeComparator:
        @staticmethod
        def get_best_model():
            return "fake", object()

    def capture_single(*args, **kwargs):
        captured.update(kwargs)
        captured["mode"] = "single"
        return object()

    def capture_compare(*args, **kwargs):
        captured.update(kwargs)
        captured["mode"] = "compare"
        return FakeComparator()

    monkeypatch.setattr(train_model, "DataLoader", FakeDataLoader)
    monkeypatch.setattr(train_model, "FeatureEngineer", FakeFeatureEngineer)
    monkeypatch.setattr(train_model, "train_single_model", capture_single)
    monkeypatch.setattr(train_model, "compare_all_models", capture_compare)

    argv = [
        "train_model.py",
        "--json-path",
        "inputs/posts.json",
        "--csv-path",
        "inputs/channel.csv",
    ]
    if compare_all:
        argv.append("--compare-all")
    monkeypatch.setattr(train_model.sys, "argv", argv)

    train_model.main()

    assert captured["json_path"] == Path("inputs/posts.json")
    assert captured["csv_path"] == Path("inputs/channel.csv")
    assert captured["mode"] == ("compare" if compare_all else "single")
