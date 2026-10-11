"""Автореакции на сообщения про свободу/демократию/выборы.

Вынесено из main.py без изменений (включая отсутствие фильтра
по входящим сообщениям и кулдауна).
"""

import re

from telethon import events
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji

from client import client
from helpers import get_time_str


@client.on(events.NewMessage)
async def handle_freedom_reaction(event):
    """Автоматическая реакция 🕊 на любые сообщения, содержащие слово связанное с демократией"""
    if not event.text:
        return

    if re.search(r'свобод[аоуеын]|демократ[аиоуе]|выбор[аоуеыин]|1984', event.text, re.IGNORECASE):
        try:
            await client(SendReactionRequest(
                peer=event.chat_id,
                msg_id=event.id,
                reaction=[ReactionEmoji(emoticon='🕊')]
            ))
            print(f"[+] {get_time_str()} Поставлена реакция 🕊 на сообщение {event.id} со словом 'свобод*' в чате {event.chat_id}")
        except Exception as e:
            print(f"[-] Ошибка отправки реакции 🕊: {e}")
