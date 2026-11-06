# 🚀 Быстрый старт ML модуля

Модуль экспериментальный. Репозиторий не содержит готовой production-модели
или подтвержденных метрик: обучите модель на своих данных и оцените ее на более
новом временном отрезке.

## Шаг 1: Установка зависимостей

```bash
cd parser_local
python3.11 -m venv .venv-ml
source .venv-ml/bin/activate
python -m pip install --require-hashes -r ML/requirements.lock
```

## Шаг 2: Подготовка данных

Убедитесь, что у вас есть:
- JSON файл с постами в `parser_local/Logs/top_posts_*.json`
- CSV файл с анализом канала в `parser_local/Logs/channels_analysis_*.csv`

Если нет - запустите:
```bash
# Создать анализ постов
python top_posts_analyzer.py demo_analytics_channel --limit 100

# Должен быть CSV файл анализа канала (из local_parser.py)
```

## Шаг 3: Обучение модели

```bash
cd parser_local/ML

# Вариант 1: Сравнить все модели и выбрать лучшую
python train_model.py --compare-all

# Вариант 2: Обучить конкретную модель
python train_model.py --model xgboost
```

## Шаг 4: Предсказание вирусности

```bash
# Предсказать вирусность последних постов
python predict.py

# С указанием файла
python predict.py --json-path ../Logs/top_posts_example_YYYYMMDD_HHMMSS.json --top 20
```

## 📊 Что вы получите:

1. **Обученная модель** в `ML/models/`
2. **Метрики модели** в `ML/models/metrics_*.json`
3. **Важность признаков** в `ML/models/feature_importance_*.csv`
4. **Предсказания** в `ML/results/predictions_*.csv`

## ⚠️ Важно:

- Фиксированного объема данных, гарантирующего качество, нет
- Для итоговой оценки используйте временной holdout, а не метрики на обучении
- Модель сохраняется автоматически
- Используется последняя локальная модель (если не указан путь)
- Не загружайте скачанные `.pkl`: допустимы только доверенные модели из `ML/models/`

## 🔧 Устранение проблем:

Если возникает ошибка импорта:
```bash
# Переустановите проверенный dependency graph
python -m pip install --force-reinstall --require-hashes -r ML/requirements.lock
```

Если мало данных:
```bash
# Соберите больше постов
cd ..
python top_posts_analyzer.py demo_analytics_channel --limit 500
```






