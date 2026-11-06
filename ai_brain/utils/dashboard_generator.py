"""Generate a deterministic, evidence-only PNG dashboard with Pillow."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

COLORS = {
    "background": "#F5F7FA",
    "card": "#FFFFFF",
    "border": "#DDE3EA",
    "text": "#17212B",
    "muted": "#667382",
    "accent": "#2A9D8F",
    "positive": "#15803D",
    "negative": "#B42318",
}

_FONT_CANDIDATES = (
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ),
    (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ),
    (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ),
)


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: float | None) -> str:
    if value is None:
        return "Нет данных"
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if magnitude >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}".replace(",", " ")


def _load_font(
    size: int, *, bold: bool = False
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for bold_path, regular_path in _FONT_CANDIDATES:
        candidate = Path(bold_path if bold else regular_path)
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    logger.warning("Cyrillic font was not found; using Pillow default font")
    return ImageFont.load_default()


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    *,
    max_lines: int,
) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = ""
    truncated = False
    for word in words:
        candidate = f"{current} {word}".strip()
        bounds = draw.textbbox((0, 0), candidate, font=font)
        if not current or bounds[2] - bounds[0] <= max_width:
            current = candidate
            continue
        lines.append(current)
        if len(lines) == max_lines:
            truncated = True
            break
        current = word
    else:
        if current:
            lines.append(current)

    if not lines and current:
        lines.append(current)

    if lines and (
        truncated or draw.textbbox((0, 0), lines[-1], font=font)[2] > max_width
    ):
        last = lines[-1]
        while last and draw.textbbox((0, 0), f"{last}…", font=font)[2] > max_width:
            last = last[:-1].rstrip()
        lines[-1] = f"{last}…" if last else "…"
    return lines[:max_lines]


def _metric_value(
    label: str,
    value: float | None,
    *,
    suffix: str = "",
) -> tuple[str, str, str]:
    if value is None:
        return label, "Нет данных", COLORS["muted"]
    if suffix:
        return label, f"{value:.1f}{suffix}", COLORS["text"]
    return label, _format_number(value), COLORS["text"]


def _growth_metric(value: float | None) -> tuple[str, str, str]:
    if value is None:
        return "Рост за период", "Нет данных", COLORS["muted"]
    prefix = "+" if value > 0 else ""
    color = (
        COLORS["positive"]
        if value > 0
        else COLORS["negative"]
        if value < 0
        else COLORS["text"]
    )
    return "Рост за период", f"{prefix}{value:.1f}%", color


def _facts(
    channel_data: dict[str, Any],
    *,
    subscribers: float | None,
    engagement_rate: float | None,
    average_reach: float | None,
    growth: float | None,
) -> list[str]:
    supplied = channel_data.get("highlights")
    if isinstance(supplied, list):
        facts = [str(item).strip() for item in supplied if str(item).strip()]
        if facts:
            return facts[:3]

    facts: list[str] = []
    if subscribers is not None:
        facts.append(f"Подписчики: {_format_number(subscribers)}")
    if engagement_rate is not None:
        facts.append(f"ERR: {engagement_rate:.1f}%")
    if average_reach is not None:
        facts.append(f"Средний охват: {_format_number(average_reach)}")
    if growth is not None:
        prefix = "+" if growth > 0 else ""
        facts.append(f"Рост за период: {prefix}{growth:.1f}%")
    return facts[:3] or ["Для аналитических выводов недостаточно данных"]


def generate_channel_dashboard_image(
    channel_data: dict[str, Any],
    saas_user_id: int = 1,
    output_path: str | None = None,
) -> str:
    """Write an evidence-only dashboard PNG and return its path."""

    if saas_user_id <= 0:
        raise ValueError("saas_user_id must be positive")

    title = str(
        channel_data.get("channel_title")
        or channel_data.get("title")
        or "Неизвестный канал"
    ).strip()[:80]
    username = (
        str(channel_data.get("channel_username") or channel_data.get("username") or "")
        .strip()
        .lstrip("@")[:64]
    )
    subscribers = _number(channel_data.get("subscribers"))
    engagement_rate = _number(
        channel_data.get("engagement_rate")
        if "engagement_rate" in channel_data
        else channel_data.get("engagement_rate_percent")
    )
    reach_values = [
        value
        for key in ("avg_reach_24h", "avg_reach_48h", "avg_reach_72h")
        if (value := _number(channel_data.get(key))) is not None
    ]
    average_reach = sum(reach_values) / len(reach_values) if reach_values else None
    growth = _number(
        channel_data.get("growth_percent")
        if "growth_percent" in channel_data
        else channel_data.get("subscriber_growth_percent")
    )

    if output_path is None:
        with tempfile.NamedTemporaryFile(
            prefix=f"dashboard-{saas_user_id}-",
            suffix=".png",
            delete=False,
        ) as temporary_file:
            output_path = temporary_file.name

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    width, height = 780, 920
    image = Image.new("RGB", (width, height), COLORS["background"])
    draw = ImageDraw.Draw(image)
    title_font = _load_font(32, bold=True)
    subtitle_font = _load_font(18)
    label_font = _load_font(17)
    value_font = _load_font(31, bold=True)
    section_font = _load_font(23, bold=True)
    body_font = _load_font(18)

    draw.text((40, 35), title, fill=COLORS["text"], font=title_font)
    subtitle = f"@{username}" if username else "username не указан"
    draw.text((40, 80), subtitle, fill=COLORS["muted"], font=subtitle_font)

    metrics = (
        _metric_value("Подписчики", subscribers),
        _metric_value("Средний охват", average_reach),
        _metric_value("ERR", engagement_rate, suffix="%"),
        _growth_metric(growth),
    )
    card_width, card_height = 340, 150
    for index, (label, value, value_color) in enumerate(metrics):
        column, row = index % 2, index // 2
        left = 40 + column * 370
        top = 125 + row * 180
        draw.rounded_rectangle(
            (left, top, left + card_width, top + card_height),
            radius=18,
            fill=COLORS["card"],
            outline=COLORS["border"],
            width=2,
        )
        draw.text((left + 22, top + 25), label, fill=COLORS["muted"], font=label_font)
        draw.text((left + 22, top + 72), value, fill=value_color, font=value_font)

    info_top = 500
    draw.rounded_rectangle(
        (40, info_top, 740, 855),
        radius=18,
        fill=COLORS["card"],
        outline=COLORS["border"],
        width=2,
    )
    draw.text(
        (66, info_top + 28), "Сводка по данным", fill=COLORS["text"], font=section_font
    )

    summary = channel_data.get("ai_summary") or channel_data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = (
            "Показаны только значения, полученные от источника. "
            "Отсутствующие показатели не рассчитываются и не подменяются оценками."
        )
    text_y = info_top + 78
    for line in _fit_text(draw, summary.strip(), body_font, 640, max_lines=4):
        draw.text((66, text_y), line, fill=COLORS["text"], font=body_font)
        text_y += 28

    text_y += 18
    for fact in _facts(
        channel_data,
        subscribers=subscribers,
        engagement_rate=engagement_rate,
        average_reach=average_reach,
        growth=growth,
    ):
        draw.ellipse((68, text_y + 7, 78, text_y + 17), fill=COLORS["accent"])
        for line in _fit_text(draw, fact, body_font, 610, max_lines=1):
            draw.text((92, text_y), line, fill=COLORS["text"], font=body_font)
        text_y += 38

    source = str(channel_data.get("data_source") or "не указан").strip()[:80]
    draw.text(
        (40, 878),
        f"Источник: {source}",
        fill=COLORS["muted"],
        font=subtitle_font,
    )

    image.save(destination, "PNG", optimize=True)
    logger.info("dashboard_artifact_written")
    return str(destination)
