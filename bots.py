"""Список ботов, действия которых мониторит юзербот.

ЕДИНСТВЕННОЕ место, где задаются боты-модераторы:
  * MODERATOR_BOTS — боты, которых отслеживает мониторинг модерации
    (handlers/moderation.py) и исторический скрапер (scraping.py);
  * ALLOWED_MODS   — плоский список их ID для фильтрации событий.

Часть ботов задана по username (bot_username) и резолвится в ID
динамически при старте (main.py): так ID остаётся актуальным, даже
если Telegram его изменит. Боты с известным статическим ID заданы
через bot_id и не требуют сетевого резолва.
"""

# --- БОТ-МОДЕРАТОРЫ ---
# bot_id       — известный статический ID (можно не резолвить);
# bot_username — username для динамического резолва ID при старте;
# bot_name     — человекочитаемое имя для логов и сообщений.
MODERATOR_BOTS = [
    {
        "bot_key": "miss_rose",
        "bot_name": "MissRose",
        "bot_id": None,
        "bot_username": "@MissRose_bot",
    },
    {
        "bot_key": "thm_chatbot",
        "bot_name": "THM Chatbot",
        "bot_id": 7945156565,
        "bot_username": None,
    },
]


def _bot_label(bot: dict) -> str:
    """Человекочитаемое имя бота: имя со ссылкой-юзернеймом, если он задан."""
    if bot.get("bot_username"):
        return f"{bot['bot_name']} ({bot['bot_username']})"
    return bot["bot_name"]


# Имя конкретного бота по ключу (удобно для логов и статусных сообщений)
MISS_ROSE_NAME = _bot_label(MODERATOR_BOTS[0])
THM_CHATBOT_NAME = _bot_label(MODERATOR_BOTS[1])


# ID ботов, известные заранее (без сетевого резолва)
STATIC_MOD_IDS = [bot["bot_id"] for bot in MODERATOR_BOTS if bot.get("bot_id")]

# Боты, которых надо дополнительно резолвить при старте
MODS_TO_RESOLVE = [bot for bot in MODERATOR_BOTS if bot.get("bot_username")]


def bots_label() -> str:
    """Строка со списком мониторируемых ботов для статусных сообщений и логов."""
    return ", ".join(_bot_label(bot) for bot in MODERATOR_BOTS)


# Рабочий список ID для фильтрации событий.
# Копия STATIC_MOD_IDS: main.py при старте дополняет его ID,
# полученными резолвом MODS_TO_RESOLVE (например, MissRose).
ALLOWED_MODS = list(STATIC_MOD_IDS)
