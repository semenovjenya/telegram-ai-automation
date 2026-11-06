"""
Модуль для создания и обработки признаков для ML моделей.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Outcomes observed only after publication must never enter a model advertised
# as a pre-publication forecast. This includes direct outcomes and every feature
# derived from them.
POST_PUBLICATION_FEATURES = frozenset(
    {
        "views",
        "forwards",
        "replies",
        "reactions",
        "engagement_rate",
        "views_to_subscribers",
        "views_to_subscribers_ratio",
        "views_per_subscriber",
        "forwards_to_views",
        "forward_rate",
        "replies_to_views",
        "reactions_to_views",
        "total_engagement",
    }
)


class FeatureEngineer:
    """Класс для создания и обработки признаков"""

    def __init__(self):
        """Инициализация Feature Engineer"""
        self.feature_columns = []
        self.categorical_columns = []
        self.numerical_columns = []

    def create_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Создание временных признаков

        Args:
            df: DataFrame с колонкой 'date'

        Returns:
            DataFrame с добавленными временными признаками
        """
        df = df.copy()

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

            # Временные признаки
            df["hour"] = df["date"].dt.hour
            df["day_of_week"] = df["date"].dt.dayofweek
            df["day_of_month"] = df["date"].dt.day
            df["month"] = df["date"].dt.month
            df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)

            # Циклические признаки для часа и дня недели (sin/cos трансформация)
            df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
            df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
            df["day_of_week_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
            df["day_of_week_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

            # Часть дня
            df["is_morning"] = ((df["hour"] >= 6) & (df["hour"] < 12)).astype(int)
            df["is_afternoon"] = ((df["hour"] >= 12) & (df["hour"] < 18)).astype(int)
            df["is_evening"] = ((df["hour"] >= 18) & (df["hour"] < 22)).astype(int)
            df["is_night"] = ((df["hour"] >= 22) | (df["hour"] < 6)).astype(int)

        return df

    def create_content_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Создание признаков контента

        Args:
            df: DataFrame

        Returns:
            DataFrame с добавленными признаками контента
        """
        df = df.copy()

        # Типы контента (бинарные)
        content_cols = [
            "has_photo",
            "has_video",
            "has_audio",
            "has_voice",
            "has_document",
            "has_round_video",
            "has_poll",
        ]

        for col in content_cols:
            if col in df.columns:
                df[col] = df[col].astype(int)

        # Комбинированные признаки
        df["has_media"] = (
            df.get("has_photo", 0) | df.get("has_video", 0) | df.get("has_audio", 0)
        ).astype(int)

        df["has_visual"] = (
            df.get("has_photo", 0)
            | df.get("has_video", 0)
            | df.get("has_round_video", 0)
        ).astype(int)

        df["has_interactive"] = (df.get("has_poll", 0)).astype(int)

        # Количество типов контента
        df["content_types_count"] = df[content_cols].sum(axis=1)

        # Текстовые признаки
        if "text_length" in df.columns:
            df["text_length_log"] = np.log1p(df["text_length"])
            df["has_text"] = (df["text_length"] > 0).astype(int)
            df["text_length_category"] = pd.cut(
                df["text_length"],
                bins=[-np.inf, 0, 50, 150, 300, np.inf],
                labels=[0, 1, 2, 3, 4],
            ).astype(int)

        return df

    def create_engagement_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Создание признаков вовлеченности

        Args:
            df: DataFrame

        Returns:
            DataFrame с признаками вовлеченности
        """
        df = df.copy()

        # Отношения метрик
        if "views" in df.columns and "channel_subscribers" in df.columns:
            df["views_to_subscribers"] = df["views"] / (df["channel_subscribers"] + 1)
            df["views_per_subscriber"] = df["views_to_subscribers"]

        if "forwards" in df.columns and "views" in df.columns:
            df["forwards_to_views"] = df["forwards"] / (df["views"] + 1)
            df["forward_rate"] = df["forwards_to_views"]

        if "replies" in df.columns and "views" in df.columns:
            df["replies_to_views"] = df["replies"] / (df["views"] + 1)

        if "reactions" in df.columns and "views" in df.columns:
            df["reactions_to_views"] = df["reactions"] / (df["views"] + 1)

        # Комбинированная метрика вовлеченности
        engagement_cols = ["forwards", "replies", "reactions"]
        available_cols = [col for col in engagement_cols if col in df.columns]
        if available_cols:
            df["total_engagement"] = df[available_cols].sum(axis=1)

        return df

    def create_channel_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Создание признаков канала

        Args:
            df: DataFrame

        Returns:
            DataFrame с признаками канала
        """
        df = df.copy()

        # Нормализация метрик канала
        channel_cols = [
            "channel_subscribers",
            "channel_engagement_rate",
            "channel_avg_reach_24h",
            "channel_avg_reach_48h",
            "channel_avg_reach_72h",
            "channel_posts_per_day",
            "channel_median_interval",
        ]

        for col in channel_cols:
            if col in df.columns:
                # Логарифмирование для больших чисел
                if col in [
                    "channel_subscribers",
                    "channel_avg_reach_24h",
                    "channel_avg_reach_48h",
                    "channel_avg_reach_72h",
                ]:
                    df[f"{col}_log"] = np.log1p(df[col])

                # Нормализация engagement_rate
                if col == "channel_engagement_rate":
                    df[f"{col}_norm"] = df[col] / 100.0

        # Категоризация стабильности
        if "channel_stability" in df.columns:
            stability_map = {"low": 0, "medium": 1, "high": 2}
            df["channel_stability_encoded"] = df["channel_stability"].map(
                lambda x: stability_map.get(x, 1)
            )

        return df

    def create_interaction_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Создание интерактивных признаков (взаимодействие признаков)

        Args:
            df: DataFrame

        Returns:
            DataFrame с интерактивными признаками
        """
        df = df.copy()

        # Взаимодействие времени и контента
        if "hour" in df.columns and "has_photo" in df.columns:
            df["hour_photo"] = df["hour"] * df["has_photo"]

        if "is_weekend" in df.columns and "has_video" in df.columns:
            df["weekend_video"] = df["is_weekend"] * df["has_video"]

        # Взаимодействие размера канала и типа контента
        if "channel_subscribers" in df.columns:
            subs_log = np.log1p(df["channel_subscribers"])

            if "has_photo" in df.columns:
                df["subs_log_photo"] = subs_log * df["has_photo"]

            if "has_video" in df.columns:
                df["subs_log_video"] = subs_log * df["has_video"]

        return df

    def create_all_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Создание всех признаков

        Args:
            df: Исходный DataFrame

        Returns:
            DataFrame со всеми признаками
        """
        logger.info("Создание временных признаков...")
        df = self.create_time_features(df)

        logger.info("Создание признаков контента...")
        df = self.create_content_features(df)

        logger.info("Создание признаков вовлеченности...")
        df = self.create_engagement_features(df)

        logger.info("Создание признаков канала...")
        df = self.create_channel_features(df)

        logger.info("Создание интерактивных признаков...")
        df = self.create_interaction_features(df)

        logger.info(f"✅ Всего признаков создано: {len(df.columns)}")

        return df

    def select_features(
        self,
        df: pd.DataFrame,
        target_col: str = "forwards",
    ) -> tuple[pd.DataFrame, list[str]]:
        """
        Выбор признаков для модели

        Args:
            df: DataFrame с признаками
            target_col: Название целевой переменной

        Returns:
            Tuple (DataFrame с признаками, список названий признаков)
        """
        # Exclude identifiers, post-publication outcomes and every feature
        # derived from those outcomes. Keeping only the raw target out is not
        # sufficient: ratios such as forwards_to_views leak the answer.
        exclude_cols = {
            "post_id",
            "date",
            "date_timestamp",
            "text_preview",
            "url",
            "age_hours",
            "age_days",
            target_col,
            *POST_PUBLICATION_FEATURES,
        }

        # Оставляем только числовые колонки
        numeric_types = [np.int64, np.float64, np.int32, np.float32]
        feature_cols = [
            col
            for col in df.columns
            if col not in exclude_cols and df[col].dtype in numeric_types
        ]

        # Убираем колонки с NaN
        feature_cols = [col for col in feature_cols if not df[col].isna().all()]

        leaked_features = POST_PUBLICATION_FEATURES.intersection(feature_cols)
        if leaked_features:
            raise RuntimeError(
                f"Post-publication feature leakage detected: {sorted(leaked_features)}"
            )

        X = df[feature_cols].copy()

        # Заполняем NaN нулями
        X = X.fillna(0)

        # Заменяем бесконечности на большие числа
        X = X.replace([np.inf, -np.inf], 0)

        logger.info(f"✅ Выбрано признаков: {len(feature_cols)}")

        return X, feature_cols

    def get_feature_importance_dataframe(
        self,
        model,
        feature_names: list[str],
    ) -> pd.DataFrame:
        """
        Создать DataFrame с важностью признаков

        Args:
            model: Обученная модель с feature_importances_
            feature_names: Список названий признаков

        Returns:
            DataFrame с важностью признаков
        """
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
        elif hasattr(model, "coef_"):
            importances = np.abs(model.coef_)
        else:
            raise ValueError("Модель не имеет атрибута feature_importances_ или coef_")

        feature_importance = pd.DataFrame(
            {"feature": feature_names, "importance": importances}
        ).sort_values("importance", ascending=False)

        return feature_importance
