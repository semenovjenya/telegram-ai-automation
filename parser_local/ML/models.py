"""
Модуль с ML моделями для предсказания вирусности постов.
"""

import logging
import pickle
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from .artifact_security import (
    MODEL_ARTIFACT_VERSION,
    MODEL_FEATURE_POLICY,
    resolve_trusted_model_path,
)

logger = logging.getLogger(__name__)


class ViralPostPredictor:
    """Класс для предсказания вирусности постов"""

    def __init__(self, model_type: str = "random_forest"):
        """
        Инициализация предсказателя

        Args:
            model_type: Тип модели ('random_forest', 'xgboost', 'lightgbm')
        """
        self.model_type = model_type
        self.model = None
        self.feature_names = []
        self.scaler = None
        self.is_trained = False

    def _create_model(self):
        """Создание модели в зависимости от типа"""
        if self.model_type == "random_forest":
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            )
        elif self.model_type == "xgboost":
            self.model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
            )
        elif self.model_type == "lightgbm":
            self.model = lgb.LGBMRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
                verbose=-1,
            )
        else:
            raise ValueError(f"Неизвестный тип модели: {self.model_type}")

    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        validation_split: float = 0.2,
        random_state: int = 42,
    ) -> dict:
        """
        Обучение модели

        Args:
            X: Признаки
            y: Целевая переменная
            validation_split: Доля данных для валидации
            random_state: Random state для воспроизводимости

        Returns:
            Словарь с метриками обучения
        """
        if self.model is None:
            self._create_model()

        self.feature_names = list(X.columns)

        # Разделение на train/validation
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=validation_split, random_state=random_state
        )

        logger.info(f"Обучение модели {self.model_type}...")
        logger.info(f"Train size: {len(X_train)}, Validation size: {len(X_val)}")

        # Обучение
        self.model.fit(X_train, y_train)
        self.is_trained = True

        # Предсказания и метрики
        y_train_pred = self.model.predict(X_train)
        y_val_pred = self.model.predict(X_val)

        metrics = {
            "train": {
                "mse": mean_squared_error(y_train, y_train_pred),
                "rmse": np.sqrt(mean_squared_error(y_train, y_train_pred)),
                "mae": mean_absolute_error(y_train, y_train_pred),
                "r2": r2_score(y_train, y_train_pred),
            },
            "validation": {
                "mse": mean_squared_error(y_val, y_val_pred),
                "rmse": np.sqrt(mean_squared_error(y_val, y_val_pred)),
                "mae": mean_absolute_error(y_val, y_val_pred),
                "r2": r2_score(y_val, y_val_pred),
            },
        }

        logger.info("✅ Модель обучена!")
        logger.info(f"Train R²: {metrics['train']['r2']:.4f}")
        logger.info(f"Validation R²: {metrics['validation']['r2']:.4f}")
        logger.info(f"Validation RMSE: {metrics['validation']['rmse']:.2f}")

        return metrics

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Предсказание

        Args:
            X: Признаки

        Returns:
            Предсказания
        """
        if not self.is_trained:
            raise ValueError("Модель не обучена! Сначала вызовите train()")

        return self.model.predict(X)

    def get_feature_importance(self) -> pd.DataFrame:
        """
        Получить важность признаков

        Returns:
            DataFrame с важностью признаков
        """
        if not self.is_trained:
            raise ValueError("Модель не обучена!")

        if hasattr(self.model, "feature_importances_"):
            importances = self.model.feature_importances_
        else:
            raise ValueError(
                f"Модель {self.model_type} не поддерживает feature_importances_"
            )

        feature_importance = pd.DataFrame(
            {"feature": self.feature_names, "importance": importances}
        ).sort_values("importance", ascending=False)

        return feature_importance

    def save(self, filepath: Path):
        """
        Сохранить модель

        Args:
            filepath: Путь для сохранения
        """
        if not self.is_trained:
            raise ValueError("Модель не обучена!")

        model_data = {
            "artifact_version": MODEL_ARTIFACT_VERSION,
            "feature_policy": MODEL_FEATURE_POLICY,
            "model": self.model,
            "model_type": self.model_type,
            "feature_names": self.feature_names,
            "is_trained": self.is_trained,
        }

        with open(filepath, "wb") as f:
            pickle.dump(model_data, f)

        logger.info(f"✅ Модель сохранена: {filepath}")

    def load(self, filepath: Path, *, trusted_dir: Path):
        """
        Загрузить модель

        Args:
            filepath: Путь к локальному файлу модели
            trusted_dir: Единственная директория доверенных model artifacts
        """
        filepath = resolve_trusted_model_path(filepath, trusted_dir)
        logger.warning(
            "Loading trusted-local pickle model %s. Pickle files can execute "
            "code and must never come from downloads or untrusted users.",
            filepath.name,
        )
        with open(filepath, "rb") as f:
            model_data = pickle.load(f)  # noqa: S301 - trusted path enforced above

        if (
            not isinstance(model_data, dict)
            or model_data.get("artifact_version") != MODEL_ARTIFACT_VERSION
            or model_data.get("feature_policy") != MODEL_FEATURE_POLICY
        ):
            raise ValueError(
                "Legacy or incompatible model artifact; retrain with the current "
                "pre-publication feature policy"
            )

        self.model = model_data["model"]
        self.model_type = model_data["model_type"]
        self.feature_names = model_data["feature_names"]
        self.is_trained = model_data["is_trained"]

        logger.info(f"✅ Модель загружена: {filepath}")


class ModelComparator:
    """Класс для сравнения разных моделей"""

    def __init__(self):
        """Инициализация компаратора"""
        self.models = {}
        self.results = {}

    def compare_models(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        models: tuple[str, ...] = ("random_forest", "xgboost", "lightgbm"),
        validation_split: float = 0.2,
    ) -> pd.DataFrame:
        """
        Сравнить разные модели

        Args:
            X: Признаки
            y: Целевая переменная
            models: Список типов моделей для сравнения
            validation_split: Доля данных для валидации

        Returns:
            DataFrame с результатами сравнения
        """
        results = []

        for model_type in models:
            logger.info(f"\n{'=' * 50}")
            logger.info(f"Обучение модели: {model_type}")
            logger.info(f"{'=' * 50}")

            predictor = ViralPostPredictor(model_type=model_type)
            metrics = predictor.train(X, y, validation_split=validation_split)

            self.models[model_type] = predictor

            results.append(
                {
                    "model": model_type,
                    "train_r2": metrics["train"]["r2"],
                    "val_r2": metrics["validation"]["r2"],
                    "val_rmse": metrics["validation"]["rmse"],
                    "val_mae": metrics["validation"]["mae"],
                }
            )

        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values("val_r2", ascending=False)

        self.results = results_df

        logger.info(f"\n{'=' * 50}")
        logger.info("РЕЗУЛЬТАТЫ СРАВНЕНИЯ МОДЕЛЕЙ:")
        logger.info(f"{'=' * 50}")
        print(results_df.to_string(index=False))

        return results_df

    def get_best_model(self) -> tuple[str, ViralPostPredictor]:
        """
        Получить лучшую модель

        Returns:
            Tuple (тип модели, объект модели)
        """
        if not self.results.empty:
            best_model_type = self.results.iloc[0]["model"]
            return best_model_type, self.models[best_model_type]
        else:
            raise ValueError("Модели еще не сравнены!")
