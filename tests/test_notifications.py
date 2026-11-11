import asyncio

import services.notifications as notifications
from core import state
from tests.fakes import make_user


VICTIM = make_user(555000111, "Victim", None, is_self=False)


def test_first_message_has_ps_and_remembers(monkeypatch, db):
    sent = []

    async def fake_get_entity(value):
        return VICTIM

    async def fake_send_message(target, text, reply_to=None, parse_mode=None):
        sent.append(("message", getattr(target, "id", target), text, reply_to, parse_mode))

    async def fake_send_file(target, file, reply_to=None):
        sent.append(("file", getattr(target, "id", target), file))

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(notifications.client, "get_entity", fake_get_entity)
    monkeypatch.setattr(notifications.client, "send_message", fake_send_message)
    monkeypatch.setattr(notifications.client, "send_file", fake_send_file)
    monkeypatch.setattr(notifications.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(notifications, "_pm_dialogs_refreshed_at", 1e18)
    state.PM_DIALOG_USER_IDS.clear()
    state.PM_INTRO_SENT.clear()
    state.PM_OPT_OUT.clear()

    asyncio.run(notifications.try_send_pm(
        VICTIM.id, None, "promo", "sticker", chat_id=-100999, reply_to=42
    ))

    assert sent[0][0] == "message"
    assert "PS:" in sent[0][2]
    assert "/stopspamming" in sent[0][2]
    assert db.load_pm_intro_sent() == {VICTIM.id}
    assert sent[1][0] == "file"

    # Повторно — уже без PS
    sent.clear()
    asyncio.run(notifications.try_send_pm(VICTIM.id, None, "promo2", None))
    assert "PS:" not in sent[0][2]


def test_failed_dm_falls_back_to_chat(monkeypatch, db):
    sent = []
    fail_dm = {"value": True}

    async def fake_get_entity(value):
        return VICTIM

    async def fake_send_message(target, text, reply_to=None, parse_mode=None):
        if fail_dm["value"] and getattr(target, "id", target) == VICTIM.id:
            raise RuntimeError("privacy")
        sent.append(("message", getattr(target, "id", target), text, reply_to, parse_mode))

    async def fake_send_file(target, file, reply_to=None):
        sent.append(("file", getattr(target, "id", target), file))

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(notifications.client, "get_entity", fake_get_entity)
    monkeypatch.setattr(notifications.client, "send_message", fake_send_message)
    monkeypatch.setattr(notifications.client, "send_file", fake_send_file)
    monkeypatch.setattr(notifications.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(notifications, "_pm_dialogs_refreshed_at", 1e18)
    state.PM_DIALOG_USER_IDS.clear()
    state.PM_INTRO_SENT.clear()
    state.PM_OPT_OUT.clear()

    asyncio.run(notifications.try_send_pm(
        VICTIM.id, None, "promo", None, chat_id=-100999, reply_to=42
    ))

    assert sent
    assert sent[0][1] == -100999
    assert "tg://user?id=555000111" in sent[0][2]
    assert db.load_pm_intro_sent() == set()


def test_opt_out_blocks_message(monkeypatch, db):
    sent = []

    async def fake_get_entity(value):
        return VICTIM

    async def fake_send_message(*args, **kwargs):
        sent.append(args)

    monkeypatch.setattr(notifications.client, "get_entity", fake_get_entity)
    monkeypatch.setattr(notifications.client, "send_message", fake_send_message)
    monkeypatch.setattr(notifications, "_pm_dialogs_refreshed_at", 1e18)
    state.PM_DIALOG_USER_IDS.clear()
    state.PM_INTRO_SENT.clear()
    state.PM_OPT_OUT.clear()
    state.PM_OPT_OUT.add(VICTIM.id)

    asyncio.run(notifications.try_send_pm(
        VICTIM.id, None, "promo", None, chat_id=-100999, reply_to=42
    ))
    assert sent == []
