"""Truthfulness contract for dashboard data exposed by the auth gateway."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_data_loader():
    path = ROOT / "auth-backend" / "data_loader.py"
    spec = importlib.util.spec_from_file_location("dashboard_data_loader", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_demo_snapshot(root: Path) -> None:
    (root / "channels_analysis_snapshot.csv").write_text(
        "username\ttitle\tsubscribers\tengagement_rate_percent\t"
        "avg_reach_72h\tposting_posts_per_day\n"
        "demo_analytics_channel\tДемо-канал аналитики\t12840\t18.7\t6100\t2.4\n",
        encoding="utf-8",
    )
    (root / "top_posts_snapshot.json").write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "post_id": 1,
                        "text_preview": "low-view post",
                        "views": 100,
                        "age_days": 1,
                    },
                    {
                        "post_id": 2,
                        "text_preview": "highest-view post",
                        "views": 2000,
                        "age_days": 2,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def test_dashboard_metric_names_match_values_and_do_not_invent_trends(
    tmp_path,
    monkeypatch,
) -> None:
    loader = _load_data_loader()
    monkeypatch.setattr(loader, "PARSER_LOGS_DIR", str(tmp_path))
    _write_demo_snapshot(tmp_path)
    args = {
        "saas_user_id": 1,
        "data_source": "synthetic-demo",
        "default_saas_user_id": 1,
    }

    metrics = loader.get_dashboard_metrics(**args)

    assert set(metrics) == {
        "subscribers",
        "engagement",
        "postsPerDay",
        "averageViews",
    }
    assert metrics["postsPerDay"]["value"] == 2.4
    assert metrics["averageViews"]["value"] == 1050
    assert metrics["engagement"]["value"] == 18.7
    assert all(metric["change"] is None for metric in metrics.values())
    assert all(metric["changePercent"] is None for metric in metrics.values())


def test_dashboard_rules_and_notifications_only_claim_available_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    loader = _load_data_loader()
    monkeypatch.setattr(loader, "PARSER_LOGS_DIR", str(tmp_path))
    _write_demo_snapshot(tmp_path)
    args = {
        "saas_user_id": 1,
        "data_source": "synthetic-demo",
        "default_saas_user_id": 1,
    }

    recommendation = loader.get_ai_recommendation(**args)
    notifications = loader.get_notifications(**args)

    assert "2.4 поста/день" in recommendation
    assert "порога правила 5" in recommendation
    assert "Причинный эффект не доказан" in recommendation
    assert "вторник" not in recommendation.casefold()
    assert notifications[0]["timeAgo"] == "Текущий срез"
    assert "highest-view post" in notifications[1]["text"]
    assert "2.0K" in notifications[1]["text"]
