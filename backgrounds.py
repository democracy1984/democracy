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

try:
    import imageio_ffmpeg
except ImportError:  # пакет опционален: GIF/WEBP работают и без него
    imageio_ffmpeg = None

from config import (
    MATRIX_BG_PATH,
    STATS_BG_ALLOW_VIDEO,
    STATS_BG_DIR,
    STATS_BG_MAX_DIMENSION,
    STATS_BG_MAX_FILE_MB,
    STATS_BG_MAX_FRAMES,
    STATS_BG_MAX_SOURCE_FRAMES,
)
from database import (
    get_user_actions_total,
    get_user_background,
    remove_user_background,
    set_user_background,
)
from matrix_bg import is_matrix_user
from rendering import CARD_STRIP_SIZE, clear_gif_cache, crop_cover


class BackgroundError(ValueError):
    """Ошибка, которую можно показать пользователю."""


def get_actions_count(user_id):
    """Сколько всего мутов и банов у пользователя (строго по user_id)."""
    return get_user_actions_total(user_id)


def _is_managed_path(path):
    """Путь лежит внутри STATS_BG_DIR и ведёт на .gif (защита от подмены в БД)."""
    if not path or not path.lower().endswith('.gif'):
        return False
    base = os.path.realpath(STATS_BG_DIR)
    try:
        real = os.path.realpath(path)
        return os.path.commonpath([base, real]) == base
    except (OSError, ValueError):
        return False


def get_user_bg_path(user_id):
    """Существующий файл фона пользователя или None."""
    path = get_user_background(user_id) if user_id else None
    if path and _is_managed_path(path) and os.path.isfile(path):
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
        if frame_count > STATS_BG_MAX_SOURCE_FRAMES:
            raise BackgroundError(
                f"Слишком длинная гифка (макс. {STATS_BG_MAX_SOURCE_FRAMES} кадров)."
            )

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
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, dest_path)
        os.chmod(dest_path, 0o600)
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


def ffmpeg_path():
    """Ищет ffmpeg: env → PATH → типовые пути → бинарник из imageio-ffmpeg."""
    explicit = os.environ.get('FFMPEG_BINARY')
    if explicit and os.path.isfile(explicit) and os.access(explicit, os.X_OK):
        return explicit

    found = shutil.which('ffmpeg')
    if found:
        return found

    for candidate in (
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        '/bin/ffmpeg',
        os.path.expanduser('~/.local/bin/ffmpeg'),
        '/opt/ffmpeg/bin/ffmpeg',
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    if imageio_ffmpeg is not None:
        try:
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            print(f"[-] imageio-ffmpeg не смог отдать бинарник: {e}")
    return None


def ffmpeg_status():
    """Строка для лога при старте."""
    if not STATS_BG_ALLOW_VIDEO:
        return "MP4-фоны отключены (STATS_BG_ALLOW_VIDEO=False)"
    path = ffmpeg_path()
    if path:
        return f"ffmpeg найден: {path}"
    return "ffmpeg не найден — MP4-фоны недоступны (GIF/WEBP работают)"


def _convert_video_to_gif(source_path, dest_path):
    """MP4-анимация (то, как Telegram обычно присылает GIF) -> временный GIF."""
    if not STATS_BG_ALLOW_VIDEO:
        raise BackgroundError("MP4-анимации отключены — пришли GIF файлом.")
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        print("[-] ffmpeg не найден: проверь PATH, FFMPEG_BINARY или установи imageio-ffmpeg")
        raise BackgroundError(
            "На сервере не найден ffmpeg. Установи ffmpeg или imageio-ffmpeg "
            "(pip install imageio-ffmpeg), либо пришли GIF файлом."
        )

    command = [
        ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
        '-probesize', '5M', '-analyzeduration', '2M',
        '-i', source_path,
        '-t', '8',
        '-threads', '1',
        '-an',
        '-vf', "fps=10,scale='min(602,iw)':-2:flags=lanczos",
        '-loop', '0', '-f', 'gif', dest_path,
    ]
    # Ограничиваем ресурсы дочернего ffmpeg (Linux; prlimit из util-linux)
    if shutil.which('prlimit'):
        command = [
            'prlimit', '--cpu=10', '--as=1073741824',
            '--fsize=33554432', '--nofile=64', '--',
        ] + command

    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=45,
            check=True,
        )
    except subprocess.TimeoutExpired:
        print(f"[-] ffmpeg timeout при конвертации {source_path}")
        raise BackgroundError("Слишком длинная анимация.")
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b'').decode('utf-8', 'replace').strip()
        print(f"[-] ffmpeg ошибка (код {e.returncode}): {stderr[-1500:] or '<пусто>'}")
        raise BackgroundError("Не удалось сконвертировать анимацию.")
    if not os.path.isfile(dest_path):
        raise BackgroundError("Не удалось сконвертировать анимацию.")


def prepare_user_bg(user_id, source_path, is_video=False):
    """Нормализует GIF и сохраняет файл, не трогая БД. Возвращает (путь, кадры)."""
    if not isinstance(user_id, int) or user_id <= 0:
        raise BackgroundError("Некорректный пользователь.")
    os.makedirs(STATS_BG_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(STATS_BG_DIR, 0o700)
    except OSError:
        pass
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

    if old_path and _is_managed_path(old_path) and os.path.realpath(old_path) != os.path.realpath(dest_path):
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
    if old_path and _is_managed_path(old_path):
        clear_gif_cache(old_path)
        try:
            os.remove(old_path)
        except OSError:
            pass
    return old_path
