"""
Модуль для загрузки и подготовки данных из парсера каналов и анализа постов.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataLoader:
    """Класс для загрузки и объединения данных из разных источников"""

    def __init__(self, base_dir: Path | None = None):
        """
        Инициализация загрузчика данных

        Args:
            base_dir: Базовая директория проекта (по умолчанию: родительская папка ML)
        """
        if base_dir is None:
            self.base_dir = Path(__file__).resolve().parent.parent
        else:
            self.base_dir = Path(base_dir)

        self.logs_dir = self.base_dir / "Logs"
        self.data_dir = self.base_dir / "ML" / "data"

    def load_top_posts_json(self, json_path: Path | None = None) -> pd.DataFrame:
        """
        Загрузить данные о топ постах из JSON файла

        Args:
            json_path: Путь к JSON файлу (по умолчанию: последний файл из Logs)

        Returns:
            DataFrame с данными о постах
        """
        if json_path is None:
            # Ищем последний JSON файл с топ постами
            json_files = list(self.logs_dir.glob("top_posts_*.json"))
            if not json_files:
                raise FileNotFoundError(f"Не найдено JSON файлов в {self.logs_dir}")
            json_path = max(json_files, key=lambda p: p.stat().st_mtime)
            logger.info(f"Используется файл: {json_path.name}")

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        posts = data.get("posts", [])
        if not posts:
            raise ValueError("JSON файл не содержит постов")

        df = pd.DataFrame(posts)
        logger.info(f"Загружено {len(df)} постов из JSON")

        return df

    def load_channel_analysis_csv(self, csv_path: Path | None = None) -> pd.DataFrame:
        """
        Загрузить данные анализа канала из CSV

        Args:
            csv_path: Путь к CSV файлу (по умолчанию: последний файл из Logs)

        Returns:
            DataFrame с данными канала
        """
        if csv_path is None:
            # Ищем последний CSV файл с анализом канала
            csv_files = list(self.logs_dir.glob("channels_analysis_*.csv"))
            if not csv_files:
                raise FileNotFoundError(
                    f"Не найдено CSV файлов анализа канала в {self.logs_dir}"
                )
            csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)
            logger.info(f"Используется файл: {csv_path.name}")

        # Пробуем разные разделители
        try:
            df = pd.read_csv(csv_path, sep="\t", encoding="utf-8")
        except Exception:
            try:
                df = pd.read_csv(csv_path, sep=",", encoding="utf-8")
            except Exception:
                df = pd.read_csv(csv_path, encoding="utf-8")

        # Если есть колонка 'tag', фильтруем по ней, иначе берем первую строку
        if "tag" in df.columns and len(df) > 0:
            # Берем строку с базовыми метриками (любую из первых, где есть основные данные)
            tag_filtered = df[
                df["tag"].isin(["format", "tonality"]) if "tag" in df.columns else True
            ]
            if len(tag_filtered) > 0:
                channel_base = tag_filtered.iloc[0]
            else:
                channel_base = df.iloc[0]
        else:
            # Берем первую строку
            channel_base = df.iloc[0] if len(df) > 0 else pd.Series()

        logger.info(f"Загружены данные канала: {channel_base.get('title', 'Unknown')}")

        return channel_base

    def merge_data(
        self, posts_df: pd.DataFrame, channel_data: pd.Series
    ) -> pd.DataFrame:
        """
        Объединить данные о постах с данными канала

        Args:
            posts_df: DataFrame с постами
            channel_data: Series с данными канала

        Returns:
            Объединенный DataFrame
        """
        # Создаем копию
        merged_df = posts_df.copy()

        # Добавляем метрики канала к каждому посту
        merged_df["channel_subscribers"] = channel_data.get("subscribers", 0)
        merged_df["channel_engagement_rate"] = channel_data.get(
            "engagement_rate_percent", 0
        )
        merged_df["channel_avg_reach_24h"] = channel_data.get("avg_reach_24h", 0)
        merged_df["channel_avg_reach_48h"] = channel_data.get("avg_reach_48h", 0)
        merged_df["channel_avg_reach_72h"] = channel_data.get("avg_reach_72h", 0)
        merged_df["channel_posts_per_day"] = channel_data.get(
            "posting_posts_per_day", 0
        )
        merged_df["channel_median_interval"] = channel_data.get(
            "posting_median_interval_min", 0
        )
        merged_df["channel_stability"] = channel_data.get(
            "posting_stability", "unknown"
        )

        # Извлекаем час публикации из даты
        merged_df["date"] = pd.to_datetime(merged_df["date"])
        merged_df["hour"] = merged_df["date"].dt.hour
        merged_df["day_of_week"] = merged_df["date"].dt.dayofweek
        merged_df["is_weekend"] = merged_df["day_of_week"].isin([5, 6]).astype(int)

        logger.info(f"Данные объединены: {len(merged_df)} постов с метриками канала")

        return merged_df

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Подготовка признаков для ML модели

        Args:
            df: Исходный DataFrame

        Returns:
            DataFrame с подготовленными признаками
        """
        features_df = df.copy()

        # Бинарные признаки типов контента
        content_types = [
            "has_photo",
            "has_video",
            "has_audio",
            "has_voice",
            "has_document",
            "has_round_video",
            "has_poll",
        ]
        for col in content_types:
            if col in features_df.columns:
                features_df[col] = features_df[col].astype(int)

        # Создаем комбинированные признаки
        features_df["has_media"] = (
            features_df.get("has_photo", 0)
            | features_df.get("has_video", 0)
            | features_df.get("has_audio", 0)
        ).astype(int)

        features_df["text_length_log"] = (features_df["text_length"] + 1).apply(
            lambda x: np.log(x)
        )

        # Нормализация engagement_rate канала
        if "channel_engagement_rate" in features_df.columns:
            features_df["channel_engagement_rate_norm"] = (
                features_df["channel_engagement_rate"] / 100.0
            )

        # Отношение подписчиков
        if (
            "channel_subscribers" in features_df.columns
            and "views" in features_df.columns
        ):
            features_df["views_to_subscribers_ratio"] = features_df["views"] / (
                features_df["channel_subscribers"] + 1
            )

        logger.info(f"Подготовлено признаков: {len(features_df.columns)}")

        return features_df

    def load_combined_data(
        self, json_path: Path | None = None, csv_path: Path | None = None
    ) -> pd.DataFrame:
        """
        Загрузить и объединить все данные

        Args:
            json_path: Путь к JSON с постами (опционально)
            csv_path: Путь к CSV с анализом канала (опционально)

        Returns:
            Объединенный DataFrame с подготовленными признаками
        """
        # Загружаем данные
        posts_df = self.load_top_posts_json(json_path)
        channel_data = self.load_channel_analysis_csv(csv_path)

        # Объединяем
        merged_df = self.merge_data(posts_df, channel_data)

        # Подготавливаем признаки
        features_df = self.prepare_features(merged_df)

        return features_df

    def save_processed_data(
        self, df: pd.DataFrame, filename: str = "processed_data.csv"
    ):
        """
        Сохранить обработанные данные

        Args:
            df: DataFrame для сохранения
            filename: Имя файла
        """
        filepath = self.data_dir / filename
        df.to_csv(filepath, index=False, encoding="utf-8")
        logger.info(f"Данные сохранены: {filepath}")
        return filepath


if __name__ == "__main__":
    # Тестирование загрузчика
    loader = DataLoader()

    try:
        df = loader.load_combined_data()
        print("\n✅ Данные загружены успешно!")
        print(f"📊 Размер: {df.shape}")
        print(f"📝 Колонки: {list(df.columns)}")
        print("\n🔝 Топ-5 постов по репостам:")
        print(df[["post_id", "forwards", "views", "text_preview"]].head())

        # Сохраняем обработанные данные
        loader.save_processed_data(df)

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
