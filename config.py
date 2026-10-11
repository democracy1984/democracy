"""Настройки и константы проекта.

Все ключевые значения (API, сессии, папки, тайминги) — здесь.
Список ботов-модераторов живёт в отдельном файле bots.py, здесь
он реэкспортируется как ALLOWED_MODS для удобства импорта.
API-ключи можно переопределить через переменные окружения
TELEGRAM_API_ID / TELEGRAM_API_HASH.
"""

import os

from bots import ALLOWED_MODS  # noqa: F401 (реэкспорт)

# --- API TELEGRAM ---
# По умолчанию — публичные ключи из документации Telethon (для тестов).
# Для своего аккаунта лучше задать собственные через переменные окружения
# или подставить сюда (ключи с https://my.telegram.org).
API_ID = int(os.environ.get("TELEGRAM_API_ID", 2040))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "b18441a1ff607e10a989891a5462e627")

# --- ПАПКА С СЕССИЯМИ TELEGRAM ---
# Файлы сессий (*.session) лежат здесь и не попадают в git (см. .gitignore).
# Можно переопределить через переменную окружения (например, для тестов на копии).
SESSION_DIR = os.environ.get("DEMOCRACY_SESSION_DIR", "secrets")

# --- ИМЕНА СЕССИЙ ---
MAIN_SESSION_NAME = "my_account"          # основная сессия юзербота
SCRAPER_SESSION_NAME = "scraper_session"  # сессия старого отдельного скрапера (может отсутствовать)

# --- ФОНОВАЯ ГИФКА ДЛЯ ПОЛЬЗОВАТЕЛЯ MATRIX ---
MATRIX_BG_URL = "https://upload-assets.vice.com/files/2016/01/22/145348420030000fps.gif"
MATRIX_BG_PATH = "matrix_bg.gif"

# Каждый N-й кадр фоновой гифки используется в карточке (ускорение без потери плавности)
GIF_FRAME_STEP = 2

# --- НАСТРОЙКИ СТИКЕРОВ ---
STICKER_PACK_NAME = "KozakDemocracy"

# --- КУЛДАУН / ЗАДЕРЖКА ДЛЯ ПОЛЬЗОВАТЕЛЕЙ (10 СЕКУНД) ---
USER_COOLDOWN_SECONDS = 10

# --- ДИАЛОГИ ДЛЯ ОТПРАВКИ В ЛС ---
PM_DIALOGS_REFRESH_SECONDS = 60
