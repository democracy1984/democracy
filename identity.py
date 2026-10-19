"""Синхронизация профилей пользователей из Telegram в БД.

Отображаемое имя и username сохраняются в момент наказания и со временем
устаревают. Здесь — общий хелпер: как только видим человека (сообщение в
чате, ЛС, новое действие бота), обновляем его имя/username во всех старых
записях, чтобы /stats и /top показывали актуальные данные.
"""

import time

from telethon.tl.types import User

from client import client
from database import format_display_name, sync_victim_identity
from helpers import get_time_str

# Не дёргаем БД чаще раза в минуту на одного пользователя (хот-путь сообщений)
_SYNC_INTERVAL_SECONDS = 60
_last_sync_at = {}
_log_counter = 0


def build_display_name(entity) -> str:
    """Отображаемое имя из сущности Telegram (имя фамилия → @username → ID)."""
    if isinstance(entity, User):
        return format_display_name(entity.first_name, entity.last_name, entity.username, entity.id)
    name = getattr(entity, 'title', None)
    return name or format_display_name(None, None, getattr(entity, 'username', None), getattr(entity, 'id', None))


def sync_user_identity(entity) -> bool:
    """Обновляет записи по уже полученной сущности пользователя."""
    if not isinstance(entity, User):
        return False
    if not entity.username and not entity.first_name:
        return False
    name = format_display_name(entity.first_name, entity.last_name, entity.username, entity.id)
    return bool(sync_victim_identity(entity.id, name, entity.username))


def sync_target_identity(entity):
    """Синхронизация из команд /stats и /top: ошибки не должны ломать команду."""
    try:
        if sync_user_identity(entity):
            print(f"[*] {get_time_str()} Обновлён профиль {entity.id}")
    except Exception as e:
        print(f"[-] Не удалось синхронизировать имя пользователя {getattr(entity, 'id', '?')}: {e}")


async def sync_sender_from_event(event) -> bool:
    """Синхронизирует профиль автора события (если это пользователь).

    Повторно проверяет одного и того же пользователя не чаще раза в минуту,
    чтобы не нагружать БД на каждом сообщении в чате.
    """
    try:
        sender = await event.get_sender()
    except Exception:
        return False
    if not isinstance(sender, User) or not sender.id:
        return False

    now = time.time()
    if now - _last_sync_at.get(sender.id, 0.0) < _SYNC_INTERVAL_SECONDS:
        return False
    _last_sync_at[sender.id] = now

    if len(_last_sync_at) > 5000:
        for uid, ts in list(_last_sync_at.items()):
            if now - ts > _SYNC_INTERVAL_SECONDS:
                del _last_sync_at[uid]

    if sync_user_identity(sender):
        global _log_counter
        _log_counter += 1
        if _log_counter % 50 == 0:
            print(f"[*] {get_time_str()} Обновлён профиль {sender.id}: "
                  f"{format_display_name(sender.first_name, sender.last_name, sender.username, sender.id)}")
        return True
    return False


async def sync_user_by_id(user_id) -> bool:
    """Синхронизирует профиль по ID (сущность берётся из кэша/Telegram)."""
    if not user_id:
        return False
    try:
        entity = await client.get_entity(user_id)
    except Exception:
        return False
    return sync_user_identity(entity)
