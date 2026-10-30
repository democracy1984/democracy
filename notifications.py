"""Уведомления в ЛС: список диалогов и отправка сообщений/стикеров.

Бот пишет первым даже незнакомым пользователям. В самое первое сообщение
нового диалога добавляется приписка про /stopspamming, чтобы у человека
был способ отписаться, не теряя доступ к командам.
"""

import asyncio
import random
import time

from telethon import errors

import state
from client import client
from config import PM_DIALOGS_REFRESH_SECONDS
from database import save_pm_intro_sent
from helpers import get_time_str

_pm_dialogs_refreshed_at = 0.0

# Приписка к первому сообщению в новом личном диалоге
FIRST_PM_PS = (
    "\n\nPS: вы вольны написать /stopspamming, тогда доступ к командам останется, "
    "а я впредь не буду вас беспокоить."
)


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


async def send_pm_fallback(chat_id, reply_to, target_victim):
    """Не удалось доставить ЛС — просим написать боту в чате, где случилось наказание."""
    if not chat_id:
        return
    mention = f'<a href="tg://user?id={target_victim.id}">{target_victim.first_name or "друг"}</a>'
    text = (
        f"🕊 {mention}, я не смог написать вам в ЛС — телеграм не дал. "
        f"Напишите мне первым, пожалуйста."
    )
    try:
        await asyncio.sleep(random.uniform(1.9, 2.6))
        await client.send_message(chat_id, text, reply_to=reply_to, parse_mode='html')
        print(f"[+] {get_time_str()} ЛС недоступны — отправлена просьба написать первой в чат {chat_id} (жертва: {target_victim.id})")
    except errors.FloodWaitError as e:
        print(f"[-] FloodWait при отправке просьбы в чат: {e.seconds} сек.")
    except Exception as e:
        print(f"[-] Не удалось отправить просьбу написать в ЛС в чат {chat_id}: {e}")


def _remember_first_message(user_id, intro_sent):
    """Запоминает, что диалог начат; при первом сообщении — что приписка уже была."""
    state.PM_DIALOG_USER_IDS.add(user_id)
    if intro_sent:
        state.PM_INTRO_SENT.add(user_id)
        save_pm_intro_sent(user_id)


async def try_send_pm(user_id, username, text, sticker, chat_id=None, reply_to=None):
    """Отправляет личное сообщение и стикер жертве блокировки (username или user_id, повтор при FloodWait).

    Пишет первым, даже если диалога ещё нет. К первому сообщению нового диалога
    добавляется приписка с /stopspamming. Если Telegram не дал доставить ЛС
    (блокировка, приватность), в исходном чате отправляется просьба написать боту.
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

    # Есть ли уже диалог: если нет — этим сообщением бот пишет первым
    if resolved_id not in state.PM_DIALOG_USER_IDS:
        await load_pm_dialogs()
    first_in_dialog = resolved_id not in state.PM_DIALOG_USER_IDS

    # Приписка про отписку — только в самое первое сообщение новому человеку
    intro_sent = first_in_dialog and resolved_id not in state.PM_INTRO_SENT
    if intro_sent:
        text += FIRST_PM_PS

    text_sent = False
    try:
        await client.send_message(target_victim, text)
        text_sent = True
        _remember_first_message(resolved_id, intro_sent)
        await asyncio.sleep(random.uniform(0.23, 0.44))
        if sticker:
            await client.send_file(target_victim, sticker)
        suffix = " (первое сообщение, с припиской)" if intro_sent else ""
        print(f"[+] {get_time_str()} Успешно отправлено уведомление в ЛС: {target_victim.id}{suffix}")
    except errors.FloodWaitError as e:
        print(f"[-] FloodWait при отправке в ЛС: {e.seconds} сек. Ждем и пробуем снова...")
        await asyncio.sleep(e.seconds + 1)
        try:
            if not text_sent:
                await client.send_message(target_victim, text)
                text_sent = True
                _remember_first_message(resolved_id, intro_sent)
                await asyncio.sleep(random.uniform(0.23, 0.44))
            if sticker:
                await client.send_file(target_victim, sticker)
            print(f"[+] {get_time_str()} Успешно отправлено уведомление в ЛС после ожидания FloodWait: {target_victim.id}")
        except Exception as retry_err:
            print(f"[-] Повторная ошибка отправки после FloodWait: {retry_err}")
            if not text_sent and first_in_dialog:
                await send_pm_fallback(chat_id, reply_to, target_victim)
    except Exception as err:
        print(f"[-] Ошибка отправки сообщения в ЛС: {err}")
        if not text_sent and first_in_dialog:
            await send_pm_fallback(chat_id, reply_to, target_victim)
