"""Встроенный скрапер истории модерации по всем чатам.

Запускается один раз при старте, если база пуста. Единственная
реализация скрапинга в проекте (отдельный scraper.py удалён).
Список ботов-модераторов берётся из bots.py (через config.ALLOWED_MODS).
"""

import asyncio

from telethon import errors, utils

from client import client
from config import ALLOWED_MODS
from database import save_batch_actions
from helpers import get_time_str
from parsing import parse_moderation_message


async def auto_scrape_history():
    """Глубокий автоматический сбор истории модерации по всем чатам."""
    print("\n⚠️ База данных пуста или отсутствует! Запускаем встроенный скрапер истории...")
    print("[*] Загрузка списка ваших диалогов...")

    dialogs = await client.get_dialogs()
    groups = [d for d in dialogs if d.is_group]

    print(f"[+] {get_time_str()} Найдено групп для анализа: {len(groups)}")
    print("[*] Начинаем сбор логов от MissRose и THM Chatbot. Пожалуйста, подождите...")

    for idx, dialog in enumerate(groups, 1):
        chat_entity = dialog.entity
        chat_title = getattr(dialog, 'name', 'Неизвестный чат')
        print(f" [{idx}/{len(groups)}] Анализ чата: '{chat_title}' (ID: {chat_entity.id})")

        batch = []
        parsed_count = 0

        # Сначала пробуем искать по from_user для каждого бота
        for mod_id in ALLOWED_MODS:
            try:
                async for message in client.iter_messages(chat_entity, from_user=mod_id, limit=None):
                    parsed = parse_moderation_message(message)
                    if parsed:
                        batch.append((
                            utils.get_peer_id(chat_entity),
                            chat_title,
                            parsed['user_id'],
                            parsed['username'],
                            parsed['victim_name'],
                            parsed['action_type'],
                            parsed['duration'],
                            parsed['reason']
                        ))
                        parsed_count += 1

                        if len(batch) >= 100:
                            save_batch_actions(batch)
                            batch = []
            except errors.FloodWaitError as e:
                print(f"    [-] FloodWait! Telegram просит перерыв. Ждем {e.seconds} сек...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                print(f"    [!] Ошибка from_user для бота {mod_id}: {e}")

        # Фоллбэк: если from_user ничего не нашёл — перебираем все сообщения вручную
        if parsed_count == 0:
            try:
                async for message in client.iter_messages(chat_entity, limit=None):
                    if message.sender_id in ALLOWED_MODS:
                        parsed = parse_moderation_message(message)
                        if parsed:
                            batch.append((
                                utils.get_peer_id(chat_entity),
                                chat_title,
                                parsed['user_id'],
                                parsed['username'],
                                parsed['victim_name'],
                                parsed['action_type'],
                                parsed['duration'],
                                parsed['reason']
                            ))
                            parsed_count += 1

                            if len(batch) >= 100:
                                save_batch_actions(batch)
                                batch = []
            except errors.FloodWaitError as e:
                print(f"    [-] FloodWait (фоллбэк)! Ждем {e.seconds} сек...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                print(f"    [!] Ошибка фоллбэк-скана в чате {chat_entity.id}: {e}")

        if batch:
            save_batch_actions(batch)
        if parsed_count > 0:
            print(f"    [+] {get_time_str()} Успешно сохранено логов из этого чата: {parsed_count}")
        else:
            print(f"    [*] Логов модерации не найдено в чате '{chat_title}'")

        await asyncio.sleep(0.67) # Небольшая пауза между чатами

    print(f"[+] {get_time_str()} Первоначальный сбор истории успешно завершен! База данных заполнена.\n")
