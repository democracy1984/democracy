"""Хендлер событий чата: вход участников, смена названия, заявки в группу.

Обычный вход ловится через ChatAction. Заявка, одобренная админом
(«Алас принят(а) в группу»), приходит как MessageService с action
MessageActionChatJoinedByRequest — этого ChatAction не умеет, поэтому
для неё отдельный Raw-хендлер.
"""

import asyncio
import random

from telethon import events, errors, utils
from telethon.tl import types

from core import state
from core.client import client
from config import USER_COOLDOWN_SECONDS
from core.database import update_chat_title
from core.helpers import check_and_update_cooldown, get_time_str


async def send_greeting_sticker(chat_id):
    """Приветственный орёл (или голубь) в чат."""
    try:
        await asyncio.sleep(random.uniform(0.34, 0.8))
        chat_sticker = state.EAGLE_STICKER if state.EAGLE_STICKER else state.PIGEON_STICKER
        if chat_sticker:
            await client.send_file(entity=chat_id, file=chat_sticker)
            print(f"[+] {get_time_str()} Отправлен приветственный Орёл в чат {chat_id}")
    except errors.FloodWaitError as e:
        print(f"[-] FloodWait при приветствии: {e.seconds} сек.")
    except Exception as e:
        print(f"[-] Ошибка отправки приветственного стикера: {e}")


@client.on(events.ChatAction)
async def handle_chat_action(event):
    """Обработка событий чата (вход участников, смена названия и т.д.)."""
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
        await send_greeting_sticker(event.chat_id)


@client.on(events.Raw(types=(types.UpdateNewMessage, types.UpdateNewChannelMessage)))
async def handle_join_request_approved(update):
    """Заявка одобрена: MessageActionChatJoinedByRequest («принят(а) в группу»)."""
    message = getattr(update, 'message', None)
    if not isinstance(message, types.MessageService):
        return
    if not isinstance(message.action, types.MessageActionChatJoinedByRequest):
        return
    if not isinstance(message.peer_id, (types.PeerChannel, types.PeerChat)):
        return
    if getattr(message, 'out', False):
        return

    chat_id = utils.get_peer_id(message.peer_id)
    user_id = getattr(message.from_id, 'user_id', None)
    user_key = f"id_{user_id}" if user_id else f"joinreq_{chat_id}"
    if check_and_update_cooldown(user_key):
        print(f"[*] Пропуск приветствия по заявке {user_key} (кулдаун {USER_COOLDOWN_SECONDS} сек)")
        return

    await send_greeting_sticker(chat_id)
    print(f"[+] {get_time_str()} Заявка одобрена в чате {chat_id} (пользователь {user_id})")
