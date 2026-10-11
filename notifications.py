"""Уведомления в ЛС: список диалогов и отправка сообщений/стикеров.

Вынесено из main.py; логика (включая текущие особенности) не менялась.
"""

import asyncio
import random
import time

from telethon import errors

import state
from client import client
from config import PM_DIALOGS_REFRESH_SECONDS
from helpers import get_time_str

_pm_dialogs_refreshed_at = 0.0


async def load_pm_dialogs():
    """Обновляет список пользователей, с которыми уже есть диалог (не чаще раза в минуту)."""
    global _pm_dialogs_refreshed_at
    now = time.time()
    if now - _pm_dialogs_refreshed_at < PM_DIALOGS_REFRESH_SECONDS:
        return
    dialog_user_ids = set()
    try:
        async for dialog in client.iter_dialogs():
            if dialog.is_user and dialog.entity:
                dialog_user_ids.add(dialog.entity.id)
    except Exception as e:
        print(f"[-] Не удалось получить список личных диалогов: {e}")
        return
    state.PM_DIALOG_USER_IDS.clear()
    state.PM_DIALOG_USER_IDS.update(dialog_user_ids)
    _pm_dialogs_refreshed_at = now
    print(f"[*] {get_time_str()} Загружено личных диалогов: {len(state.PM_DIALOG_USER_IDS)}")


async def send_no_dialog_fallback(chat_id, reply_to, target_victim):
    """Не можем писать первыми — просим написать боту в чате, где случилось наказание."""
    if not chat_id:
        return
    mention = f'<a href="tg://user?id={target_victim.id}">{target_victim.first_name or "друг"}</a>'
    text = (
        f"🕊 {mention} к сожелению я не могу писать первым ибо телеграм сделает мне айайай, прошу написать мне первым"
    )
    try:
        await asyncio.sleep(random.uniform(1.9, 2.6))
        await client.send_message(chat_id, text, reply_to=reply_to, parse_mode='html')
        print(f"[+] {get_time_str()} ЛС недоступны — отправлена просьба написать первой в чат {chat_id} (жертва: {target_victim.id})")
    except errors.FloodWaitError as e:
        print(f"[-] FloodWait при отправке просьбы в чат: {e.seconds} сек.")
    except Exception as e:
        print(f"[-] Не удалось отправить просьбу написать в ЛС в чат {chat_id}: {e}")


async def try_send_pm(user_id, username, text, sticker, chat_id=None, reply_to=None):
    """Попытка отправить личное сообщение и стикер жертве блокировки с поддержкой username и повтором при FloodWait.

    Если личного диалога нет и писать первыми нельзя — в исходном чате отправляется
    просьба написать боту в ЛС (chat_id и reply_to для этого передаёт вызывающий код).
    """
    target_victim = None

    # Сначала пытаемся разрешить по username (работает глобально)
    if username:
        try:
            target_victim = await client.get_entity(username)
        except Exception:
            pass

    # Если не вышло или нет username, пробуем по user_id
    if not target_victim and user_id:
        try:
            target_victim = await client.get_entity(user_id)
        except Exception:
            pass

    if not target_victim:
        print(f"[-] Не удалось найти сущность для отправки в ЛС: ID {user_id}, Username {username}")
        return

    # Проверяем opt-out
    resolved_id = target_victim.id
    if resolved_id in state.PM_OPT_OUT:
        print(f"[*] Пользователь {resolved_id} отписался от ЛС-рассылки, пропускаем.")
        return

    # Пишем в ЛС только тем, с кем диалог уже существует (неважно, кто его начал)
    if resolved_id not in state.PM_DIALOG_USER_IDS:
        await load_pm_dialogs()
    if resolved_id not in state.PM_DIALOG_USER_IDS:
        print(f"[*] Диалога с {resolved_id} ({username or user_id}) нет — просим написать первыми в чат.")
        await send_no_dialog_fallback(chat_id, reply_to, target_victim)
        return

    try:
        await client.send_message(target_victim, text)
        await asyncio.sleep(random.uniform(0.23, 0.44))
        if sticker:
            await client.send_file(target_victim, sticker)
        print(f"[+] {get_time_str()} Успешно отправлено уведомление в ЛС: {target_victim.id}")
    except errors.FloodWaitError as e:
        print(f"[-] FloodWait при отправке в ЛС: {e.seconds} сек. Ждем и пробуем снова...")
        await asyncio.sleep(e.seconds + 1)
        try:
            await client.send_message(target_victim, text)
            if sticker:
                await client.send_file(target_victim, sticker)
            print(f"[+] {get_time_str()} Успешно отправлено уведомление в ЛС после ожидания FloodWait: {target_victim.id}")
        except Exception as retry_err:
            print(f"[-] Повторная ошибка отправки после FloodWait: {retry_err}")
    except Exception as err:
        print(f"[-] Ошибка отправки сообщения в ЛС: {err}")
