"""Хендлер событий чата: вход участников, смена названия.

Вынесено из main.py без изменений.
"""

import asyncio
import random

from telethon import events, errors

import state
from client import client
from config import USER_COOLDOWN_SECONDS
from database import update_chat_title
from helpers import check_and_update_cooldown, get_time_str


@client.on(events.ChatAction)
async def handle_chat_action(event):
    """Обработка событий чата (вход пользователей, смена названия и т.д.)."""
    # Если изменилось название чата, обновляем его во всех записях БД
    if event.new_title:
        try:
            update_chat_title(event.chat_id, event.new_title)
            print(f"[+] {get_time_str()} Название чата {event.chat_id} изменено на: {event.new_title}")
        except Exception as e:
            print(f"[-] Ошибка обновления названия чата: {e}")

    # Отправка стикера орла при входе нового юзера в чат/канал
    if event.user_joined or event.user_added:
        user_key = f"id_{event.user_id}" if getattr(event, 'user_id', None) else None
        if user_key and check_and_update_cooldown(user_key):
            print(f"[*] Пропуск приветствия для пользователя {user_key} (кулдаун {USER_COOLDOWN_SECONDS} сек)")
            return
        try:
            await asyncio.sleep(random.uniform(0.34, 0.8))
            chat_sticker = state.EAGLE_STICKER if state.EAGLE_STICKER else state.PIGEON_STICKER
            if chat_sticker:
                await client.send_file( entity=event.chat_id, file=chat_sticker )
                print(f"[+] {get_time_str()} Отправлен приветственный Орёл в чат {event.chat_id}")
        except errors.FloodWaitError as e:
            print(f"[-] FloodWait при приветствии: {e.seconds} сек.")
        except Exception as e:
            print(f"[-] Ошибка отправки приветственного стикера: {e}")
