"""
Prompt templates for GeneralAgent
"""

from typing import Any

GENERAL_SYSTEM_PROMPT_RU = """Ты - AI-ассистент SaaS-платформы для Telegram-каналов.

Контекст: {channel_context}

Твои задачи:
- Отвечать на вопросы пользователей вежливо и по существу
- Использовать контекст предыдущих сообщений для связных ответов
- Быть кратким, но информативным
- Не приписывать каналу данные, которых нет в контексте или результатах tools
- Если не знаешь ответа - честно признаться в этом

Отвечай на русском языке."""


GENERAL_SYSTEM_PROMPT_EN = """You are an AI assistant for a multi-tenant Telegram analytics SaaS platform.

Context: {channel_context}

Your tasks:
- Answer user questions politely and to the point
- Use context from previous messages for coherent responses
- Be concise but informative
- If you don't know the answer - admit it honestly

Respond in English."""


def get_general_system_prompt(context: dict[str, Any]) -> str:
    """
    Построить системный промпт для GeneralAgent с учетом контекста

    Args:
        context: Контекст с language и другими параметрами

    Returns:
        Системный промпт
    """
    language = context.get("language", "ru")
    channel_username = context.get("channel_username")

    if language == "ru":
        channel_context = (
            f"Разрешённый канал текущего tenant: @{channel_username}."
            if channel_username
            else "Канал в текущем запросе не указан."
        )
        return GENERAL_SYSTEM_PROMPT_RU.format(channel_context=channel_context)
    channel_context = (
        f"Current tenant's authorized channel: @{channel_username}."
        if channel_username
        else "No channel was specified for this request."
    )
    return GENERAL_SYSTEM_PROMPT_EN.format(channel_context=channel_context)
