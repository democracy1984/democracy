"""Отслеживание личных диалогов и обновление профилей.

Любой входящий ЛС означает, что диалог с пользователем уже существует.
Заодно синхронизируем его актуальное имя/username в БД.
"""

from telethon import events

import state
from client import client
from identity import sync_sender_from_event


@client.on(events.NewMessage)
async def track_private_dialogs(event):
    """Любой входящий ЛС означает, что диалог с пользователем уже существует."""
    if event.is_private and event.sender_id:
        state.PM_DIALOG_USER_IDS.add(event.sender_id)
        await sync_sender_from_event(event)
    elif event.is_group:
        # В группах тоже обновляем профили: человек написал — видим актуальное имя
        await sync_sender_from_event(event)
