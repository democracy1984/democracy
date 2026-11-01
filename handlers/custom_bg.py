"""Команда /setbg: свой GIF-фон для карточек /stats.

Работает только в ЛС (как /help). До STATS_BG_MIN_ACTIONS мутов+банов
команда отказывает и показывает, сколько осталось. После порога можно
прислать GIF вместе с командой или ответом на GIF; /setbg off убирает фон.
"""

import asyncio
import os
import tempfile

from telethon import events

from backgrounds import (
    BackgroundError,
    commit_user_bg,
    get_actions_count,
    prepare_user_bg,
    remove_user_bg,
)
from client import client
from config import (
    STATS_BG_DIR,
    STATS_BG_MAX_FILE_MB,
    STATS_BG_MIN_ACTIONS,
    STATS_BG_UPLOAD_COOLDOWN_SECONDS,
)
from helpers import check_and_update_cooldown, get_time_str
from matrix_bg import is_matrix_user


def _parse_command(event):
    text = (event.text or '').strip()
    if not text:
        return None, ''
    parts = text.split(maxsplit=1)
    command = parts[0].split('@', 1)[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ''
    return command, arg


def _media_document(message):
    """GIF/анимация из сообщения (текущего или reply)."""
    if not message:
        return None
    return getattr(message, 'gif', None) or getattr(message, 'document', None)


def _media_kind(doc):
    mime = (getattr(doc, 'mime_type', '') or '').lower()
    if mime == 'image/gif':
        return 'gif'
    if mime == 'image/webp':
        return 'webp'
    if mime == 'video/mp4':
        return 'video'
    return None


@client.on(events.NewMessage)
async def handle_setbg(event):
    command, arg = _parse_command(event)
    if command != '/setbg':
        return

    # Как /help: в группах/каналах команда молчит
    if not event.is_private:
        return

    sender = await event.get_sender()
    if not sender:
        return

    total = get_actions_count(sender.id, getattr(sender, 'username', None))
    if total < STATS_BG_MIN_ACTIONS and not is_matrix_user(sender):
        left = STATS_BG_MIN_ACTIONS - total
        await event.reply(
            f"📊 У тебя {total} наказаний (муты + баны). "
            f"До своего фона осталось {left}."
        )
        return

    if arg.lower() in ('off', 'remove', 'reset', 'убрать', 'удалить'):
        removed = remove_user_bg(sender.id)
        if removed:
            await event.reply("🗑 Фон удалён. На карточках снова стандартный вид.")
            print(f"[*] {get_time_str()} Пользователь {sender.id} удалил фон /stats")
        else:
            await event.reply("У тебя и так нет своего фона.")
        return

    message = event.message
    document = _media_document(message)
    if not document and event.is_reply:
        message = await event.get_reply_message()
        document = _media_document(message)

    if not document:
        await event.reply(
            "🎨 Пришли GIF вместе с /setbg или ответь /setbg на GIF.\n"
            "Убрать свой фон: /setbg off"
        )
        return

    kind = _media_kind(document)
    if not kind:
        await event.reply("🎨 Поддерживаются GIF, анимированный WEBP и MP4-анимации.")
        return

    size = getattr(document, 'size', 0) or 0
    if size > STATS_BG_MAX_FILE_MB * 1024 * 1024:
        await event.reply(f"📦 Файл слишком большой (макс. {STATS_BG_MAX_FILE_MB} МБ).")
        return

    if check_and_update_cooldown(f"setbg_{sender.id}", STATS_BG_UPLOAD_COOLDOWN_SECONDS):
        await event.reply("⏳ Подожди немного перед следующей загрузкой фона.")
        return

    os.makedirs(STATS_BG_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f"setbg_{sender.id}_", suffix='.bin', dir=STATS_BG_DIR)
    os.close(fd)
    downloaded_path = None

    try:
        downloaded_path = await message.download_media(file=tmp_path)
        if not downloaded_path:
            await event.reply("❌ Не удалось скачать файл. Попробуй ещё раз.")
            return

        try:
            dest_path, frames = await asyncio.to_thread(
                prepare_user_bg, sender.id, downloaded_path, kind == 'video'
            )
            commit_user_bg(sender.id, dest_path)
        except BackgroundError as e:
            await event.reply(f"❌ {e}")
            return
        except Exception as e:
            print(f"[-] Ошибка сохранения фона {sender.id}: {e}")
            await event.reply("❌ Не удалось обработать GIF.")
            return

        await event.reply(
            f"✅ Фон принят! Он будет на твоих карточках /stats в чатах.\n"
            f"Кадров: {frames}. Убрать: /setbg off"
        )
        print(f"[+] {get_time_str()} Пользователь {sender.id} обновил фон /stats (кадров: {frames})")
    finally:
        for path in {tmp_path, downloaded_path}:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
