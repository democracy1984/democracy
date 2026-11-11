import asyncio

import handlers.moderation as moderation
from services.promo import VICTORY_PHRASES


class Message:
    def __init__(self, text):
        self.message = text
        self.entities = []


class Chat:
    title = "Тестовый чат"


class Event:
    is_group = True
    chat_id = -1002329918083
    id = 42
    chat = Chat()

    def __init__(self, text, sender_id=7945156565):
        self.sender_id = sender_id
        self.message = Message(text)


def test_unmute_sends_victory_and_does_not_save(monkeypatch, db):
    sent = []

    async def fake_send_message(entity, text, reply_to=None):
        sent.append((entity, text, reply_to))

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(moderation.client, "send_message", fake_send_message)
    monkeypatch.setattr(moderation.asyncio, "sleep", no_sleep)

    text = (
        "Пользователь fraudleaker (https://t.me/fraudleak) (id 8363960791) "
        "был размучен администратором Krass Fyrrsel (id 1005328899)"
    )
    asyncio.run(moderation.handle_moderation_message(Event(text)))

    assert len(sent) == 1
    entity, sent_text, reply_to = sent[0]
    assert entity == -1002329918083
    assert reply_to == 42
    assert sent_text in VICTORY_PHRASES
    assert db.check_db_empty() is True


def test_unmute_miss_rose(monkeypatch, db):
    sent = []

    async def fake_send_message(entity, text, reply_to=None):
        sent.append((entity, text, reply_to))

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(moderation.client, "send_message", fake_send_message)
    monkeypatch.setattr(moderation.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(moderation, "ALLOWED_MODS", [609517172])  # MissRose

    asyncio.run(moderation.handle_moderation_message(
        Event("Fine, реля <3 can speak again.", sender_id=609517172)
    ))

    assert len(sent) == 1
    assert sent[0][1] in VICTORY_PHRASES
