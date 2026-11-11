import asyncio
import io
import os

from PIL import Image

import handlers.commands as cmd
import handlers.custom_bg as custom_bg
from core import state
from services import backgrounds
from tests.fakes import FakeEvent, FakeMsg, make_user


A = -1001737370533
B = -1002338569737
C = -1003542986112
UID = 100


async def _no_entities(user_ids):
    return {}


async def _send_file(*args, **kwargs):
    return None


def test_help_lists_new_commands():
    ev = FakeEvent("/help")
    asyncio.run(cmd.handle_commands(ev))
    text = ev.replies[-1]
    assert "/setbg" in text
    assert "/globaltop" in text


def test_top_private_uses_groups_where_user_was_punished(monkeypatch, db):
    db.save_batch_actions([
        (A, "Chat A", UID, None, "Me", "mute", "1h", "x"),
        (B, "Chat B", UID, None, "Me", "ban", "permanent", "x"),
        (C, "Chat C", 101, None, "Other", "mute", "1h", "x"),
    ])
    monkeypatch.setattr(cmd, "resolve_current_names", _no_entities)
    ev = FakeEvent("/top", sender=make_user(UID, "Me"))
    asyncio.run(cmd.handle_commands(ev))

    text = ev.replies[-1]
    assert "по 2 группам" in text
    assert "Chat C" not in text


def test_top_group_renders_chat_card(monkeypatch, db):
    db.save_action(A, "Chat A", 1, None, "User", "mute", "1h", "spam")
    captured = {}

    def fake_render(title, sections, **kwargs):
        captured["title"] = title
        captured["sections"] = sections
        captured.update(kwargs)
        return io.BytesIO(b"GIF89a")

    monkeypatch.setattr(cmd, "resolve_current_names", _no_entities)
    monkeypatch.setattr(cmd, "render_telegram_bubble", fake_render)
    monkeypatch.setattr(cmd.client, "send_file", _send_file)

    ev = FakeEvent("/top", private=False, chat_id=A, chat_title="Chat A")
    asyncio.run(cmd.handle_commands(ev))
    assert captured["title"] == "ТОП чата"
    assert captured.get("strip_gif_path") is None
    assert any("Chat A" in str(section) for section in captured["sections"])


def test_top_by_query(monkeypatch, db):
    db.save_action(A, "Chat A", 1, None, "User", "mute", "1h", "spam")
    monkeypatch.setattr(cmd, "resolve_current_names", _no_entities)

    async def fake_chats():
        return [{"id": A, "title": "Chat A", "username": None}]

    monkeypatch.setattr(cmd, "get_account_chats", fake_chats)
    ev = FakeEvent("/top Chat A")
    asyncio.run(cmd.handle_commands(ev))
    text = ev.replies[-1]
    assert "Chat A" in text
    assert "Всего наказаний" in text


def test_stats_uses_custom_background(monkeypatch, tmp_path, db):
    db.save_action(A, "Chat A", UID, None, "Me", "mute", "1h", "spam")
    monkeypatch.setattr(backgrounds, "STATS_BG_DIR", str(tmp_path / "bg"))

    src = tmp_path / "src.gif"
    frames = [Image.new("RGB", (80, 50), (i * 40, 20, 100)) for i in range(3)]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=80, loop=0)
    path, _ = backgrounds.save_user_bg(UID, str(src))

    captured = {}

    def fake_render(title, sections, **kwargs):
        captured["title"] = title
        captured["strip_gif_path"] = kwargs.get("strip_gif_path")
        return io.BytesIO(b"GIF89a")

    monkeypatch.setattr(cmd, "render_telegram_bubble", fake_render)
    monkeypatch.setattr(cmd.client, "send_file", _send_file)

    ev = FakeEvent("/stats", private=False, chat_id=A, chat_title="Chat A",
                   sender=make_user(UID, "Me"))
    asyncio.run(cmd.handle_commands(ev))
    assert captured["strip_gif_path"] == path


def test_setbg_group_is_silent():
    ev = FakeEvent("/setbg", private=False, message=FakeMsg())
    asyncio.run(custom_bg.handle_setbg(ev))
    assert ev.replies == []


def test_setbg_below_threshold(monkeypatch):
    monkeypatch.setattr(custom_bg, "get_actions_count", lambda uid: 99)
    ev = FakeEvent("/setbg", message=FakeMsg())
    asyncio.run(custom_bg.handle_setbg(ev))
    assert "осталось 1" in ev.replies[-1]


def test_setbg_success(monkeypatch, tmp_path, db):
    src = tmp_path / "src.gif"
    frames = [Image.new("RGB", (80, 50), (i * 40, 20, 100)) for i in range(3)]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=80, loop=0)

    bg_dir = tmp_path / "bg"
    monkeypatch.setattr(backgrounds, "STATS_BG_DIR", str(bg_dir))
    monkeypatch.setattr(custom_bg, "STATS_BG_DIR", str(bg_dir))
    monkeypatch.setattr(custom_bg, "get_actions_count", lambda uid: 100)

    ev = FakeEvent("/setbg", message=FakeMsg(path=str(src)))
    asyncio.run(custom_bg.handle_setbg(ev))

    assert "Фон принят" in ev.replies[-1]
    path = db.get_user_background(UID)
    assert path and os.path.exists(path)
    assert Image.open(path).size == backgrounds.CARD_STRIP_SIZE
