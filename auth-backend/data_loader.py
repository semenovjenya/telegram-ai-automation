"""Модуль для загрузки данных из файлов парсеров."""

import csv
import json
import os
from pathlib import Path
from typing import Any

# Путь к логам парсеров
PARSER_LOGS_DIR = os.getenv("PARSER_LOGS_DIR", "/app/parser_local/Logs")


def get_parser_logs_dir(
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
) -> str:
    """Resolve an authenticated tenant's dataset without a global live fallback."""

    if saas_user_id <= 0:
        raise ValueError("saas_user_id must be positive")

    root = Path(PARSER_LOGS_DIR).expanduser().resolve()
    if data_source == "synthetic-demo":
        if saas_user_id != default_saas_user_id:
            raise PermissionError("Synthetic dashboard data is unavailable")
        return str(root)
    if data_source != "live":
        raise ValueError("Unsupported dashboard data source")

    # Live files are always namespaced by the verified numeric tenant claim.
    return str(root / str(saas_user_id))


def find_latest_file(
    pattern: str,
    extension: str,
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
) -> str | None:
    """Найти последний файл по паттерну и расширению."""
    logs_dir = get_parser_logs_dir(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )

    if not os.path.exists(logs_dir):
        return None

    try:
        files = [
            f
            for f in os.listdir(logs_dir)
            if f.startswith(pattern) and f.endswith(extension)
        ]

        if not files:
            return None

        # Сортируем по времени модификации
        files_with_time = [
            (f, os.path.getmtime(os.path.join(logs_dir, f))) for f in files
        ]
        files_with_time.sort(key=lambda x: x[1], reverse=True)

        return os.path.join(logs_dir, files_with_time[0][0])
    except Exception as e:
        print(f"Error finding latest file: {e}")
        return None


def load_channel_metrics(
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
) -> dict[str, Any] | None:
    """Загрузить метрики канала из CSV файла."""
    csv_path = find_latest_file(
        "channels_analysis_",
        ".csv",
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )

    if not csv_path or not os.path.exists(csv_path):
        return None

    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            row = next(reader, None)

            if not row:
                return None

            # Обрезаем пробелы из ключей и значений
            row = {k.strip(): (v.strip() if v else "") for k, v in row.items()}

            return {
                "subscribers": int(row.get("subscribers", 0) or 0),
                "engagement_rate_percent": float(
                    row.get("engagement_rate_percent", 0) or 0
                ),
                "avg_reach_24h": float(row.get("avg_reach_24h", 0) or 0),
                "avg_reach_48h": float(row.get("avg_reach_48h", 0) or 0),
                "avg_reach_72h": float(row.get("avg_reach_72h", 0) or 0),
                "posting_posts_per_day": float(
                    row.get("posting_posts_per_day", 0) or 0
                ),
                "reposts_72h": int(row.get("reposts_72h", 0) or 0),
                "title": row.get("title", ""),
                "username": row.get("username", ""),
            }
    except Exception as e:
        print(f"Error loading channel metrics: {e}")
        return None


def load_top_posts(
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
) -> dict[str, Any] | None:
    """Загрузить топ посты из JSON файла."""
    json_path = find_latest_file(
        "top_posts_",
        ".json",
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )

    if not json_path or not os.path.exists(json_path):
        return None

    try:
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading top posts: {e}")
        return None


def get_dashboard_metrics(
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
) -> dict[str, Any] | None:
    """Получить метрики для dashboard."""
    channel_metrics = load_channel_metrics(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )
    top_posts = load_top_posts(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )

    if not channel_metrics:
        return None

    # Вычисляем средние значения из постов
    avg_views = int(channel_metrics.get("avg_reach_72h", 0))

    if top_posts and "posts" in top_posts and top_posts["posts"]:
        posts = top_posts["posts"]
        if posts:
            avg_views = int(sum(p.get("views", 0) for p in posts) / len(posts))

    return {
        "subscribers": {
            "value": channel_metrics["subscribers"],
            "change": None,
            "changePercent": None,
        },
        "engagement": {
            "value": float(channel_metrics["engagement_rate_percent"]),
            "change": None,
            "changePercent": None,
        },
        "postsPerDay": {
            "value": channel_metrics["posting_posts_per_day"],
            "change": None,
            "changePercent": None,
        },
        "averageViews": {"value": avg_views, "change": None, "changePercent": None},
    }


def get_publications(
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Получить лучшие публикации."""
    top_posts = load_top_posts(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )

    if not top_posts or "posts" not in top_posts:
        return []

    posts = top_posts["posts"]
    # Сортируем по просмотрам и берем топ
    sorted_posts = sorted(posts, key=lambda x: x.get("views", 0), reverse=True)

    def format_views(views: int) -> str:
        if views >= 1_000_000:
            return f"{(views / 1_000_000):.1f}М просмотров"
        if views >= 1_000:
            return f"{(views / 1_000):.1f}K просмотров"
        return f"{views} просмотров"

    def format_time_ago(days: float) -> str:
        if days < 1:
            hours = int(days * 24)
            return f"{hours} {'час' if hours == 1 else 'часов'} назад"
        elif days < 7:
            d = int(days)
            return f"{d} {'день' if d == 1 else 'дней'} назад"
        else:
            weeks = int(days / 7)
            return f"{weeks} {'неделя' if weeks == 1 else 'недель'} назад"

    return [
        {
            "id": str(post.get("post_id", "")),
            "title": (post.get("text_preview", "")[:50] + "...")
            if len(post.get("text_preview", "")) > 50
            else post.get("text_preview", ""),
            "views": format_views(post.get("views", 0)),
            "timeAgo": format_time_ago(post.get("age_days", 0)),
        }
        for post in sorted_posts[:limit]
    ]


def get_profile(
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
) -> dict[str, str]:
    """Получить профиль канала."""
    channel_metrics = load_channel_metrics(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )

    if not channel_metrics:
        return {"username": "Telegram-канал", "url": ""}

    username = channel_metrics.get("title", "Telegram-канал")
    channel_username = channel_metrics.get("username", "")
    url = f"t.me/{channel_username}" if channel_username else ""

    return {"username": username, "url": url}


def get_ai_summary(
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
) -> list[dict[str, str]]:
    """Получить AI сводку."""
    channel_metrics = load_channel_metrics(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )
    top_posts = load_top_posts(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )

    if not channel_metrics:
        return []

    summaries = []

    engagement = channel_metrics.get("engagement_rate_percent", 0)
    if engagement > 20:
        summaries.append(
            {
                "id": "1",
                "text": f"Измеренная вовлеченность: {engagement:.1f}%; порог правила 20% превышен.",
            }
        )

    if top_posts and "posts" in top_posts and top_posts["posts"]:
        posts = top_posts["posts"]
        if posts:
            avg_engagement = sum(p.get("engagement_rate", 0) for p in posts) / len(
                posts
            )
            summaries.append(
                {
                    "id": "2",
                    "text": f"Средний engagement rate постов: {avg_engagement:.1f}%.",
                }
            )

    posting = channel_metrics.get("posting_posts_per_day", 0)
    if posting > 10:
        summaries.append(
            {"id": "3", "text": f"Активная публикация: {posting:.1f} постов в день."}
        )

    return (
        summaries
        if summaries
        else [
            {
                "id": "1",
                "text": "Данные канала загружены; пороговые события не зафиксированы.",
            }
        ]
    )


def get_ai_recommendation(
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
) -> str:
    """Получить AI рекомендацию."""
    channel_metrics = load_channel_metrics(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )

    if not channel_metrics:
        return "Недостаточно измеренных данных для пороговой оценки."

    posting = channel_metrics.get("posting_posts_per_day", 0)
    engagement = channel_metrics.get("engagement_rate_percent", 0)

    triggered_rules = []
    if posting < 5:
        triggered_rules.append("частота ниже порога правила 5 постов/день")
    if engagement < 15:
        triggered_rules.append("вовлечённость ниже порога правила 15%")

    measured = f"Измерено: {posting:.1f} поста/день, вовлечённость {engagement:.1f}%."
    if triggered_rules:
        return f"{measured} Сработало правило: {'; '.join(triggered_rules)}. Причинный эффект не доказан."
    return f"{measured} Пороговые правила не сработали; причинный эффект не доказан."


def get_notifications(
    saas_user_id: int,
    *,
    data_source: str,
    default_saas_user_id: int,
) -> list[dict[str, Any]]:
    """Получить уведомления."""
    channel_metrics = load_channel_metrics(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )
    top_posts = load_top_posts(
        saas_user_id,
        data_source=data_source,
        default_saas_user_id=default_saas_user_id,
    )

    notifications = []

    if channel_metrics:
        subscribers = channel_metrics.get("subscribers", 0)
        if subscribers > 0:

            def format_number(num: int) -> str:
                if num >= 1_000_000:
                    return f"{(num / 1_000_000):.1f}M"
                if num >= 1_000:
                    return f"{(num / 1_000):.1f}K"
                return str(num)

            notifications.append(
                {
                    "id": "1",
                    "icon": "chart",
                    "text": f"Число подписчиков: {format_number(subscribers)}.",
                    "timeAgo": "Текущий срез",
                }
            )

    if top_posts and "posts" in top_posts and top_posts["posts"]:
        posts = top_posts["posts"]
        if posts:
            top_post = max(posts, key=lambda post: post.get("views", 0))
            text_preview = top_post.get("text_preview", "")
            views = top_post.get("views", 0)

            def format_views(views: int) -> str:
                if views >= 1_000_000:
                    return f"{(views / 1_000_000):.1f}М"
                if views >= 1_000:
                    return f"{(views / 1_000):.1f}K"
                return str(views)

            notifications.append(
                {
                    "id": "2",
                    "icon": "lightning",
                    "text": f'Топ пост "{text_preview[:30]}..." набрал {format_views(views)} просмотров.',
                    "timeAgo": f"{int(top_post.get('age_days', 0))} дней назад",
                }
            )

    return notifications
