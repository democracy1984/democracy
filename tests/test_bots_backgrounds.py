import os
import stat
import subprocess

import pytest
from PIL import Image
from telethon.tl.types import User

import config
from core import bots
from services import backgrounds
from services.matrix_bg import is_matrix_user


def user(uid, first="X", username=None):
    return User(
        id=uid, is_self=False, contact=False, mutual_contact=False, deleted=False,
        bot=False, bot_chat_history=False, bot_nochats=False, verified=False,
        restricted=False, min=False, bot_inline_geo=False, support=False, scam=False,
        fake=False, access_hash=1, first_name=first, username=username,
    )


def make_gif(path, frames=4, size=(100, 80)):
    images = [Image.new("RGB", size, (i * 50 % 255, 20, 200)) for i in range(frames)]
    images[0].save(
        path, save_all=True, append_images=images[1:],
        duration=80, loop=0,
    )


@pytest.fixture
def bg_env(tmp_path, db, monkeypatch):
    monkeypatch.setattr(backgrounds, "STATS_BG_DIR", str(tmp_path / "bg"))
    return backgrounds


def test_bots_config():
    assert config.ALLOWED_MODS is bots.ALLOWED_MODS
    assert 7945156565 in bots.ALLOWED_MODS
    assert "GroupHelp" in bots.bots_label()
    assert bots.bot_name_by_key("iris").startswith("Iris")


def test_matrix_identity_is_not_name_based():
    assert is_matrix_user(user(5963786103, "Whatever")) is True
    assert is_matrix_user(user(1, "X", "Matrixivo")) is True
    assert is_matrix_user(user(1, "Matrix", "not_matrix")) is False


def test_ffmpeg_status_is_a_string():
    status = backgrounds.ffmpeg_status()
    assert isinstance(status, str)
    assert "ffmpeg" in status or "MP4" in status


def test_actions_count_by_id_only(db):
    db.save_batch_actions([
        (-1001, "Chat", 5, None, "User", "mute", "1h", "x"),
        (-1001, "Chat", 5, None, "User", "ban", "permanent", "x"),
        (-1001, "Chat", None, "5", "Legacy", "mute", "1h", "x"),
    ])
    assert backgrounds.get_actions_count(5) == 2


def test_save_resolve_remove(bg_env, tmp_path, db):
    src = tmp_path / "src.gif"
    make_gif(src)
    path, frames = bg_env.save_user_bg(10, str(src))

    assert frames >= 1
    assert os.path.isfile(path)
    assert db.get_user_background(10) == path
    assert Image.open(path).size == bg_env.CARD_STRIP_SIZE
    assert bg_env.resolve_stats_bg(user(10)) == path

    if os.name == "posix":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(bg_env.STATS_BG_DIR).st_mode) == 0o700

    bg_env.remove_user_bg(10)
    assert not os.path.exists(path)
    assert db.get_user_background(10) is None


def test_path_containment(bg_env, tmp_path, db):
    outside = tmp_path / "outside.gif"
    make_gif(outside)
    db.set_user_background(11, str(outside))

    assert bg_env.get_user_bg_path(11) is None
    assert bg_env.resolve_stats_bg(user(11)) is None

    removed = bg_env.remove_user_bg(11)
    assert removed == str(outside)
    assert outside.exists()
    assert db.get_user_background(11) is None


def test_matrix_fallback(bg_env):
    assert bg_env.resolve_stats_bg(user(5963786103, "Whatever")) == bg_env.MATRIX_BG_PATH
    assert bg_env.resolve_stats_bg(user(1, "Matrix", "not_matrix")) is None


def test_invalid_user_id(bg_env, tmp_path):
    src = tmp_path / "src.gif"
    make_gif(src)
    with pytest.raises(bg_env.BackgroundError):
        bg_env.prepare_user_bg("not-an-int", str(src))


def test_non_gif_rejected(bg_env, tmp_path):
    src = tmp_path / "src.png"
    Image.new("RGB", (50, 50), (255, 0, 0)).save(src)
    with pytest.raises(bg_env.BackgroundError):
        bg_env.save_user_bg(12, str(src))


def test_video_conversion(bg_env, tmp_path):
    ffmpeg = bg_env.ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg недоступен")
    source = tmp_path / "src.mp4"
    try:
        subprocess.run([
            ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10",
            "-t", "1", "-pix_fmt", "yuv420p", str(source),
        ], check=True, capture_output=True, timeout=30)
    except Exception:
        pytest.skip("не удалось создать тестовое видео")

    path, frames = bg_env.save_user_bg(13, str(source), is_video=True)
    assert os.path.isfile(path)
    assert frames >= 1
    assert Image.open(path).size == bg_env.CARD_STRIP_SIZE
