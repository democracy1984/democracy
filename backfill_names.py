"""Разовая синхронизация имён/username для всех пользователей из БД.

Проходит по тем, кого бот видел в наказаниях, берёт их актуальные профили
из Telegram и обновляет имя/username во всех старых записях.

Запуск (бот предварительно остановить — сессия занята):
    .venv/bin/python backfill_names.py            # обновить
    .venv/bin/python backfill_names.py --dry-run  # только показать, что изменится

Пути можно переопределить переменными окружения (удобно для теста на копии):
    DEMOCRACY_DB=test.db DEMOCRACY_SESSION_DIR=/tmp/sess .venv/bin/python backfill_names.py

Скрипт идемпотентен: повторный запуск не находит изменений.
"""

import asyncio
import os
import sys

from telethon import errors
from telethon.tl.types import User

from client import client
from database import format_display_name, get_conn, init_db, sync_victim_identity


def get_user_ids():
    """Все user_id из базы (без NULL)."""
    cursor = get_conn().cursor()
    cursor.execute("SELECT DISTINCT user_id FROM actions WHERE user_id IS NOT NULL ORDER BY user_id")
    return [row[0] for row in cursor.fetchall()]


def current_names(user_id):
    """Сколько строк с каждым сохранённым именем: [(имя, число), ...]."""
    cursor = get_conn().cursor()
    cursor.execute('''
        SELECT victim_name, COUNT(*) FROM actions
        WHERE user_id = ? GROUP BY victim_name ORDER BY COUNT(*) DESC
    ''', (user_id,))
    return cursor.fetchall()


async def resolve_entity(user_id):
    """Сущность из Telegram с одной повторной попыткой при FloodWait."""
    try:
        return await client.get_entity(user_id)
    except errors.FloodWaitError as e:
        print(f"\n    [-] FloodWait {e.seconds} сек, ждём...")
        await asyncio.sleep(e.seconds + 1)
        try:
            return await client.get_entity(user_id)
        except Exception:
            return None
    except Exception:
        return None


async def main():
    dry_run = "--dry-run" in sys.argv

    init_db()
    user_ids = get_user_ids()
    print(f"[*] Пользователей в базе: {len(user_ids)}"
          f"{' (предпросмотр, ничего не меняем)' if dry_run else ''}")

    await client.start()
    me = await client.get_me()
    print(f"[*] Аккаунт: {me.first_name} (@{me.username})")

    updated_users = 0
    updated_rows = 0
    failed = 0

    for idx, user_id in enumerate(user_ids, 1):
        entity = await resolve_entity(user_id)
        if not isinstance(entity, User):
            failed += 1
            continue

        name = format_display_name(entity.first_name, entity.last_name, entity.username, entity.id)
        before = current_names(user_id)

        if dry_run:
            stale = [(n, cnt) for n, cnt in before if n != name]
            if stale:
                print(f"    [~] {user_id}: {stale} -> «{name}»")
            continue

        rows = sync_victim_identity(user_id, name, entity.username)
        if rows:
            updated_users += 1
            updated_rows += rows
            print(f"    [+] {user_id}: обновлено строк: {rows} -> «{name}»")

        # Компактный прогресс каждые 25 пользователей
        if idx % 25 == 0:
            print(f"    ... {idx}/{len(user_ids)} (обновлено: {updated_users})")

        await asyncio.sleep(0.35)  # не частим с запросами к Telegram

    print(f"\n[+] Готово. Пользователей обновлено: {updated_users}, строк: {updated_rows}, "
          f"не удалось разрешить (нет в кэше/удалены): {failed}")


if __name__ == "__main__":
    asyncio.run(main())
