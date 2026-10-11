"""Хендлер модерации: мониторинг действий ботов-модераторов.

Список ботов и их ID задаётся в bots.py (реэкспорт через config.ALLOWED_MODS).
"""

import asyncio
import random

from telethon import events, errors

import state
from achievements import check_new_achievements
from client import client
from config import ALLOWED_MODS, USER_COOLDOWN_SECONDS
from database import backfill_victim_user_id, get_user_stats, lookup_user_by_victim_name, save_action
from helpers import check_and_update_cooldown, get_time_str
from identity import sync_user_by_id
from notifications import try_send_pm
from parsing import parse_moderation_message


@client.on(events.NewMessage)
async def handle_moderation_message(event):
    """Мониторинг действий ботов во всех группах (MissRose & THM Chatbot)."""
    try:
        if not event.is_group:
            return

        if event.sender_id not in ALLOWED_MODS:
            return

        parsed = parse_moderation_message(event.message)
        if not parsed:
            return

        # Если бот не дал ни ID, ни username — пробуем найти человека по
        # отображаемому имени (только если имя однозначно указывает на него)
        if not parsed.get('user_id') and not parsed.get('username') and parsed.get('victim_name'):
            found_id = lookup_user_by_victim_name(parsed['victim_name'])
            if found_id:
                parsed['user_id'] = found_id

        # Если ID известен — привязываем его к старым безымянным записям
        if parsed.get('user_id') and parsed.get('victim_name'):
            backfill_victim_user_id(parsed['victim_name'], parsed['user_id'])

        # Обновляем имя/username во всех старых записях нарушителя
        if parsed.get('user_id'):
            await sync_user_by_id(parsed['user_id'])

        # Кулдаун только по стабильному идентификатору: ID, иначе username.
        # Отображаемое имя не используем — однофамильцы/заглушки схлопнулись бы.
        user_key = None
        if parsed.get('user_id'):
            user_key = f"id_{parsed['user_id']}"
        elif parsed.get('username'):
            user_key = f"user_{parsed['username'].lower()}"

        if user_key and check_and_update_cooldown(user_key):
            print(f"[*] Пропуск дублирующей реакции для пользователя {user_key} (кулдаун {USER_COOLDOWN_SECONDS} сек)")
            return

        chat_title = "Неизвестный чат"
        if event.chat and hasattr(event.chat, 'title'):
            chat_title = event.chat.title

        save_action(
            chat_id=chat_id,
            chat_title=chat_title,
            user_id=parsed['user_id'],
            username=parsed['username'],
            victim_name=parsed['victim_name'],
            action_type=parsed['action_type'],
            duration=parsed['duration'],
            reason=parsed['reason']
        )
        print(f"[+] {get_time_str()} Сохранен лог от бота (ID: {event.sender_id}) в чате '{chat_title}'. Нарушитель: {parsed['victim_name']}, Время: {parsed['duration']}")

        # В чат летит ГОЛУБЬ
        chat_sticker = state.PIGEON_STICKER if state.PIGEON_STICKER else state.EAGLE_STICKER
        if chat_sticker:
            await asyncio.sleep(random.uniform(0.07, 0.17))
            try:
                await client.send_file( entity=event.chat_id, file=chat_sticker, reply_to=event.id )
            except errors.FloodWaitError as e:
                print(f"[-] FloodWait в чате: {e.seconds} сек.")
            except Exception as e:
                print(f"[-] Ошибка отправки стикера в чат: {e}")

        # В ЛС летит ГОЛУБЬ
        if parsed['user_id'] or parsed['username']:
            await asyncio.sleep(random.uniform(1.18, 1.84))
            action_word = "замутили" if parsed['action_type'] == "mute" else "забанили"
            promo_text = (
                f"Тебя совершенно несправедливо {action_word} в чате {chat_title}, это ВОЗМУТИТЕЛЬНО!!!\n"
                f"ДОВОЛЬНО ЭТО ТЕРПЕТЬ!!! Вставай на путь демократии и свободы выбора!!!\n"
                f"Присоединяйся к нашему походу за справедливость, распространяй стикер, ВЫБОРЫ ЕСТЬ!!!"
            )

            # Проверка на новые достижения
            mutes, bans, _, _ = get_user_stats(parsed['user_id'], parsed['username'])
            new_achievements = check_new_achievements(mutes, bans, parsed['action_type'])
            if new_achievements:
                promo_text += "\n\n🏆 Вы разблокировали новое достижение!"
                for ach in new_achievements:
                    promo_text += f"\n🎉 {ach['title']} — {ach['desc']}"

            pm_sticker = state.PIGEON_STICKER if state.PIGEON_STICKER else state.EAGLE_STICKER
            await try_send_pm(
                parsed['user_id'], parsed['username'], promo_text, pm_sticker,
                chat_id=chat_id, reply_to=event.id,
            )

    except Exception as log_err:
        print(f"[-] Критическая ошибка в обработчике модерации: {log_err}")
