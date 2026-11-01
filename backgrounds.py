"""Пользовательские GIF-фоны для карточек /stats.

Право на свой фон получают пользователи с STATS_BG_MIN_ACTIONS мутами/банами.
Файлы нормализуются в полосу CARD_STRIP_SIZE и хранятся в STATS_BG_DIR.
"""

import math
import os
import shutil
import subprocess
import tempfile

from PIL import Image

from config import (
    MATRIX_BG_PATH,
    STATS_BG_DIR,
    STATS_BG_MAX_DIMENSION,
    STATS_BG_MAX_FILE_MB,
    STATS_BG_MAX_FRAMES,
)
from database import (
    get_user_background,
    get_user_stats,
    remove_user_background,
    set_user_background,
)
from matrix_bg import is_matrix_user
from rendering import CARD_STRIP_SIZE, clear_gif_cache, crop_cover


class BackgroundError(ValueError):
    """Ошибка, которую можно показать пользователю."""


def get_actions_count(user_id, username=None):
    """Сколько всего мутов и банов у пользователя."""
    mutes, bans, _, _ = get_user_stats(user_id, username)
    return mutes + bans


def get_user_bg_path(user_id):
    """Существующий файл фона пользователя или None."""
    path = get_user_background(user_id) if user_id else None
    if path and os.path.isfile(path):
        return path
    return None


def resolve_stats_bg(user):
    """Фон для карточки /stats: пользовательский, иначе матричный, иначе None."""
    user_id = getattr(user, 'id', None) if user else None
    path = get_user_bg_path(user_id)
    if path:
        return path
    if is_matrix_user(user):
        return MATRIX_BG_PATH
    return None


def _frame_duration_ms(image):
    try:
        duration = int(image.info.get('duration', 50) or 50)
    except (TypeError, ValueError):
        duration = 50
    return max(20, min(200, duration))


def _check_source(source_path):
    if not os.path.isfile(source_path):
        raise BackgroundError("Файл не найден.")
    size_mb = os.path.getsize(source_path) / (1024 * 1024)
    if size_mb > STATS_BG_MAX_FILE_MB:
        raise BackgroundError(f"Файл больше {STATS_BG_MAX_FILE_MB} МБ.")


def _normalize_to_strip(source_path, dest_path):
    """Открывает GIF/WEBP, обрезает кадры в полосу и сохраняет нормализованный GIF."""
    _check_source(source_path)
    try:
        image = Image.open(source_path)
    except Exception:
        raise BackgroundError("Не удалось открыть файл как изображение.")

    with image:
        if image.format not in ('GIF', 'WEBP'):
            raise BackgroundError("Поддерживаются GIF или анимированный WEBP.")
        if image.width > STATS_BG_MAX_DIMENSION or image.height > STATS_BG_MAX_DIMENSION:
            raise BackgroundError(f"Слишком большое изображение (макс. {STATS_BG_MAX_DIMENSION}px).")

        try:
            frame_count = int(getattr(image, 'n_frames', 1) or 1)
        except Exception:
            raise BackgroundError("Не удалось прочитать кадры GIF.")

        # Слишком длинные гифки прореживаем, а не отклоняем целиком
        step = max(1, math.ceil(frame_count / STATS_BG_MAX_FRAMES))
        frames, durations = [], []
        for frame_index in range(0, frame_count, step):
            try:
                image.seek(frame_index)
                frame = crop_cover(image.convert('RGB'), CARD_STRIP_SIZE)
            except Exception:
                raise BackgroundError("Не удалось обработать один из кадров.")
            frames.append(frame)
            durations.append(_frame_duration_ms(image) * step)

    if not frames:
        raise BackgroundError("В файле не оказалось кадров.")

    os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
    tmp_path = dest_path + '.tmp'
    try:
        if len(frames) == 1:
            frames[0].save(tmp_path, 'GIF', loop=0)
        else:
            frames[0].save(
                tmp_path, 'GIF',
                save_all=True, append_images=frames[1:],
                duration=durations, loop=0, optimize=True,
            )
        os.replace(tmp_path, dest_path)
    except Exception as e:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise BackgroundError("Не удалось сохранить фон.") from e

    # Pillow может схлопнуть одинаковые кадры при optimize — считаем фактическое число
    try:
        with Image.open(dest_path) as saved:
            return int(getattr(saved, 'n_frames', len(frames)) or len(frames))
    except Exception:
        return len(frames)


def _convert_video_to_gif(source_path, dest_path):
    """MP4-анимация (то, как Telegram обычно присылает GIF) -> временный GIF."""
    if not shutil.which('ffmpeg'):
        raise BackgroundError("Пришли GIF файлом — MP4-анимации на этом сервере не поддерживаются.")
    command = [
        'ffmpeg', '-y', '-i', source_path,
        '-t', '8',
        '-vf', "fps=10,scale='min(602,iw)':-2:flags=lanczos",
        '-loop', '0', dest_path,
    ]
    try:
        subprocess.run(command, capture_output=True, timeout=45, check=True)
    except subprocess.TimeoutExpired:
        raise BackgroundError("Слишком длинная анимация.")
    except subprocess.CalledProcessError:
        raise BackgroundError("Не удалось сконвертировать анимацию.")
    if not os.path.isfile(dest_path):
        raise BackgroundError("Не удалось сконвертировать анимацию.")


def prepare_user_bg(user_id, source_path, is_video=False):
    """Нормализует GIF и сохраняет файл, не трогая БД. Возвращает (путь, кадры)."""
    os.makedirs(STATS_BG_DIR, exist_ok=True)
    dest_path = os.path.join(STATS_BG_DIR, f"{user_id}.gif")

    if is_video:
        with tempfile.TemporaryDirectory(dir=STATS_BG_DIR) as tmp_dir:
            converted = os.path.join(tmp_dir, 'converted.gif')
            _convert_video_to_gif(source_path, converted)
            frame_count = _normalize_to_strip(converted, dest_path)
    else:
        frame_count = _normalize_to_strip(source_path, dest_path)

    return dest_path, frame_count


def commit_user_bg(user_id, dest_path):
    """Записывает путь в БД и удаляет прежний файл. Вызывать из event loop."""
    old_path = get_user_background(user_id)
    set_user_background(user_id, dest_path)
    clear_gif_cache(dest_path)

    if old_path and os.path.realpath(old_path) != os.path.realpath(dest_path):
        clear_gif_cache(old_path)
        try:
            os.remove(old_path)
        except OSError:
            pass

    return old_path


def save_user_bg(user_id, source_path, is_video=False):
    """Нормализует, сохраняет и регистрирует фон. Возвращает (путь, число кадров)."""
    dest_path, frame_count = prepare_user_bg(user_id, source_path, is_video)
    commit_user_bg(user_id, dest_path)
    return dest_path, frame_count


def remove_user_bg(user_id):
    """Удаляет фон пользователя: запись в БД и файл. Возвращает прежний путь."""
    old_path = remove_user_background(user_id)
    if old_path:
        clear_gif_cache(old_path)
        try:
            os.remove(old_path)
        except OSError:
            pass
    return old_path
