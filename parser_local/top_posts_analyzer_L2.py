"""
Скрипт для глубокого LLM анализа топ-20 самых репощенных постов за последний месяц.
Автоматически запускается после top_posts_analyzer.py или может быть вызван отдельно.
"""

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from openai import OpenAI

if __package__:
    from .csv_safety import neutralize_csv_row
    from .runtime_config import load_openai_config
else:
    from csv_safety import neutralize_csv_row
    from runtime_config import load_openai_config

# Настройка путей
SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "Logs"
LOG_DIR.mkdir(exist_ok=True)


@dataclass
class LLMAnalysis:
    """Результат глубокого LLM анализа поста"""

    post_id: int
    date: str
    forwards: int
    views: int

    # Анализ контента
    content_analysis: str  # Глубокий анализ содержания поста
    viral_factors: str  # Факторы вирусности
    target_audience: str  # Целевая аудитория
    content_type: str  # Тип контента (мем, анонс, личное и т.д.)
    emotional_tone: str  # Эмоциональная тональность

    # Рекомендации
    recommendations: str  # Рекомендации для улучшения
    similar_content_suggestions: str  # Предложения похожего контента

    # Метаданные
    text_preview: str
    url: str
    analysis_timestamp: str


class TopPostsLLMAnalyzer:
    """Глубокий LLM анализатор топ постов"""

    def __init__(self, openai_api_key: str, openai_model: str = "gpt-4o"):
        """
        Инициализация анализатора

        Args:
            openai_api_key: OpenAI API ключ
            openai_model: Модель OpenAI (по умолчанию: gpt-4o)
        """
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.openai_model = openai_model

    def create_analysis_prompt(self, post_data: dict) -> str:
        """
        Создание промпта для глубокого анализа поста

        Args:
            post_data: Данные о посте

        Returns:
            Промпт для LLM
        """
        # Используем полный текст, если есть, иначе превью
        text = post_data.get("text_full") or post_data.get("text_preview", "")
        forwards = post_data.get("forwards", 0)
        views = post_data.get("views", 0)
        replies = post_data.get("replies", 0)
        reactions = post_data.get("reactions", 0)
        engagement_rate = post_data.get("engagement_rate", 0)

        content_types = []
        if post_data.get("has_photo"):
            content_types.append("фото")
        if post_data.get("has_video"):
            content_types.append("видео")
        if post_data.get("has_audio"):
            content_types.append("аудио")
        if post_data.get("has_voice"):
            content_types.append("голосовое сообщение")
        if post_data.get("has_document"):
            content_types.append("документ")
        if post_data.get("has_poll"):
            content_types.append("опрос")

        prompt = f"""Проведи глубокий анализ этого поста из Telegram канала. Пост получил {forwards} репостов при {views} просмотрах (engagement rate: {engagement_rate}%).

ДАННЫЕ ПОСТА:
- Текст: {text[:2000] if text else "(без текста)"}
- Типы контента: {", ".join(content_types) if content_types else "только текст"}
- Репосты: {forwards}
- Просмотры: {views}
- Ответы: {replies}
- Реакции: {reactions}
- Дата: {post_data.get("date", "Unknown")}

ПРОВЕДИ АНАЛИЗ ПО СЛЕДУЮЩИМ КАТЕГОРИЯМ:

1. **Глубокий анализ содержания** (2-3 предложения):
   - О чем этот пост? Какую основную мысль или эмоцию передает?
   - Какие элементы делают его интересным?

2. **Факторы вирусности** (конкретные причины, почему пост стал вирусным):
   - Что именно привлекло внимание?
   - Какие эмоции вызывает?
   - Что заставило людей репостить?

3. **Целевая аудитория**:
   - Кому этот пост адресован?
   - Какие интересы/ценности аудитории он отражает?

4. **Тип контента** (одно слово или короткая фраза):
   - Например: мем, анонс, личное, шутка, обзор, новость и т.д.

5. **Эмоциональная тональность**:
   - Какие эмоции передает? (юмор, ирония, грусть, вдохновение и т.д.)

6. **Рекомендации для улучшения**:
   - Как можно было бы улучшить пост для еще большей вирусности?
   - Что добавить/изменить?

7. **Предложения похожего контента**:
   - Какие похожие посты можно создать?
   - Какие темы/форматы повторить?

Верни ответ в формате JSON со следующими ключами:
{{
  "content_analysis": "...",
  "viral_factors": "...",
  "target_audience": "...",
  "content_type": "...",
  "emotional_tone": "...",
  "recommendations": "...",
  "similar_content_suggestions": "..."
}}
"""
        return prompt

    def analyze_post_with_llm(self, post_data: dict) -> dict:
        """
        Анализ одного поста через LLM

        Args:
            post_data: Данные о посте

        Returns:
            Словарь с результатами анализа
        """
        try:
            prompt = self.create_analysis_prompt(post_data)

            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Ты эксперт по анализу контента в социальных сетях и маркетингу. "
                        "Проводишь глубокий анализ вирусных постов, выявляешь факторы успеха "
                        "и даешь практические рекомендации. Отвечай на русском языке.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )

            content = response.choices[0].message.content.strip()

            # Парсим JSON из ответа
            # Убираем markdown форматирование если есть
            content = re.sub(
                r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE
            )

            try:
                analysis_data = json.loads(content)
            except json.JSONDecodeError:
                # Если не JSON, создаем структурированный ответ
                analysis_data = {
                    "content_analysis": content[:500]
                    if content
                    else "Не удалось проанализировать",
                    "viral_factors": "Требуется ручной анализ",
                    "target_audience": "Не определено",
                    "content_type": "Не определено",
                    "emotional_tone": "Не определено",
                    "recommendations": "Требуется дополнительный анализ",
                    "similar_content_suggestions": "Требуется дополнительный анализ",
                }

            return analysis_data

        except Exception as e:
            print(f"⚠️ Ошибка при анализе поста {post_data.get('post_id', '?')}: {e}")
            return {
                "content_analysis": f"Ошибка анализа: {str(e)}",
                "viral_factors": "",
                "target_audience": "",
                "content_type": "",
                "emotional_tone": "",
                "recommendations": "",
                "similar_content_suggestions": "",
            }

    def filter_posts_by_month(self, posts: list[dict], months: int = 1) -> list[dict]:
        """
        Фильтрация постов за последние N месяцев

        Args:
            posts: Список постов
            months: Количество месяцев (по умолчанию: 1)

        Returns:
            Отфильтрованные посты
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=30 * months)

        filtered = []
        for post in posts:
            try:
                post_date = datetime.fromtimestamp(
                    post.get("date_timestamp", 0), tz=UTC
                )
                if post_date >= cutoff_date:
                    filtered.append(post)
            except (TypeError, ValueError, OSError, OverflowError):
                # Пробуем парсить строку даты
                try:
                    post_date_str = post.get("date", "")
                    post_date = datetime.strptime(
                        post_date_str, "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=UTC)
                    if post_date >= cutoff_date:
                        filtered.append(post)
                except (TypeError, ValueError):  # noqa: S112 - skip invalid input date
                    continue

        return filtered

    def get_top_posts_by_forwards(
        self, posts: list[dict], top_n: int = 20
    ) -> list[dict]:
        """
        Получить топ-N постов по количеству репостов

        Args:
            posts: Список постов
            top_n: Количество топ постов

        Returns:
            Отсортированные посты
        """
        sorted_posts = sorted(posts, key=lambda x: x.get("forwards", 0), reverse=True)
        return sorted_posts[:top_n]

    def get_top_post_by_forwards(self, posts: list[dict]) -> dict | None:
        """
        Получить самый репощеный пост (топ-1)

        Args:
            posts: Список постов

        Returns:
            Самый репощеный пост или None
        """
        if not posts:
            return None
        return max(posts, key=lambda x: x.get("forwards", 0))

    def parse_channel_from_url(self, url: str) -> dict[str, str | int | None]:
        """
        Парсинг URL поста для извлечения данных канала

        Args:
            url: URL поста (например: https://t.me/demo_analytics_channel/43853)

        Returns:
            Словарь с source_channel, source_channel_id и message_id
        """
        # Формат: https://t.me/username/post_id или https://t.me/c/channel_id/post_id
        if "/c/" in url:
            # Приватный канал
            parts = url.split("/c/")[1].split("/")
            channel_id_str = parts[0]
            message_id = (
                int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            )
            # Для приватных каналов ID в URL без префикса -100
            channel_id = int(channel_id_str) if channel_id_str.isdigit() else None
            return {
                "source_channel": None,
                "source_channel_id": channel_id,
                "message_id": message_id,
            }
        else:
            # Публичный канал
            parts = (
                url.replace("https://t.me/", "").replace("http://t.me/", "").split("/")
            )
            username = parts[0] if parts else None
            message_id = (
                int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            )
            return {
                "source_channel": username,
                "source_channel_id": None,
                "message_id": message_id,
            }

    def save_forward_data_json(self, post: dict, target_channel: str, filename: str):
        """
        Сохранение данных для репоста в минималистичном JSON формате

        Args:
            post: Данные поста
            target_channel: Целевой канал для репоста
            filename: Имя файла для сохранения
        """
        filepath = LOG_DIR / filename

        # Парсим URL для получения данных канала
        url = post.get("url", "")
        channel_data = self.parse_channel_from_url(url)

        data = {
            "forward_post": {
                "source_channel": channel_data["source_channel"],
                "source_channel_id": channel_data["source_channel_id"],
                "message_id": channel_data["message_id"],
                "target_channel": target_channel,
            },
            "post_info": {
                "forwards": post.get("forwards", 0),
                "views": post.get("views", 0),
                "url": url,
                "date": post.get("date", ""),
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"💾 Сохранены данные для репоста: {filepath}")

    def load_latest_posts_json(self, json_path: Path | None = None) -> list[dict]:
        """
        Загрузить последний JSON файл с постами

        Args:
            json_path: Путь к JSON файлу (опционально)

        Returns:
            Список постов
        """
        if json_path is None:
            # Ищем последний JSON файл с топ постами
            json_files = list(LOG_DIR.glob("top_posts_*.json"))
            if not json_files:
                raise FileNotFoundError(f"Не найдено JSON файлов в {LOG_DIR}")
            json_path = max(json_files, key=lambda p: p.stat().st_mtime)
            print(f"📂 Используется файл: {json_path.name}")

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        posts = data.get("posts", [])
        if not posts:
            raise ValueError("JSON файл не содержит постов")

        print(f"✅ Загружено {len(posts)} постов из JSON")
        return posts

    def analyze_posts_batch(
        self, posts: list[dict], delay: float = 1.0
    ) -> list[LLMAnalysis]:
        """
        Анализ батча постов через LLM

        Args:
            posts: Список постов для анализа
            delay: Задержка между запросами (секунды)

        Returns:
            Список результатов анализа
        """
        results = []
        total = len(posts)

        print(f"\n🤖 Начало LLM анализа {total} постов...")
        print(f"⏱️  Примерное время: ~{total * (delay + 2)} секунд\n")

        for idx, post in enumerate(posts, 1):
            print(
                f"[{idx}/{total}] Анализ поста #{post.get('post_id', '?')} ({post.get('forwards', 0)} репостов)..."
            )

            analysis_data = self.analyze_post_with_llm(post)

            llm_analysis = LLMAnalysis(
                post_id=post.get("post_id", 0),
                date=post.get("date", ""),
                forwards=post.get("forwards", 0),
                views=post.get("views", 0),
                content_analysis=analysis_data.get("content_analysis", ""),
                viral_factors=analysis_data.get("viral_factors", ""),
                target_audience=analysis_data.get("target_audience", ""),
                content_type=analysis_data.get("content_type", ""),
                emotional_tone=analysis_data.get("emotional_tone", ""),
                recommendations=analysis_data.get("recommendations", ""),
                similar_content_suggestions=analysis_data.get(
                    "similar_content_suggestions", ""
                ),
                text_preview=post.get("text_preview", "")[:200],
                url=post.get("url", ""),
                analysis_timestamp=datetime.now(UTC).isoformat(),
            )

            results.append(llm_analysis)

            # Задержка между запросами
            if idx < total:
                time.sleep(delay)

        print(f"\n✅ LLM анализ завершен для {len(results)} постов")
        return results

    def save_analysis_to_json(self, analyses: list[LLMAnalysis], filename: str):
        """Сохранение анализа в JSON"""
        filepath = LOG_DIR / filename
        data = {
            "generated_at": datetime.now(UTC).isoformat(),
            "total_analyzed": len(analyses),
            "analyses": [asdict(analysis) for analysis in analyses],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"💾 Сохранено в JSON: {filepath}")

    def save_analysis_to_csv(self, analyses: list[LLMAnalysis], filename: str):
        """Сохранение анализа в CSV"""
        filepath = LOG_DIR / filename
        fieldnames = [
            "rank",
            "post_id",
            "date",
            "forwards",
            "views",
            "content_type",
            "emotional_tone",
            "target_audience",
            "viral_factors",
            "content_analysis",
            "recommendations",
            "similar_content_suggestions",
            "text_preview",
            "url",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for rank, analysis in enumerate(analyses, 1):
                writer.writerow(
                    neutralize_csv_row(
                        {
                            "rank": rank,
                            "post_id": analysis.post_id,
                            "date": analysis.date,
                            "forwards": analysis.forwards,
                            "views": analysis.views,
                            "content_type": analysis.content_type,
                            "emotional_tone": analysis.emotional_tone,
                            "target_audience": analysis.target_audience,
                            "viral_factors": analysis.viral_factors,
                            "content_analysis": analysis.content_analysis[
                                :500
                            ],  # Ограничиваем длину
                            "recommendations": analysis.recommendations[:500],
                            "similar_content_suggestions": analysis.similar_content_suggestions[
                                :500
                            ],
                            "text_preview": analysis.text_preview,
                            "url": analysis.url,
                        }
                    )
                )

        print(f"💾 Сохранено в CSV: {filepath}")

    def print_analysis_report(self, analyses: list[LLMAnalysis], top_n: int = 5):
        """Вывод отчета анализа"""
        print("\n" + "=" * 80)
        print(f"🧠 ГЛУБОКИЙ LLM АНАЛИЗ ТОП-{min(len(analyses), top_n)} ПОСТОВ")
        print("=" * 80)

        for rank, analysis in enumerate(analyses[:top_n], 1):
            print(f"\n{'=' * 80}")
            print(f"📌 #{rank} (ID: {analysis.post_id}) - {analysis.forwards} репостов")
            print(f"{'=' * 80}")
            print(f"📅 Дата: {analysis.date}")
            print(f"👁️  Просмотров: {analysis.views:,}")
            print(f"🔄 Репостов: {analysis.forwards}")
            print(f"\n📝 Текст: {analysis.text_preview}")

            print(f"\n🏷️  ТИП КОНТЕНТА: {analysis.content_type}")
            print(f"💭 ТОНАЛЬНОСТЬ: {analysis.emotional_tone}")
            print(f"🎯 АУДИТОРИЯ: {analysis.target_audience}")

            print("\n🔥 ФАКТОРЫ ВИРУСНОСТИ:")
            print(f"   {analysis.viral_factors}")

            print("\n📊 АНАЛИЗ СОДЕРЖАНИЯ:")
            print(f"   {analysis.content_analysis}")

            print("\n💡 РЕКОМЕНДАЦИИ:")
            print(f"   {analysis.recommendations}")

            print("\n🔄 ПОХОЖИЙ КОНТЕНТ:")
            print(f"   {analysis.similar_content_suggestions}")

            print(f"\n🔗 {analysis.url}")

        print(f"\n{'=' * 80}\n")


def load_config():
    """Load OpenAI settings from environment only."""
    return load_openai_config(SCRIPT_DIR)


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="Глубокий LLM анализ топ-20 самых репощенных постов за последний месяц",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Автоматический анализ последнего JSON файла
  python top_posts_analyzer_L2.py

  # Указать конкретный файл
  python top_posts_analyzer_L2.py --json-path Logs/top_posts_example_YYYYMMDD_HHMMSS.json

  # Изменить количество месяцев или топ постов
  python top_posts_analyzer_L2.py --months 2 --top 30

  # Только создать JSON с данными для репоста (без LLM анализа)
  python top_posts_analyzer_L2.py --forward-to @my_channel --forward-only

  # LLM анализ + создать JSON с данными для репоста
  python top_posts_analyzer_L2.py --forward-to @my_channel
        """,
    )

    parser.add_argument(
        "--json-path",
        type=str,
        default=None,
        help="Путь к JSON файлу с постами (по умолчанию: последний файл)",
    )

    parser.add_argument(
        "--months",
        type=int,
        default=1,
        help="Количество месяцев для фильтрации (по умолчанию: 1)",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Количество топ постов для анализа (по умолчанию: 20)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Модель OpenAI (по умолчанию: из конфига)",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Задержка между запросами к OpenAI в секундах (по умолчанию: 1.0)",
    )

    parser.add_argument("--no-csv", action="store_true", help="Не сохранять CSV файл")

    parser.add_argument("--no-json", action="store_true", help="Не сохранять JSON файл")

    parser.add_argument(
        "--report-top",
        type=int,
        default=5,
        help="Количество постов для вывода в отчет (по умолчанию: 5)",
    )

    parser.add_argument(
        "--forward-to",
        type=str,
        default=None,
        help="Username или ID канала, куда отправить самый репощеный пост (например: @my_channel). Создаст JSON с данными для репоста.",
    )

    parser.add_argument(
        "--forward-only",
        action="store_true",
        help="Только создать JSON с данными для репоста, без LLM анализа",
    )

    args = parser.parse_args()

    try:
        print("⚙️ Загрузка конфигурации...")
        config = load_config()

        openai_key = config["openai_api_key"]
        openai_model = args.model or config.get("openai_model", "gpt-4o")

        if not openai_key:
            raise RuntimeError("❌ OpenAI API ключ не найден")

        print(f"✅ OpenAI модель: {openai_model}")

        # Инициализация анализатора
        analyzer = TopPostsLLMAnalyzer(
            openai_api_key=openai_key, openai_model=openai_model
        )

        # Загрузка постов
        json_path = Path(args.json_path) if args.json_path else None
        if json_path and not json_path.is_absolute():
            json_path = LOG_DIR / json_path.name

        posts = analyzer.load_latest_posts_json(json_path)

        # Фильтрация по последнему месяцу
        print(f"\n📅 Фильтрация постов за последние {args.months} месяц(ев)...")
        filtered_posts = analyzer.filter_posts_by_month(posts, months=args.months)
        print(f"✅ Найдено {len(filtered_posts)} постов за последний месяц")

        if not filtered_posts:
            print("❌ Нет постов за указанный период")
            return

        # Если нужен только репост (без LLM анализа)
        if args.forward_only and args.forward_to:
            print("\n🔄 Поиск самого репощеного поста...")
            top_post = analyzer.get_top_post_by_forwards(filtered_posts)

            if not top_post:
                print("❌ Не найден пост для репоста")
                return

            print(
                f"✅ Найден пост #{top_post.get('post_id')} с {top_post.get('forwards')} репостами"
            )
            print(f"   URL: {top_post.get('url')}")

            # Сохранение данных для репоста
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"forward_post_{timestamp}.json"
            analyzer.save_forward_data_json(top_post, args.forward_to, filename)

            print(f"\n✅ Данные для репоста сохранены в {filename}")
            return

        # Выбор топ постов
        print(f"\n🏆 Выбор топ-{args.top} самых репощенных постов...")
        top_posts = analyzer.get_top_posts_by_forwards(filtered_posts, top_n=args.top)
        print(f"✅ Выбрано {len(top_posts)} постов для анализа")

        if not top_posts:
            print("❌ Нет постов для анализа")
            return

        # LLM анализ
        analyses = analyzer.analyze_posts_batch(top_posts, delay=args.delay)

        # Вывод отчета
        analyzer.print_analysis_report(analyses, top_n=args.report_top)

        # Сохранение результатов
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"llm_analysis_top_posts_{timestamp}"

        if not args.no_json:
            analyzer.save_analysis_to_json(analyses, f"{base_filename}.json")

        if not args.no_csv:
            analyzer.save_analysis_to_csv(analyses, f"{base_filename}.csv")

        # Если указан целевой канал, сохраняем данные для репоста самого репощеного поста
        if args.forward_to:
            print("\n🔄 Поиск самого репощеного поста для репоста...")
            top_post = analyzer.get_top_post_by_forwards(filtered_posts)

            if top_post:
                forward_filename = f"forward_post_{timestamp}.json"
                analyzer.save_forward_data_json(
                    top_post, args.forward_to, forward_filename
                )
                print(f"✅ Данные для репоста сохранены в {forward_filename}")

        print("\n✅ Глубокий анализ завершен успешно!")

    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
