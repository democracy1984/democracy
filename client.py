"""Общий Telegram-клиент (сессия my_account).

Раньше создавался на уровне модуля main.py; вынесен отдельно, чтобы
main.py, хендлеры и сервисные модули импортировали один и тот же объект.
Файл сессии хранится в папке secrets (см. config.SESSION_DIR).
"""

import os

from telethon import TelegramClient

from config import API_ID, API_HASH, MAIN_SESSION_NAME, SESSION_DIR

os.makedirs(SESSION_DIR, exist_ok=True)

client = TelegramClient(
    os.path.join(SESSION_DIR, MAIN_SESSION_NAME),
    API_ID,
    API_HASH,
    device_model="Linux",
    system_version="Ubuntu 22.04",
    app_version="4.14.9",
    lang_code="en",
    system_lang_code="en-US"
)
