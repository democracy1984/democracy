import asyncio
from datetime import datetime, timezone

from telethon.tl import types

import handlers.chat_actions as chat_actions
from core import state


def service_message(action):
    return types.MessageService(
        id=1,
        peer_id=types.PeerChannel(channel_id=123456),
        date=datetime.now(timezone.utc),
        action=action,
        from_id=types.PeerUser(user_id=777),
    )


def update(message):
    return types.UpdateNewChannelMessage(message=message, pts=0, pts_count=0)


def test_join_request_approved_sends_sticker(monkeypatch):
    sent = []

    async def fake_send_file(entity, file):
        sent.append(entity)

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(chat_actions.client, "send_file", fake_send_file)
    monkeypatch.setattr(chat_actions.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(state, "EAGLE_STICKER", object())
    monkeypatch.setattr(state, "PIGEON_STICKER", None)

    asyncio.run(chat_actions.handle_join_request_approved(
        update(service_message(types.MessageActionChatJoinedByRequest()))
    ))
    assert sent == [-1000000123456]


def test_other_service_message_is_ignored(monkeypatch):
    sent = []

    async def fake_send_file(entity, file):
        sent.append(entity)

    monkeypatch.setattr(chat_actions.client, "send_file", fake_send_file)
    asyncio.run(chat_actions.handle_join_request_approved(
        update(service_message(types.MessageActionChatEditTitle(title="X")))
    ))
    assert sent == []


def test_normal_message_is_ignored(monkeypatch):
    sent = []

    async def fake_send_file(entity, file):
        sent.append(entity)

    monkeypatch.setattr(chat_actions.client, "send_file", fake_send_file)
    message = types.Message(
        id=2,
        peer_id=types.PeerChannel(channel_id=123456),
        date=datetime.now(timezone.utc),
        message="Алас принят(а) в группу",
    )
    asyncio.run(chat_actions.handle_join_request_approved(update(message)))
    assert sent == []


def test_join_request_cooldown(monkeypatch):
    sent = []

    async def fake_send_file(entity, file):
        sent.append(entity)

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(chat_actions.client, "send_file", fake_send_file)
    monkeypatch.setattr(chat_actions.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(state, "EAGLE_STICKER", object())
    monkeypatch.setattr(state, "PIGEON_STICKER", None)

    async def run_twice():
        await chat_actions.handle_join_request_approved(
            update(service_message(types.MessageActionChatJoinedByRequest()))
        )
        await chat_actions.handle_join_request_approved(
            update(service_message(types.MessageActionChatJoinedByRequest()))
        )

    asyncio.run(run_twice())
    assert len(sent) == 1


def test_regular_chat_action_still_sends(monkeypatch):
    sent = []

    async def fake_send_file(entity, file):
        sent.append(entity)

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(chat_actions.client, "send_file", fake_send_file)
    monkeypatch.setattr(chat_actions.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(state, "EAGLE_STICKER", object())
    monkeypatch.setattr(state, "PIGEON_STICKER", None)

    class Event:
        new_title = None
        user_joined = True
        user_added = False
        user_id = 777
        chat_id = -100123456

    asyncio.run(chat_actions.handle_chat_action(Event()))
    assert sent == [-100123456]
