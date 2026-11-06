import logging
from pathlib import Path

import pytest
from PIL import Image

from ai_brain.utils.dashboard_generator import (
    _facts,
    _growth_metric,
    generate_channel_dashboard_image,
)


def test_dashboard_marks_missing_growth_without_inventing_a_value(
    tmp_path: Path,
    caplog,
) -> None:
    caplog.set_level(logging.INFO)
    output = tmp_path / "sentinel-private-path" / "dashboard.png"
    output.parent.mkdir()
    result = generate_channel_dashboard_image(
        {
            "channel_title": "Synthetic channel",
            "channel_username": "synthetic_channel",
            "subscribers": 1200,
            "engagement_rate": 4.5,
            "data_source": "synthetic-demo",
        },
        saas_user_id=7,
        output_path=str(output),
    )

    assert Path(result) == output
    with Image.open(output) as image:
        assert image.format == "PNG"
        assert image.size == (780, 920)

    _, value, _ = _growth_metric(None)
    assert value == "Нет данных"
    assert "sentinel-private-path" not in caplog.text


def test_dashboard_facts_are_derived_only_from_supplied_metrics() -> None:
    facts = _facts(
        {},
        subscribers=None,
        engagement_rate=None,
        average_reach=None,
        growth=None,
    )

    assert facts == ["Для аналитических выводов недостаточно данных"]


def test_dashboard_rejects_invalid_tenant(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="saas_user_id"):
        generate_channel_dashboard_image(
            {},
            saas_user_id=0,
            output_path=str(tmp_path / "dashboard.png"),
        )
