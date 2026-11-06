"""
Скрипт для анализа топ постов канала по количеству репостов.
Собирает метаданные о постах и ранжирует их по убыванию.
"""

import argparse
import asyncio
import csv
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError, UsernameNotOccupiedError
from telethon.tl.functions.channels import GetFullChannelRequest

if __package__:
    from .csv_safety import neutralize_csv_row
    from .runtime_config import load_telegram_config
else:
    from csv_safety import neutralize_csv_row
    from runtime_config import load_telegram_config

# Настройка путей
SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "Logs"
LOG_DIR.mkdir(exist_ok=True)


@dataclass
class PostMetadata:
    """Метаданные одного поста"""

    post_id: int
    date: str
    date_timestamp: float
    text_full: str  # Полный текст поста
    text_preview: str  # Первые 200 символов для предпросмотра
    text_length: int
    views: int
    forwards: int
    replies: int
    reactions: int
    has_photo: bool
    has_video: bool
    has_audio: bool
    has_voice: bool
    has_document: bool
    has_round_video: bool
    has_poll: bool
    url: str
    engagement_rate: float  # (views / subscribers) * 100
    age_hours: float
    age_days: float


class TopPostsAnalyzer:
    """Анализатор топ постов по репостам"""

    def __init__(self, session_path: str, api_id: int, api_hash: str, proxy=None):
        """
        Инициализация анализатора

        Args:
            session_path: Путь к файлу сессии Telegram
            api_id: API ID Telegram
            api_hash: API Hash Telegram
            proxy: Прокси (опционально)
        """
        self.client = TelegramClient(
            session_path,
            api_id,
            api_hash,
            proxy=proxy,
            device_model="Samsung SM-G996B",
            system_version="Android 13",
            app_version="10.3.1",
            lang_code="ru",
            system_lang_code="ru-RU",
        )
        self.posts: list[PostMetadata] = []

    async def connect(self):
        """Подключение к Telegram"""
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError(
                "❌ Пользователь не авторизован. Запустите авторизацию сначала."
            )
        print("✅ Подключено к Telegram")

    async def disconnect(self):
        """Отключение от Telegram"""
        await self.client.disconnect()

    def _resolve_channel(self, channel_input: str):
        """Разрешение имени канала (username или ссылка)"""
        # Убираем префиксы
        channel_input = channel_input.strip()
        if channel_input.startswith("https://t.me/"):
            channel_input = channel_input.replace("https://t.me/", "")
        if channel_input.startswith("t.me/"):
            channel_input = channel_input.replace("t.me/", "")
        if channel_input.startswith("@"):
            channel_input = channel_input[1:]
        return channel_input

    async def get_channel_info(self, channel_username: str):
        """Получение информации о канале"""
        try:
            entity = await self.client.get_entity(channel_username)
            full = await self.client(GetFullChannelRequest(channel=entity))

            username = getattr(entity, "username", "") or ""
            title = getattr(entity, "title", "") or (
                getattr(entity, "first_name", "") or ""
            )
            subscribers = getattr(full.full_chat, "participants_count", 0) or 0

            return {
                "entity": entity,
                "username": username,
                "title": title,
                "subscribers": subscribers,
            }
        except (UsernameNotOccupiedError, ValueError) as e:
            raise RuntimeError(f"❌ Канал '{channel_username}' не найден: {e}") from e

    async def collect_posts_metadata(
        self,
        channel_entity,
        limit: int = 1000,
        subscribers: int = 0,
        min_forwards: int = 0,
    ) -> list[PostMetadata]:
        """
        Сбор метаданных о постах

        Args:
            channel_entity: Entity канала
            limit: Максимальное количество постов для анализа
            subscribers: Количество подписчиков (для расчета engagement rate)
            min_forwards: Минимальное количество репостов (фильтр)
        """
        print(f"📥 Загрузка постов (лимит: {limit})...")

        now = datetime.now(UTC)
        posts_metadata = []

        async for msg in self.client.iter_messages(channel_entity, limit=limit):
            try:
                # Пропускаем служебные сообщения
                if msg.action:
                    continue

                # Базовые метрики
                views = getattr(msg, "views", 0) or 0
                forwards = getattr(msg, "forwards", 0) or 0
                replies = getattr(msg, "replies", None)
                replies_count = replies.replies if replies else 0

                # Реакции
                reactions = getattr(msg, "reactions", None)
                reactions_count = (
                    sum(r.count for r in reactions.results)
                    if reactions and reactions.results
                    else 0
                )

                # Фильтр по минимальному количеству репостов
                if forwards < min_forwards:
                    continue

                # Тип контента
                has_photo = bool(msg.photo)
                has_video = bool(msg.video)
                has_audio = bool(msg.audio)
                has_voice = bool(getattr(msg, "voice", None))
                has_document = bool(msg.document)
                has_round_video = bool(getattr(msg, "video_note", None))
                has_poll = bool(msg.poll)

                # Текст - собираем полный текст
                text_full = msg.message or ""
                text_length = len(text_full)
                # Превью - первые 200 символов, заменяем переносы строк на пробелы для компактности
                text_preview = (
                    text_full[:200].replace("\n", " ") if text_full else "(без текста)"
                )

                # Дата
                msg_date = msg.date
                age_hours = (now - msg_date).total_seconds() / 3600
                age_days = age_hours / 24

                # Engagement rate
                engagement_rate = (views / subscribers * 100) if subscribers > 0 else 0

                # URL поста
                username = getattr(channel_entity, "username", "")
                if username:
                    url = f"https://t.me/{username}/{msg.id}"
                else:
                    channel_id = str(abs(channel_entity.id))[3:]  # Убираем префикс
                    url = f"https://t.me/c/{channel_id}/{msg.id}"

                post_meta = PostMetadata(
                    post_id=msg.id,
                    date=msg_date.strftime("%Y-%m-%d %H:%M:%S"),
                    date_timestamp=msg_date.timestamp(),
                    text_full=text_full,
                    text_preview=text_preview,
                    text_length=text_length,
                    views=views,
                    forwards=forwards,
                    replies=replies_count,
                    reactions=reactions_count,
                    has_photo=has_photo,
                    has_video=has_video,
                    has_audio=has_audio,
                    has_voice=has_voice,
                    has_document=has_document,
                    has_round_video=has_round_video,
                    has_poll=has_poll,
                    url=url,
                    engagement_rate=round(engagement_rate, 2),
                    age_hours=round(age_hours, 1),
                    age_days=round(age_days, 2),
                )

                posts_metadata.append(post_meta)

            except FloodWaitError as e:
                print(f"⚠️ FloodWait: нужно подождать {e.seconds} секунд")
                await asyncio.sleep(e.seconds)
                continue
            except Exception as e:
                print(f"⚠️ Ошибка при обработке поста {getattr(msg, 'id', '?')}: {e}")
                continue

        print(f"✅ Собрано метаданных: {len(posts_metadata)} постов")
        return posts_metadata

    def rank_posts(
        self, posts: list[PostMetadata], sort_by: str = "forwards"
    ) -> list[PostMetadata]:
        """
        Ранжирование постов

        Args:
            posts: Список постов
            sort_by: Поле для сортировки ('forwards', 'views', 'engagement_rate')
        """
        if sort_by == "forwards":
            return sorted(posts, key=lambda x: x.forwards, reverse=True)
        elif sort_by == "views":
            return sorted(posts, key=lambda x: x.views, reverse=True)
        elif sort_by == "engagement_rate":
            return sorted(posts, key=lambda x: x.engagement_rate, reverse=True)
        else:
            return sorted(posts, key=lambda x: x.forwards, reverse=True)

    def save_to_csv(self, posts: list[PostMetadata], filename: str):
        """Сохранение в CSV"""
        if not posts:
            print("⚠️ Нет данных для сохранения")
            return

        filepath = LOG_DIR / filename
        fieldnames = [
            "rank",
            "post_id",
            "date",
            "forwards",
            "views",
            "replies",
            "reactions",
            "engagement_rate",
            "age_days",
            "text_full",
            "text_preview",
            "has_photo",
            "has_video",
            "has_audio",
            "url",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for rank, post in enumerate(posts, 1):
                writer.writerow(
                    neutralize_csv_row(
                        {
                            "rank": rank,
                            "post_id": post.post_id,
                            "date": post.date,
                            "forwards": post.forwards,
                            "views": post.views,
                            "replies": post.replies,
                            "reactions": post.reactions,
                            "engagement_rate": post.engagement_rate,
                            "age_days": post.age_days,
                            "text_full": post.text_full,
                            "text_preview": post.text_preview,
                            "has_photo": "✓" if post.has_photo else "",
                            "has_video": "✓" if post.has_video else "",
                            "has_audio": "✓" if post.has_audio else "",
                            "url": post.url,
                        }
                    )
                )

        print(f"💾 Сохранено в CSV: {filepath}")

    def save_to_json(self, posts: list[PostMetadata], filename: str):
        """Сохранение в JSON"""
        if not posts:
            print("⚠️ Нет данных для сохранения")
            return

        filepath = LOG_DIR / filename
        data = {
            "generated_at": datetime.now(UTC).isoformat(),
            "total_posts": len(posts),
            "posts": [asdict(post) for post in posts],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"💾 Сохранено в JSON: {filepath}")

    def print_top_report(
        self, posts: list[PostMetadata], channel_title: str, top_n: int = 10
    ):
        """Вывод отчета в консоль"""
        print("\n" + "=" * 80)
        print(f"🏆 ТОП-{top_n} ПОСТОВ ПО РЕПОСТАМ: {channel_title}")
        print("=" * 80)

        if not posts:
            print("❌ Нет постов для отображения")
            return

        for rank, post in enumerate(posts[:top_n], 1):
            print(f"\n📌 #{rank} (ID: {post.post_id})")
            print(f"   🔄 Репостов: {post.forwards:,}")
            print(f"   👁️  Просмотров: {post.views:,}")
            print(f"   💬 Ответов: {post.replies}")
            print(f"   ⭐ Реакций: {post.reactions}")
            print(f"   📊 Engagement: {post.engagement_rate}%")
            print(f"   📅 Дата: {post.date} ({post.age_days:.1f} дн. назад)")

            # Типы контента
            content_types = []
            if post.has_photo:
                content_types.append("📷 фото")
            if post.has_video:
                content_types.append("🎥 видео")
            if post.has_audio:
                content_types.append("🎵 аудио")
            if post.has_voice:
                content_types.append("🎤 голос")
            if post.has_document:
                content_types.append("📄 документ")
            if post.has_round_video:
                content_types.append("⭕ круг")
            if post.has_poll:
                content_types.append("📊 опрос")

            if content_types:
                print(f"   📎 Контент: {', '.join(content_types)}")

            # Превью текста
            if post.text_preview and post.text_preview != "(без текста)":
                preview = (
                    post.text_preview[:150] + "..."
                    if len(post.text_preview) > 150
                    else post.text_preview
                )
                print(f"   📝 {preview}")

            print(f"   🔗 {post.url}")

        print("\n" + "=" * 80)

        # Статистика
        if len(posts) > 0:
            total_forwards = sum(p.forwards for p in posts)
            avg_forwards = total_forwards / len(posts)
            max_forwards = posts[0].forwards

            print("\n📈 СТАТИСТИКА:")
            print(f"   Всего постов с репостами: {len(posts)}")
            print(f"   Максимум репостов: {max_forwards:,}")
            print(f"   Среднее репостов: {avg_forwards:.1f}")
            print(f"   Сумма репостов: {total_forwards:,}")
            print("=" * 80 + "\n")


def load_config():
    """Load Telegram credentials from environment and a local session file."""
    return load_telegram_config(SCRIPT_DIR)


async def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="Анализ топ постов канала по количеству репостов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python top_posts_analyzer.py demo_analytics_channel
  python top_posts_analyzer.py t.me/demo_analytics_channel --limit 500 --top 20
  python top_posts_analyzer.py demo_analytics_channel --min-forwards 10 --sort-by views
        """,
    )
    parser.add_argument(
        "channel",
        help="Канал для анализа (username или ссылка, например: demo_analytics_channel или t.me/demo_analytics_channel)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Максимальное количество постов для анализа (по умолчанию: 1000)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Количество топ постов для отображения (по умолчанию: 10)",
    )
    parser.add_argument(
        "--min-forwards",
        type=int,
        default=0,
        help="Минимальное количество репостов для фильтрации (по умолчанию: 0)",
    )
    parser.add_argument(
        "--sort-by",
        choices=["forwards", "views", "engagement_rate"],
        default="forwards",
        help="Поле для сортировки (по умолчанию: forwards)",
    )
    parser.add_argument("--no-csv", action="store_true", help="Не сохранять CSV файл")
    parser.add_argument("--no-json", action="store_true", help="Не сохранять JSON файл")
    parser.add_argument(
        "--auto-llm-analysis",
        action="store_true",
        help="Автоматически запустить LLM анализ топ-20 постов после завершения",
    )

    args = parser.parse_args()

    try:
        # Загрузка конфигурации
        print("⚙️ Загрузка конфигурации...")
        config = load_config()

        # Путь к сессии
        session_path = str(config["session_path"])

        # Инициализация анализатора
        analyzer = TopPostsAnalyzer(
            session_path=session_path,
            api_id=config["api_id"],
            api_hash=config["api_hash"],
        )

        # Подключение
        await analyzer.connect()

        # Получение информации о канале
        channel_username = analyzer._resolve_channel(args.channel)
        print(f"📺 Анализ канала: {channel_username}")

        channel_info = await analyzer.get_channel_info(channel_username)
        print(f"   Название: {channel_info['title']}")
        print(f"   Подписчиков: {channel_info['subscribers']:,}")

        # Сбор метаданных
        posts = await analyzer.collect_posts_metadata(
            channel_entity=channel_info["entity"],
            limit=args.limit,
            subscribers=channel_info["subscribers"],
            min_forwards=args.min_forwards,
        )

        if not posts:
            print("❌ Не найдено постов, соответствующих критериям")
            await analyzer.disconnect()
            return

        # Ранжирование
        ranked_posts = analyzer.rank_posts(posts, sort_by=args.sort_by)

        # Вывод отчета
        analyzer.print_top_report(ranked_posts, channel_info["title"], top_n=args.top)

        # Сохранение результатов
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"top_posts_{channel_username}_{timestamp}"

        if not args.no_csv:
            analyzer.save_to_csv(ranked_posts, f"{base_filename}.csv")

        if not args.no_json:
            analyzer.save_to_json(ranked_posts, f"{base_filename}.json")

        # Отключение
        await analyzer.disconnect()
        print("\n✅ Анализ завершен!")

        # Автоматический запуск LLM анализа, если запрошено
        if args.auto_llm_analysis:
            print("\n" + "=" * 80)
            print("🤖 Автоматический запуск LLM анализа...")
            print("=" * 80 + "\n")

            try:
                import subprocess

                json_filename = f"{base_filename}.json"
                json_path = LOG_DIR / json_filename

                if json_path.exists():
                    cmd = [
                        sys.executable,
                        str(SCRIPT_DIR / "top_posts_analyzer_L2.py"),
                        "--json-path",
                        str(json_path),
                    ]
                    # Fixed interpreter/script; JSON path is produced by this parser.
                    subprocess.run(cmd, check=False)  # noqa: S603
                else:
                    print(f"⚠️ JSON файл не найден: {json_path}")
            except Exception as e:
                print(f"⚠️ Ошибка при запуске LLM анализа: {e}")

    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
