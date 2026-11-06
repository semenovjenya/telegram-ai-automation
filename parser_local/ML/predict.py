"""
Скрипт для предсказания вирусности постов с использованием обученной модели.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Добавляем родительскую папку в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from ML.data_loader import DataLoader  # noqa: E402
from ML.feature_engineering import FeatureEngineer  # noqa: E402
from ML.models import ViralPostPredictor  # noqa: E402

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_latest_model(models_dir: Path) -> ViralPostPredictor:
    """
    Загрузить последнюю обученную модель

    Args:
        models_dir: Директория с моделями

    Returns:
        Загруженный предсказатель
    """
    model_files = list(models_dir.glob("viral_predictor_*.pkl"))

    if not model_files:
        raise FileNotFoundError(f"Не найдено моделей в {models_dir}")

    # Берем последнюю по времени
    latest_model = max(model_files, key=lambda p: p.stat().st_mtime)

    predictor = ViralPostPredictor()
    predictor.load(latest_model, trusted_dir=models_dir)

    logger.info(f"✅ Модель загружена: {latest_model.name}")

    return predictor


def predict_viral_potential(
    predictor: ViralPostPredictor,
    data_loader: DataLoader,
    feature_engineer: FeatureEngineer,
    json_path: Path = None,
    csv_path: Path = None,
) -> pd.DataFrame:
    """
    Предсказать вирусный потенциал постов

    Args:
        predictor: Обученный предсказатель
        data_loader: Загрузчик данных
        feature_engineer: Feature engineer
        json_path: Путь к JSON с постами (опционально)
        csv_path: Путь к CSV с анализом канала (опционально)

    Returns:
        DataFrame с предсказаниями
    """
    logger.info("📥 Загрузка данных...")

    # Загружаем данные
    df = data_loader.load_combined_data(json_path=json_path, csv_path=csv_path)

    logger.info("🔧 Создание признаков...")

    # Создаем признаки
    df = feature_engineer.create_all_features(df)

    logger.info("🎯 Подготовка данных для предсказания...")

    # Выбираем признаки (те же, что использовались при обучении)
    X, _ = feature_engineer.select_features(df, target_col="forwards")

    # Предсказания
    logger.info("🔮 Генерация предсказаний...")
    predictions = predictor.predict(X)

    # Добавляем предсказания к исходным данным
    result_df = df.copy()
    result_df["predicted_forwards"] = predictions.astype(int)
    result_df["predicted_forwards"] = result_df["predicted_forwards"].clip(
        lower=0,
    )

    # Сортируем по предсказанным репостам
    result_df = result_df.sort_values("predicted_forwards", ascending=False)

    logger.info(f"✅ Предсказания сгенерированы для {len(result_df)} постов")

    return result_df


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="Предсказание вирусности постов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Предсказать вирусность последних постов
  python predict.py

  # Указать конкретный файл с постами
  python predict.py --json-path ../Logs/top_posts_example_YYYYMMDD_HHMMSS.json

  # Указать конкретную модель
  python predict.py --model-path viral_predictor_random_forest_YYYYMMDD_HHMMSS.pkl
        """,
    )

    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help=(
            "Имя доверенного локального файла в ML/models "
            "(по умолчанию: последняя модель)"
        ),
    )

    parser.add_argument(
        "--json-path",
        type=str,
        default=None,
        help="Путь к JSON файлу с постами (опционально)",
    )

    parser.add_argument(
        "--csv-path",
        type=str,
        default=None,
        help="Путь к CSV файлу с анализом канала (опционально)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Путь для сохранения результатов (опционально)",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Показать топ-N постов по предсказанной вирусности (по умолчанию: 10)",
    )

    args = parser.parse_args()

    try:
        base_dir = Path(__file__).parent.parent
        models_dir = Path(__file__).parent / "models"
        results_dir = Path(__file__).parent / "results"

        # Загрузка модели
        if args.model_path:
            if Path(args.model_path).name != args.model_path:
                raise ValueError(
                    "--model-path accepts only a filename from parser_local/ML/models"
                )
            predictor = ViralPostPredictor()
            predictor.load(
                models_dir / args.model_path,
                trusted_dir=models_dir,
            )
        else:
            predictor = load_latest_model(models_dir)

        logger.info(f"📊 Модель: {predictor.model_type}")
        logger.info(f"📊 Признаков: {len(predictor.feature_names)}")

        # Инициализация компонентов
        data_loader = DataLoader(base_dir=base_dir)
        feature_engineer = FeatureEngineer()

        # Предсказания
        json_path = Path(args.json_path) if args.json_path else None
        csv_path = Path(args.csv_path) if args.csv_path else None

        result_df = predict_viral_potential(
            predictor,
            data_loader,
            feature_engineer,
            json_path=json_path,
            csv_path=csv_path,
        )

        # Вывод топ постов
        logger.info(f"\n{'=' * 80}")
        logger.info(f"🏆 ТОП-{args.top} ПОСТОВ ПО ПРЕДСКАЗАННОЙ ВИРУСНОСТИ")
        logger.info(f"{'=' * 80}\n")

        top_posts = result_df[
            [
                "post_id",
                "date",
                "predicted_forwards",
                "forwards",
                "views",
                "text_preview",
                "url",
            ]
        ].head(args.top)

        for idx, (_, row) in enumerate(top_posts.iterrows(), 1):
            print(f"\n📌 #{idx}")
            print(f"   Пост ID: {row['post_id']}")
            print(f"   Предсказано репостов: {row['predicted_forwards']}")
            if "forwards" in row and pd.notna(row["forwards"]):
                print(f"   Фактически репостов: {int(row['forwards'])}")
            print(f"   Просмотров: {row['views']}")
            print(f"   Дата: {row['date']}")
            if pd.notna(row["text_preview"]) and row["text_preview"] != "(без текста)":
                full_preview = str(row["text_preview"])
                preview = (
                    full_preview[:100] + "..."
                    if len(full_preview) > 100
                    else full_preview
                )
                print(f"   Текст: {preview}")
            print(f"   URL: {row['url']}")

        # Сохранение результатов
        output_path = args.output
        if output_path is None:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = results_dir / f"predictions_{timestamp}.csv"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Сохраняем только нужные колонки
        output_cols = [
            "post_id",
            "date",
            "predicted_forwards",
            "forwards",
            "views",
            "replies",
            "reactions",
            "text_preview",
            "url",
        ]
        available_cols = [col for col in output_cols if col in result_df.columns]

        result_df[available_cols].to_csv(output_path, index=False, encoding="utf-8")
        logger.info(f"\n💾 Результаты сохранены: {output_path}")

        logger.info("\n✅ Предсказания завершены успешно!")

    except Exception as e:
        logger.error(f"\n❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
