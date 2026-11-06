"""
Локальный парсер каналов Telegram.
Упрощенная версия без БД/Redis для локального использования.
Анализирует канал и собирает общую статистику с AI-анализом контента.
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from openai import OpenAI
from socks import SOCKS5
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    RPCError,
    UsernameNotOccupiedError,
)
from telethon.sync import TelegramClient
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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "local_parser.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Константы
SLEEP_MIN, SLEEP_MAX = 3, 7
RESOLVE_BACKOFFS = [5, 15, 45]

# ---------------------- AI PROMPT ----------------------

AI_SYSTEM_PROMPT = """
 Ты — опытный SMM-аналитик и медиабайер. Отвечай строго по схеме.
Верни ТОЛЬКО ВАЛИДНЫЙ JSON UTF-8, без markdown, без комментариев, без лишних полей.

{
  "format":          {"content":"ключи через запятую"},
  "tonality":        {"content":"ключи через запятую"},
  "patterns":        {"content":"ключи через запятую"},
  "ad_fit":          {"content":"ровно 10 ключей через запятую"},
  "brand_mentions":  {"content":"реальные бренды/артисты/лейблы/фестивали из текста через запятую"},
  "audience":        {"content":"ключи через запятую"},
  "channel_topic":   {"content":"ровно 3 ключа через запятую"},
  "channel_summary": {"content":"2–4 коротких предложения без воды"},
  "geo_city_guess":  {"city":"...", "country":"...", "confidence":0.0},
  "brand_candidates":{"list":["бренд1","бренд2","..."]}
}

ПРАВИЛА ФОРМИРОВАНИЯ «СЕМАНТИЧЕСКИХ ЯДЕР» (content) ДЛЯ format / tonality / patterns / ad_fit / audience / channel_topic:
1) Формат ключей:
   — Только смысловые ключи 1–2 слова (существительные или устойчивые словосочетания); без глаголов, без эмодзи.
   — Лемматизируй и пиши в нижнем регистре (кроме brand_mentions).
   — Разделитель: запятая + пробел. Никаких точек, кавычек, тире в конце.
2) Объёмы:
   — format: 4–6 ключей (про подачу: «мемы, афиши, сторителлинг, шортсы, опросы, подборки…»).
   — tonality: 3–6 ключей (тон/манера: «сарказм, ирония, дерзость, провокация, неформальность…»; допускаются прилагательные-существительные, приводить к форме существительного, напр. «сарказм», «ирония»).
   — patterns: 6–10 ключей (повторяющиеся паттерны контента: «анонсы, мемы, личные заметки, афиши, репосты, шутки, плейлисты…»).
   — ad_fit: РОВНО 10 категорий (только ниши/категории, не бренды): «фестивали, клубы, тикетинг, алкоголь, звукотехника, мерч, одежда, такси, бары, стриминги…».
   — audience: 4–8 ключей (сегменты/психографика: «молодёжь, студенты, клубная аудитория, меломаны, тусовщики…»).
   — channel_topic: РОВНО 3 устойчивых темы (не даты/ивенты): «клубная культура, юмор, отношения».
3) Глобальная уникальность (критично):
   — Удали повторы внутри каждого тега.
   — Удали повторы МЕЖДУ тегами из набора {format, tonality, patterns, ad_fit, audience, channel_topic}.
   — Если ключ уже использован в предыдущем теге из этого набора — замени на близкий синоним, которого ещё нет; если синонима нет, пропусти.
   — Не используй ключи из brand_mentions в остальных тегах.
4) brand_mentions:
   — Только реальные бренды/артисты/лейблы/фестивали/медиа/площадки, которые ЯВНО встречаются в TITLE/BIO/POSTS.
   — Сохраняй оригинальный регистр/написание (латиница/кириллица), разделитель — запятая.
   — 0–30 позиций, никаких служебных/общих слов («пятница», «девочка» и т.п.) и выдумок.
   — Поле brand_candidates.list дублирует эти бренды массивом (без дублей) и используется как вспомогательное.
5) channel_summary:
   — 2–4 предложения по делу: чем канал «продаёт внимание», ядро тем и пользы; без эпитетов и воды.
6) geo_city_guess:
   — Если локаль угадывается — заполни city/country и confidence (0..1), иначе верни пустые строки и 0.0.

ВХОД:
Я даю тебе:
TITLE: <заголовок канала>
BIO: <описание канала>
POSTS (sample): <фрагменты постов>

СГЕНЕРИРУЙ РОВНО ОДИН JSON СТРОГО ПО СХЕМЕ ВЫШЕ.
"""


def ai_analyze(title, bio, posts_text, openai_api_key, ai_model):
    """Анализ канала через OpenAI"""
    if not (title or bio or posts_text):
        return {}
    try:
        client_ai = OpenAI(api_key=openai_api_key)
        user_block = f"TITLE:\n{title}\n\nBIO:\n{bio}\n\nPOSTS (sample):\n{posts_text}"
        resp = client_ai.chat.completions.create(
            model=ai_model,
            messages=[
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": user_block},
            ],
            temperature=0.2,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        out = {}
        for k in (
            "format",
            "tonality",
            "patterns",
            "ad_fit",
            "audience",
            "channel_summary",
            "channel_topic",
            "geo_city_guess",
            "brand_candidates",
        ):
            v = data.get(k, {})
            out[k] = v if isinstance(v, dict) else {}
        return out
    except Exception as e:
        logger.error(f"AI JSON error: {e}")
        return {}


def ai_geo_guess(openai_api_key, ai_model, bio, posts_text):
    """Определение геолокации через AI"""
    ai_result = ai_analyze("", bio, posts_text, openai_api_key, ai_model)
    geo = ai_result.get("geo_city_guess", {})
    city = geo.get("city", "") if isinstance(geo, dict) else ""
    country = geo.get("country", "") if isinstance(geo, dict) else ""
    confidence = geo.get("confidence", 0.0) if isinstance(geo, dict) else 0.0
    return city, country, confidence


def ai_analyze_channel(openai_api_key, ai_model, bio, posts_text):
    """Анализ канала через AI и извлечение полей"""
    ai_result = ai_analyze("", bio, posts_text, openai_api_key, ai_model)

    format_c = (
        ai_result.get("format", {}).get("content", "")
        if isinstance(ai_result.get("format"), dict)
        else ""
    )
    tonality_c = (
        ai_result.get("tonality", {}).get("content", "")
        if isinstance(ai_result.get("tonality"), dict)
        else ""
    )
    patterns_c = (
        ai_result.get("patterns", {}).get("content", "")
        if isinstance(ai_result.get("patterns"), dict)
        else ""
    )
    ad_fit_c = (
        ai_result.get("ad_fit", {}).get("content", "")
        if isinstance(ai_result.get("ad_fit"), dict)
        else ""
    )
    audience_c = (
        ai_result.get("audience", {}).get("content", "")
        if isinstance(ai_result.get("audience"), dict)
        else ""
    )
    summary_c = (
        ai_result.get("channel_summary", {}).get("content", "")
        if isinstance(ai_result.get("channel_summary"), dict)
        else ""
    )
    topic_c = (
        ai_result.get("channel_topic", {}).get("content", "")
        if isinstance(ai_result.get("channel_topic"), dict)
        else ""
    )

    return format_c, tonality_c, patterns_c, ad_fit_c, audience_c, summary_c, topic_c


# ---------------------- HELPERS ----------------------


def username_from_link(link: str):
    """Извлечение username из ссылки"""
    s = (link or "").strip()
    if not s:
        return None

    # Убираем префиксы
    if s.startswith("https://t.me/"):
        s = s.replace("https://t.me/", "")
    elif s.startswith("http://t.me/"):
        s = s.replace("http://t.me/", "")
    elif s.startswith("t.me/"):
        s = s.replace("t.me/", "")
    elif s.startswith("@"):
        s = s[1:]

    # Проверка на приватные ссылки и инвайты
    if s.startswith("+") or "joinchat" in s.lower() or "/c/" in s.lower():
        return None

    # Извлечение username (часть до первого / или ?)
    username = s.split("/")[0].split("?")[0].strip()

    return username if username else None


def resolve_entity_safe(client, uname: str):
    """Безопасное разрешение entity с повторными попытками"""
    last = None
    for i in range(len(RESOLVE_BACKOFFS) + 1):
        # Non-cryptographic retry jitter; no security decision depends on it.
        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))  # noqa: S311
        try:
            return client.get_entity(uname)
        except FloodWaitError as e:
            wait_s = int(getattr(e, "seconds", 60)) + 1
            logger.warning(f"[resolve] floodwait @{uname}: sleep {wait_s}s")
            time.sleep(wait_s)
        except UsernameNotOccupiedError as e:
            last = e
            if i < len(RESOLVE_BACKOFFS):
                backoff = RESOLVE_BACKOFFS[i]
                logger.warning(f"[resolve] @{uname} not occupied, retry in {backoff}s")
                time.sleep(backoff)
                continue
            raise
        except RPCError as e:
            last = e
            if i < len(RESOLVE_BACKOFFS):
                backoff = RESOLVE_BACKOFFS[i]
                logger.warning(
                    f"[resolve] RPC @{uname}: {e.__class__.__name__}, retry in {backoff}s"
                )
                time.sleep(backoff)
                continue
            raise
        except Exception as e:
            last = e
            if i < len(RESOLVE_BACKOFFS):
                time.sleep(RESOLVE_BACKOFFS[i])
                continue
            raise
    if last:
        raise last


def extract_contacts(text: str):
    """Извлечение контактов из текста"""
    if not text:
        return "", "", ""
    usernames = ", ".join(re.findall(r"@\w+", text))
    emails = ", ".join(re.findall(r"[\w\.-]+@[\w\.-]+", text))
    links = ", ".join(re.findall(r"https?://\S+", text))
    return usernames, emails, links


def classify_message_type(msg):
    """Классификация типа сообщения"""
    try:
        if getattr(msg, "video_note", None):
            return "round"
    except Exception:
        logger.debug("Не удалось определить video_note", exc_info=True)
    if getattr(msg, "video", None) is not None:
        return "video"
    if getattr(msg, "photo", None) is not None:
        return "image"
    if getattr(msg, "voice", None) is not None:
        return "audio"
    if getattr(msg, "audio", None) is not None:
        return "audio"
    doc = getattr(msg, "document", None)
    if doc:
        mime = (getattr(doc, "mime_type", "") or "").lower()
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("audio/"):
            return "audio"
        for attr in getattr(doc, "attributes", []) or []:
            if hasattr(attr, "round_message") and attr.round_message:
                return "round"
            if attr.__class__.__name__ in ("DocumentAttributeAnimated",):
                return "video"
    if getattr(msg, "sticker", None) is not None:
        return "image"
    text = (getattr(msg, "text", "") or "").strip()
    return "text" if text else "text"


def compute_posting_cadence_components(messages):
    """Вычисление метрик постинга: posts_per_day, median_interval_min, stability, peak_window"""
    if not messages:
        return 0.0, 0, "none", "—"
    dates = [m.date for m in messages if getattr(m, "date", None)]
    if len(dates) < 2:
        return 0.0, 0, "none", "—"
    dates_sorted = sorted(dates)
    deltas = [
        (dates_sorted[i] - dates_sorted[i - 1]).total_seconds()
        for i in range(1, len(dates_sorted))
    ]
    if not deltas:
        return 0.0, 0, "none", "—"
    med_interval_sec = median(deltas)
    median_interval_min = int(round(med_interval_sec / 60))
    days_span = max(1, (dates_sorted[-1] - dates_sorted[0]).days + 1)
    posts_per_day = round(len(dates_sorted) / days_span, 2)
    abs_dev = [abs(d - med_interval_sec) for d in deltas]
    mad = median(abs_dev) if abs_dev else 0
    cv_like = (mad / med_interval_sec) if med_interval_sec else 1
    stability = "high" if cv_like < 0.25 else ("medium" if cv_like < 0.6 else "low")
    hours = [d.hour for d in dates_sorted]
    top_hour = max(set(hours), key=hours.count) if hours else None
    peak_window = (
        f"{top_hour:02d}:00–{(top_hour + 1) % 24:02d}:00"
        if top_hour is not None
        else "—"
    )
    return posts_per_day, median_interval_min, stability, peak_window


# ---------------------- CONFIG ----------------------


def load_config():
    """Загрузка конфигурации из .env"""
    telegram = load_telegram_config(SCRIPT_DIR)

    proxy_enabled = os.getenv("PROXY_ENABLED", "0").strip() in ("1", "true", "True")
    proxy = None
    if proxy_enabled:
        host = os.getenv("PROXY_HOST")
        port = int(os.getenv("PROXY_PORT", "1080"))
        rdns = os.getenv("PROXY_RDNS", "1").strip() in ("1", "true", "True")
        user = os.getenv("PROXY_USER") or None
        pwd = os.getenv("PROXY_PASS") or None
        proxy = (SOCKS5, host, port, rdns, user, pwd)

    return {
        "session": Path(telegram["session_path"]).name,
        "session_path": str(telegram["session_path"]),
        "api_id": telegram["api_id"],
        "api_hash": telegram["api_hash"],
        "proxy": proxy,
        "openai_key": os.getenv("OPENAI_API_KEY"),
        "MSG_LIMIT": int(os.getenv("MSG_LIMIT", "100")),
        "AI_MODEL": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "AI_POSTS_LIMIT": int(os.getenv("AI_POSTS_LIMIT", "50")),
    }


# ---------------------- CORE ----------------------


def process_channel(cfg, channel_link: str):
    """Обработка одного канала"""
    session_name = cfg["session"]
    session_path = cfg["session_path"]
    api_id = cfg["api_id"]
    api_hash = cfg["api_hash"]
    proxy = cfg["proxy"]
    openai_api_key = cfg["openai_key"]
    msg_limit = cfg["MSG_LIMIT"]
    ai_model = cfg["AI_MODEL"]
    ai_posts_limit = cfg["AI_POSTS_LIMIT"]

    # Подключение к Telegram
    try:
        client = TelegramClient(
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
        client.connect()
    except Exception as e:
        logger.error(f"[connect] {session_name} error: {e}")
        raise

    if not client.is_user_authorized():
        logger.error(f"[auth] {session_name} not authorized.")
        client.disconnect()
        raise RuntimeError("Пользователь не авторизован")

    try:
        # Разрешение канала
        uname = username_from_link(channel_link)
        if not uname:
            raise ValueError(f"Не удалось извлечь username из {channel_link}")

        logger.info(f"Анализ канала: @{uname}")
        entity = resolve_entity_safe(client, uname)
        full = client(GetFullChannelRequest(channel=entity))

        username = getattr(entity, "username", "") or ""
        title = getattr(entity, "title", "") or (
            getattr(entity, "first_name", "") or ""
        )
        subscribers = getattr(full.full_chat, "participants_count", 0) or 0
        description = getattr(full.full_chat, "about", "") or ""
        contacts, emails, links_found = extract_contacts(description)
        chat_discussion = bool(getattr(full.full_chat, "linked_chat_id", None))

        # Загрузка сообщений
        logger.info(f"Загрузка сообщений (лимит: {msg_limit})...")
        all_messages = list(client.iter_messages(entity, limit=msg_limit))
        logger.info(f"Загружено {len(all_messages)} сообщений")

        # Вычисление метрик охвата
        err_list, reach_24, reach_48, reach_72 = [], [], [], []
        now = datetime.now(UTC)
        for msg in all_messages:
            views = getattr(msg, "views", None)
            if not views:
                continue
            age_hours = (now - msg.date).total_seconds() / 3600
            err = (views / subscribers) * 100 if subscribers else 0
            err_list.append(err)
            if age_hours <= 24:
                reach_24.append(views)
            if age_hours <= 48:
                reach_48.append(views)
            if age_hours <= 72:
                reach_72.append(views)

        avg_err = sum(err_list) / len(err_list) if err_list else 0
        avg_reach_24 = sum(reach_24) / len(reach_24) if reach_24 else 0
        avg_reach_48 = sum(reach_48) / len(reach_48) if reach_48 else 0
        avg_reach_72 = sum(reach_72) / len(reach_72) if reach_72 else 0

        # Метрики за 72 часа
        link_out_ratio_72h = 0
        reposts_72h = 0
        for msg in all_messages:
            if (now - msg.date).total_seconds() / 3600 > 72:
                continue
            if getattr(msg, "forwards", 0):
                reposts_72h += 1
            if getattr(msg, "entities", None):
                if any(getattr(ent, "url", None) for ent in msg.entities):
                    link_out_ratio_72h += 1
        link_out_ratio_72h = (
            (link_out_ratio_72h / len(all_messages) * 100) if all_messages else 0
        )

        # Метрики постинга
        posts_per_day, median_interval_min, stability, peak_window = (
            compute_posting_cadence_components(all_messages)
        )

        # Подсчет типов контента
        c_text = c_video = c_image = c_round = c_audio = 0
        posts_text = []
        for msg in all_messages[:ai_posts_limit]:
            if msg.message:
                c_text += 1
                posts_text.append(msg.message)
            if msg.video:
                c_video += 1
            if msg.photo:
                c_image += 1
            if getattr(msg, "video_note", None):
                c_round += 1
            if getattr(msg, "audio", None):
                c_audio += 1

        posts_text_joined = "\n\n".join(filter(None, posts_text))
        c_text = min(c_text, msg_limit)

        # AI анализ
        logger.info("Запуск AI анализа...")
        geo_city, geo_country, geo_conf = ai_geo_guess(
            openai_api_key, ai_model, description, posts_text_joined
        )
        format_c, tonality_c, patterns_c, ad_fit_c, audience_c, summary_c, topic_c = (
            ai_analyze_channel(openai_api_key, ai_model, description, posts_text_joined)
        )

        # Подготовка данных для записи
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = LOG_DIR / f"channels_analysis_{timestamp}.csv"

        fieldnames = [
            "row_id",
            "title",
            "username",
            "contacts",
            "emails",
            "links",
            "subscribers",
            "engagement_rate_percent",
            "avg_reach_24h",
            "avg_reach_48h",
            "avg_reach_72h",
            "link_out_ratio_72h",
            "reposts_72h",
            "posting_posts_per_day",
            "posting_median_interval_min",
            "posting_stability",
            "posting_peak_hour",
            "posts_text",
            "posts_video",
            "posts_image",
            "posts_round",
            "posts_audio",
            "geo_city_guess_city",
            "geo_city_guess_country",
            "geo_city_guess_confidence",
            "chat_discussion",
            "tag",
            "content",
            "account",
        ]

        base_row_id = f"{session_name}-{timestamp}"
        common_cols = {
            "title": title,
            "username": username,
            "contacts": contacts,
            "emails": emails,
            "links": links_found,
            "subscribers": subscribers,
            "engagement_rate_percent": round(avg_err, 2),
            "avg_reach_24h": round(avg_reach_24, 2),
            "avg_reach_48h": round(avg_reach_48, 2),
            "avg_reach_72h": round(avg_reach_72, 2),
            "link_out_ratio_72h": round(link_out_ratio_72h, 2),
            "reposts_72h": reposts_72h,
            "posting_posts_per_day": posts_per_day,
            "posting_median_interval_min": median_interval_min,
            "posting_stability": stability,
            "posting_peak_hour": peak_window,
            "posts_text": c_text,
            "posts_video": c_video,
            "posts_image": c_image,
            "posts_round": c_round,
            "posts_audio": c_audio,
            "geo_city_guess_city": geo_city,
            "geo_city_guess_country": geo_country,
            "geo_city_guess_confidence": round(geo_conf, 2),
            "chat_discussion": str(chat_discussion).lower(),
            "account": session_name,
        }

        rows = [
            ("format", format_c),
            ("tonality", tonality_c),
            ("patterns", patterns_c),
            ("ad_fit", ad_fit_c),
            ("audience", audience_c),
            ("channel_summary", summary_c),
            ("channel_topic", topic_c),
            ("channel_bio_raw", description),
        ]

        # Запись в CSV
        logger.info(f"Сохранение результатов в {output_file}")
        with open(output_file, "w", encoding="utf-8", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()

            for seq, (tag, content) in enumerate(rows, start=1):
                row = {
                    "row_id": f"{base_row_id}-{seq}",
                    "tag": tag,
                    "content": (content or "").strip(),
                    **common_cols,
                }
                writer.writerow(neutralize_csv_row(row))

        logger.info(f"✅ Анализ завершен. Результаты сохранены в {output_file}")
        print(f"\n✅ Анализ канала @{username} завершен!")
        print(f"📊 Результаты сохранены в: {output_file}")
        print(f"📈 Подписчиков: {subscribers:,}")
        print(f"📝 Проанализировано постов: {len(all_messages)}")

    except ChannelPrivateError as exc:
        logger.error("Канал приватный")
        raise RuntimeError("Канал приватный, доступ запрещен") from exc
    except FloodWaitError as e:
        wait_s = int(getattr(e, "seconds", 60)) + 1
        logger.warning(f"[flood] wait {wait_s}s")
        raise RuntimeError(f"Flood wait: {wait_s} секунд") from e
    except (UsernameNotOccupiedError, RPCError) as e:
        logger.error(f"[rpc] {channel_link}: {e.__class__.__name__}")
        raise RuntimeError(f"Ошибка при обращении к каналу: {e}") from e
    except Exception as e:
        logger.error(f"[loop] Ошибка с {channel_link}: {e}")
        raise
    finally:
        try:
            client.disconnect()
        except Exception:
            logger.debug("Не удалось отключить Telegram client", exc_info=True)


# ---------------------- MAIN ----------------------


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="Локальный парсер каналов Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python local_parser.py t.me/demo_analytics_channel
  python local_parser.py @demo_analytics_channel
  python local_parser.py demo_analytics_channel
        """,
    )
    parser.add_argument(
        "channel", help="Канал для анализа (username, @username или t.me/username)"
    )

    args = parser.parse_args()

    try:
        cfg = load_config()
        process_channel(cfg, args.channel)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
