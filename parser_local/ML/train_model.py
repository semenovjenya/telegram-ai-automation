"""
Скрипт для обучения ML моделей предсказания вирусности постов.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Добавляем родительскую папку в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from ML.data_loader import DataLoader
from ML.feature_engineering import FeatureEngineer
from ML.models import ModelComparator, ViralPostPredictor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def train_single_model(
    data_loader: DataLoader,
    feature_engineer: FeatureEngineer,
    model_type: str = "random_forest",
    target_col: str = "forwards",
    validation_split: float = 0.2,
    save_model: bool = True,
    json_path: Path | None = None,
    csv_path: Path | None = None,
) -> ViralPostPredictor:
    """
    Обучение одной модели

    Args:
        data_loader: Загрузчик данных
        feature_engineer: Feature engineer
        model_type: Тип модели
        target_col: Целевая переменная
        validation_split: Доля валидации
        save_model: Сохранять ли модель
        json_path: JSON с постами; по умолчанию используется последний из Logs
        csv_path: CSV с анализом канала; по умолчанию последний из Logs

    Returns:
        Обученный предсказатель
    """
    logger.info(f"\n{'=' * 60}")
    logger.info(f"ОБУЧЕНИЕ МОДЕЛИ: {model_type.upper()}")
    logger.info(f"{'=' * 60}\n")

    # Загрузка данных
    logger.info("📥 Загрузка данных...")
    df = data_loader.load_combined_data(json_path=json_path, csv_path=csv_path)

    # Создание признаков
    logger.info("🔧 Создание признаков...")
    df = feature_engineer.create_all_features(df)

    # Выбор признаков
    logger.info("🎯 Выбор признаков...")
    X, feature_names = feature_engineer.select_features(df, target_col=target_col)
    y = df[target_col].copy()

    # Проверка на достаточность данных
    if len(df) < 10:
        logger.warning(f"⚠️ Мало данных для обучения: {len(df)} постов")
        logger.warning("Рекомендуется минимум 50+ постов для хорошего результата")

    # Обучение модели
    predictor = ViralPostPredictor(model_type=model_type)
    metrics = predictor.train(X, y, validation_split=validation_split)

    # Сохранение модели
    if save_model:
        models_dir = Path(__file__).parent / "models"
        models_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = f"viral_predictor_{model_type}_{timestamp}.pkl"
        model_path = models_dir / model_filename

        predictor.save(model_path)

        # Сохранение метрик
        metrics_path = models_dir / f"metrics_{model_type}_{timestamp}.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "model_type": model_type,
                    "target": target_col,
                    "timestamp": timestamp,
                    "metrics": metrics,
                    "n_samples": len(df),
                    "n_features": len(feature_names),
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        logger.info(f"💾 Модель сохранена: {model_path}")
        logger.info(f"💾 Метрики сохранены: {metrics_path}")

    # Важность признаков
    logger.info("\n📊 ТОП-10 ВАЖНЫХ ПРИЗНАКОВ:")
    feature_importance = predictor.get_feature_importance()
    print(feature_importance.head(10).to_string(index=False))

    # Сохранение важности признаков
    if save_model:
        importance_path = (
            models_dir / f"feature_importance_{model_type}_{timestamp}.csv"
        )
        feature_importance.to_csv(importance_path, index=False, encoding="utf-8")
        logger.info(f"💾 Важность признаков сохранена: {importance_path}")

    return predictor


def compare_all_models(
    data_loader: DataLoader,
    feature_engineer: FeatureEngineer,
    target_col: str = "forwards",
    validation_split: float = 0.2,
    save_results: bool = True,
    json_path: Path | None = None,
    csv_path: Path | None = None,
) -> ModelComparator:
    """
    Сравнение всех моделей

    Args:
        data_loader: Загрузчик данных
        feature_engineer: Feature engineer
        target_col: Целевая переменная
        validation_split: Доля валидации
        save_results: Сохранять ли результаты
        json_path: JSON с постами; по умолчанию используется последний из Logs
        csv_path: CSV с анализом канала; по умолчанию последний из Logs

    Returns:
        Компаратор моделей
    """
    logger.info(f"\n{'=' * 60}")
    logger.info("СРАВНЕНИЕ ВСЕХ МОДЕЛЕЙ")
    logger.info(f"{'=' * 60}\n")

    # Загрузка данных
    logger.info("📥 Загрузка данных...")
    df = data_loader.load_combined_data(json_path=json_path, csv_path=csv_path)

    # Создание признаков
    logger.info("🔧 Создание признаков...")
    df = feature_engineer.create_all_features(df)

    # Выбор признаков
    logger.info("🎯 Выбор признаков...")
    X, feature_names = feature_engineer.select_features(df, target_col=target_col)
    y = df[target_col].copy()

    # Сравнение моделей
    comparator = ModelComparator()
    results_df = comparator.compare_models(
        X,
        y,
        models=["random_forest", "xgboost", "lightgbm"],
        validation_split=validation_split,
    )

    # Сохранение результатов сравнения
    if save_results:
        results_dir = Path(__file__).parent / "results"
        results_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_path = results_dir / f"model_comparison_{timestamp}.csv"
        results_df.to_csv(results_path, index=False, encoding="utf-8")

        logger.info(f"\n💾 Результаты сравнения сохранены: {results_path}")

        # Сохранение лучшей модели
        best_model_type, best_model = comparator.get_best_model()
        models_dir = Path(__file__).parent / "models"
        model_path = models_dir / f"best_model_{best_model_type}_{timestamp}.pkl"
        best_model.save(model_path)
        logger.info(f"💾 Лучшая модель сохранена: {model_path}")

    return comparator


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="Обучение ML моделей для предсказания вирусности постов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Обучить одну модель (Random Forest)
  python train_model.py --model random_forest

  # Обучить XGBoost
  python train_model.py --model xgboost

  # Сравнить все модели
  python train_model.py --compare-all

  # Указать целевую переменную
  python train_model.py --model random_forest --target views
        """,
    )

    parser.add_argument(
        "--model",
        choices=["random_forest", "xgboost", "lightgbm"],
        default="random_forest",
        help="Тип модели для обучения (по умолчанию: random_forest)",
    )

    parser.add_argument(
        "--compare-all", action="store_true", help="Сравнить все модели"
    )

    parser.add_argument(
        "--target",
        default="forwards",
        choices=["forwards", "views", "replies", "reactions"],
        help="Целевая переменная (по умолчанию: forwards)",
    )

    parser.add_argument(
        "--validation-split",
        type=float,
        default=0.2,
        help="Доля данных для валидации (по умолчанию: 0.2)",
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

    args = parser.parse_args()

    try:
        # Инициализация компонентов
        base_dir = Path(__file__).parent.parent
        data_loader = DataLoader(base_dir=base_dir)
        feature_engineer = FeatureEngineer()
        json_path = Path(args.json_path).expanduser() if args.json_path else None
        csv_path = Path(args.csv_path).expanduser() if args.csv_path else None

        if args.compare_all:
            # Сравнение всех моделей
            comparator = compare_all_models(
                data_loader,
                feature_engineer,
                target_col=args.target,
                validation_split=args.validation_split,
                save_results=True,
                json_path=json_path,
                csv_path=csv_path,
            )

            best_model_type, best_model = comparator.get_best_model()
            logger.info(f"\n🏆 ЛУЧШАЯ МОДЕЛЬ: {best_model_type}")

        else:
            # Обучение одной модели
            train_single_model(
                data_loader,
                feature_engineer,
                model_type=args.model,
                target_col=args.target,
                validation_split=args.validation_split,
                save_model=True,
                json_path=json_path,
                csv_path=csv_path,
            )

        logger.info("\n✅ Обучение завершено успешно!")

    except Exception as e:
        logger.error(f"\n❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
