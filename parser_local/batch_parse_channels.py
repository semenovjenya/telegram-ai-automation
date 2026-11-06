"""
Пакетная обработка каналов из CSV файла через local_parser.py
"""

import csv
import logging
import sys
import time
from pathlib import Path

# Добавляем путь к модулю local_parser
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from local_parser import load_config, process_channel  # noqa: E402
from runtime_config import resolve_channels_csv_path  # noqa: E402

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(SCRIPT_DIR / "Logs" / "batch_parse.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def read_channels_from_csv(csv_path: Path) -> list[dict[str, str]]:
    """Чтение списка каналов из CSV файла"""
    channels = []
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                username = row.get("username", "").strip()
                if username:
                    channels.append(
                        {
                            "id": row.get("id", ""),
                            "username": username,
                            "title": row.get("title", ""),
                            "subscribers": row.get("subscribers", ""),
                            "engagement_rate": row.get("engagement_rate", ""),
                        }
                    )
        logger.info(f"Прочитано {len(channels)} каналов из {csv_path}")
        return channels
    except Exception as e:
        logger.error(f"Ошибка при чтении CSV: {e}")
        raise


def batch_process_channels(csv_path: Path, delay: int = 5):
    """
    Пакетная обработка каналов из CSV файла

    Args:
        csv_path: Путь к CSV файлу с каналами
        delay: Задержка между обработкой каналов (секунды)
    """
    # Загружаем конфигурацию
    try:
        cfg = load_config()
        logger.info("Конфигурация загружена успешно")
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации: {e}")
        sys.exit(1)

    # Читаем каналы из CSV
    try:
        channels = read_channels_from_csv(csv_path)
    except Exception as e:
        logger.error(f"Не удалось прочитать каналы: {e}")
        sys.exit(1)

    if not channels:
        logger.warning("Список каналов пуст")
        return

    # Статистика
    total = len(channels)
    successful = 0
    failed = 0
    failed_channels = []

    logger.info(f"Начинаем обработку {total} каналов...")
    print(f"\n{'=' * 60}")
    print(f"Пакетная обработка {total} каналов")
    print(f"{'=' * 60}\n")

    # Обрабатываем каждый канал
    for idx, channel in enumerate(channels, 1):
        username = channel["username"]
        title = channel.get("title", "")

        print(f"\n[{idx}/{total}] Обработка: @{username} - {title}")
        logger.info(f"[{idx}/{total}] Обработка канала @{username}")

        try:
            # Формируем ссылку на канал
            channel_link = f"t.me/{username}"

            # Обрабатываем канал
            process_channel(cfg, channel_link)

            successful += 1
            logger.info(f"[{idx}/{total}] ✅ Успешно обработан: @{username}")
            print(f"✅ Успешно обработан: @{username}")

        except KeyboardInterrupt:
            logger.warning("Обработка прервана пользователем")
            print("\n⚠️ Обработка прервана пользователем")
            break

        except Exception as e:
            failed += 1
            failed_channels.append(
                {"username": username, "title": title, "error": str(e)}
            )
            logger.error(f"[{idx}/{total}] ❌ Ошибка при обработке @{username}: {e}")
            print(f"❌ Ошибка: {e}")

        # Задержка между каналами (кроме последнего)
        if idx < total and delay > 0:
            print(f"⏳ Пауза {delay} секунд перед следующим каналом...")
            time.sleep(delay)

    # Итоговая статистика
    print(f"\n{'=' * 60}")
    print("ИТОГИ ОБРАБОТКИ")
    print(f"{'=' * 60}")
    print(f"Всего каналов: {total}")
    print(f"✅ Успешно: {successful}")
    print(f"❌ Ошибок: {failed}")

    if failed_channels:
        print("\n❌ Каналы с ошибками:")
        for ch in failed_channels:
            print(f"  - @{ch['username']} ({ch['title']}): {ch['error']}")

    logger.info(f"Обработка завершена. Успешно: {successful}, Ошибок: {failed}")


def main():
    """Главная функция"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Пакетная обработка каналов из CSV файла",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python batch_parse_channels.py ../vector_search/channels.csv
  python batch_parse_channels.py ../vector_search/channels.csv --delay 10
        """,
    )

    parser.add_argument(
        "csv_file",
        help="Путь к CSV файлу с каналами (должен содержать колонку 'username')",
    )

    parser.add_argument(
        "--delay",
        type=int,
        default=5,
        help="Задержка между обработкой каналов в секундах (по умолчанию: 5)",
    )

    args = parser.parse_args()

    # Проверяем существование файла
    csv_path = resolve_channels_csv_path(Path(args.csv_file))

    if not csv_path.exists():
        logger.error(f"CSV файл не найден: {csv_path}")
        print(f"\n❌ Ошибка: CSV файл не найден: {csv_path}")
        sys.exit(1)

    try:
        batch_process_channels(csv_path, delay=args.delay)
    except KeyboardInterrupt:
        logger.warning("Прервано пользователем")
        print("\n⚠️ Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
