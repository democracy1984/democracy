"""Отслеживание личных диалогов: любой входящий ЛС = диалог уже существует.

Вынесено из main.py без изменений.
"""

from telethon import events

import state
from client import client


@client.on(events.NewMessage)
async def track_private_dialogs(event):
    """Любой входящий ЛС означает, что диалог с пользователем уже существует."""
    if event.is_private and event.sender_id:
        state.PM_DIALOG_USER_IDS.add(event.sender_id)
