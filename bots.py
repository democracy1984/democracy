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
    {
        "bot_key": "iris",
        "bot_name": "Iris",
        "bot_id": 5434504334,
        "bot_username": "@iris_moon_bot",
    },
    {
        "bot_key": "sentinel_prime",
        "bot_name": "Sentinel Prime",
        "bot_id": 7847367200,
        "bot_username": "@SentinelPrime_bot",
    },
    {
        "bot_key": "orgrobot",
        "bot_name": "OrgRobot",
        "bot_id": 787057350,
        "bot_username": "@orgrobot",
    },
]


def _bot_label(bot: dict) -> str:
    """Человекочитаемое имя бота: имя со ссылкой-юзернеймом, если он задан."""
    if bot.get("bot_username"):
        return f"{bot['bot_name']} ({bot['bot_username']})"
    return bot["bot_name"]


def bot_name_by_key(bot_key: str) -> str:
    """Имя конкретного бота по ключу (удобно для логов и статусных сообщений)."""
    for bot in MODERATOR_BOTS:
        if bot.get("bot_key") == bot_key:
            return _bot_label(bot)
    return bot_key


# Имена конкретных ботов (ленивый доступ по ключу)
MISS_ROSE_NAME = bot_name_by_key("miss_rose")
THM_CHATBOT_NAME = bot_name_by_key("thm_chatbot")
IRIS_NAME = bot_name_by_key("iris")


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
