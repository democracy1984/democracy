"""Работа с базой данных бота.

Единая схема и функции доступа к SQLite-базе для всех модулей проекта.

Соединение с SQLite создаётся один раз и переиспользуется всеми
функциями (раньше каждый вызов открывал и закрывал базу заново).
Это безопасно: весь код асинхронный и однопоточный, доступ к базе
идёт последовательно из event loop.
"""

import sqlite3
import atexit
import os

DB_PATH = os.environ.get("DEMOCRACY_DB", "bot_stats.db")

_conn = None


def get_conn() -> sqlite3.Connection:
    """Возвращает общее соединение с БД, создавая его при первом обращении."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")   # устойчивее к параллельным чтениям
        _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


def close_db():
    """Закрывает общее соединение (вызывается при выходе процесса)."""
    global _conn
    if _conn is not None:
        try:
            _conn.commit()
        except Exception:
            pass
        _conn.close()
        _conn = None


atexit.register(close_db)


def init_db():
    """Инициализация базы данных и создание таблиц."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            chat_title TEXT,
            user_id INTEGER,
            username TEXT,
            victim_name TEXT,
            action_type TEXT,
            duration TEXT,
            reason TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pm_opt_out (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_user_id ON actions (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_chat_id ON actions (chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_action_type ON actions (action_type)')
    conn.commit()
    migrate_legacy_chat_ids()


def load_pm_opt_out() -> set:
    """Загружает список user_id, отписавшихся от ЛС, из БД."""
    cursor = get_conn().cursor()
    cursor.execute("SELECT user_id FROM pm_opt_out")
    rows = {row[0] for row in cursor.fetchall()}
    return rows


def save_pm_opt_out(user_id: int):
    """Добавляет user_id в таблицу pm_opt_out."""
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO pm_opt_out (user_id) VALUES (?)", (user_id,))
    conn.commit()


def remove_pm_opt_out(user_id: int):
    """Удаляет user_id из таблицы pm_opt_out."""
    conn = get_conn()
    conn.execute("DELETE FROM pm_opt_out WHERE user_id = ?", (user_id,))
    conn.commit()


def migrate_legacy_chat_ids():
    """Одноразовая миграция: сырые id из скрапера (1737370533) приводим к marked-форме realtime-хендлеров (-1001737370533).
    ponytail: legacy-group ghost rows (marked -id) тоже попали бы в -100, но в этой БД таких нет; realtime пишет правильный id при первом событии."""
    conn = get_conn()
    changed = conn.execute("UPDATE actions SET chat_id = -(1000000000000 + chat_id) WHERE chat_id > 0").rowcount
    if changed:
        conn.execute("UPDATE actions SET chat_title = (SELECT chat_title FROM actions a2 WHERE a2.chat_id = actions.chat_id ORDER BY a2.id DESC LIMIT 1)")
    conn.commit()


def check_db_empty():
    """Проверяет, пуста ли таблица логов."""
    cursor = get_conn().cursor()
    cursor.execute("SELECT COUNT(*) FROM actions")
    count = cursor.fetchone()[0]
    return count == 0


def save_action(chat_id, chat_title, user_id, username, victim_name, action_type, duration, reason):
    """Сохранение одного события в БД."""
    conn = get_conn()
    conn.execute('''
        INSERT INTO actions (chat_id, chat_title, user_id, username, victim_name, action_type, duration, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (chat_id, chat_title, user_id, username, victim_name, action_type, duration, reason))
    conn.commit()


def update_chat_title(chat_id, new_title):
    """Обновление названия чата во всех существующих записях БД."""
    conn = get_conn()
    conn.execute("UPDATE actions SET chat_title = ? WHERE chat_id = ?", (new_title, chat_id))
    conn.commit()


def save_batch_actions(actions_list):
    """Массовое сохранение событий (используется при автоматическом скрапинге)."""
    if not actions_list:
        return
    conn = get_conn()
    conn.executemany('''
        INSERT INTO actions (chat_id, chat_title, user_id, username, victim_name, action_type, duration, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', actions_list)
    conn.commit()


def _junk_name(name):
    """Имя-заглушка (точка, невидимый символ и т.п.) — по нему матчить нельзя."""
    return not name or name.strip('. \u200b\u200c\u200d\ufeff') == ''


def lookup_user_by_victim_name(victim_name):
    """Ищет реальный user_id по отображаемому имени — только если имя однозначно.

    Работает, когда в сообщении бота не оказалось ни ID, ни @username: если имя
    ровно у одного человека во всей базе (все известные записи указывают на один
    user_id), считаем, что безымянные записи — его. Если имя засвечено у разных
    людей — не угадываем и возвращаем None.
    """
    if not victim_name or _junk_name(victim_name):
        return None
    cursor = get_conn().cursor()
    cursor.execute('''
        SELECT user_id FROM actions
        WHERE victim_name = ? AND user_id IS NOT NULL
        GROUP BY user_id
        LIMIT 2
    ''', (victim_name,))
    rows = cursor.fetchall()
    if len(rows) == 1:
        return rows[0][0]
    return None  # имени нет или оно неоднозначно


def backfill_victim_user_id(victim_name, user_id):
    """Привязывает известный user_id к старым записям, где его не было.

    Обновляются только строки с user_id IS NULL (записи с уже известным ID
    никогда не перезаписываются). Вызывать только когда имя однозначно
    указывает на этого пользователя. Возвращает число обновлённых строк.
    """
    if not user_id or not victim_name or _junk_name(victim_name):
        return 0
    conn = get_conn()
    cursor = conn.execute('''
        UPDATE actions SET user_id = ?
        WHERE victim_name = ? AND user_id IS NULL
    ''', (user_id, victim_name))
    conn.commit()
    return cursor.rowcount


def format_display_name(first_name, last_name=None, username=None, user_id=None):
    """Единый формат отображаемого имени (как в /stats): имя фамилия → @username → ID."""
    name = (first_name or '').strip()
    if last_name:
        name += f" {last_name}"
    name = name.strip()
    if not name and username:
        name = f"@{username}"
    if not name and user_id:
        name = f"ID {user_id}"
    return name


def sync_victim_identity(user_id, victim_name=None, username=None):
    """Обновляет имя/username во ВСЕХ записях пользователя.

    Вызывается, когда видим актуальный профиль из Telegram (новое сообщение,
    действие бота), чтобы /stats и /top не показывали старое имя. Обновляются
    в том числе строки с устаревшими вариантами имени (например, если раньше
    человек писался иначе). Возвращает число обновлённых строк.
    """
    if not user_id or (not victim_name and not username):
        return 0

    sets, params, changed_conditions, check_params = [], [], [], []
    if victim_name and not _junk_name(victim_name):
        sets.append("victim_name = ?")
        params.append(victim_name)
        changed_conditions.append("(victim_name IS NULL OR victim_name != ?)")
        check_params.append(victim_name)
    if username:
        sets.append("username = ?")
        params.append(username)
        changed_conditions.append("(username IS NULL OR username != ?)")
        check_params.append(username)
    if not sets:
        return 0

    conn = get_conn()
    cursor = conn.execute(
        f"UPDATE actions SET {', '.join(sets)} WHERE user_id = ? AND ({' OR '.join(changed_conditions)})",
        params + [user_id] + check_params,
    )
    conn.commit()
    return cursor.rowcount


def get_user_stats(user_id, username):
    """Получение индивидуальной статистики пользователя из БД.

    Матч строго по стабильным идентификаторам: user_id и username.
    Записи без ID («безымянные») добираются бэкфиллом ID, когда он
    становится известен (см. backfill_victim_user_id).
    """
    where = "user_id = ?"
    params = [user_id]
    if username and username not in ('.', ' '):
        where += " OR username = ?"
        params.append(username)
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(f'''
        SELECT COUNT(*) FROM actions
        WHERE action_type = 'mute' AND ({where})
    ''', params)
    mutes_count = cursor.fetchone()[0]

    cursor.execute(f'''
        SELECT COUNT(*) FROM actions
        WHERE action_type = 'ban' AND ({where})
    ''', params)
    bans_count = cursor.fetchone()[0]

    cursor.execute(f'''
        SELECT 
            (SELECT chat_title FROM actions a2 WHERE a2.chat_id = a.chat_id ORDER BY a2.id DESC LIMIT 1) as latest_title,
            COUNT(*) as cnt 
        FROM actions a
        WHERE {where}
        GROUP BY chat_id
        ORDER BY cnt DESC
    ''', params)
    chats_data = cursor.fetchall()

    cursor.execute(f'''
        SELECT reason, COUNT(*) as cnt FROM actions
        WHERE {where}
        GROUP BY reason
        ORDER BY cnt DESC
        LIMIT 3
    ''', params)
    reasons_data = cursor.fetchall()

    return mutes_count, bans_count, chats_data, reasons_data


def get_global_top():
    """Получение глобального топа для администратора.

    Каждая строка: (user_id, name, mutes, bans, total). user_id нужен,
    чтобы показать актуальное имя пользователя из Telegram.
    """
    cursor = get_conn().cursor()

    cursor.execute('''
        SELECT
            user_id,
            COALESCE(victim_name, '@' || username, 'ID ' || user_id) as name,
            SUM(CASE WHEN action_type = 'mute' THEN 1 ELSE 0 END) as mutes,
            SUM(CASE WHEN action_type = 'ban' THEN 1 ELSE 0 END) as bans,
            COUNT(*) as total
        FROM actions
        GROUP BY COALESCE(user_id, username, victim_name)
        ORDER BY total DESC
        LIMIT 15
    ''')
    top_users = cursor.fetchall()

    cursor.execute('''
        SELECT reason, COUNT(*) as cnt
        FROM actions
        GROUP BY reason
        ORDER BY cnt DESC
        LIMIT 5
    ''')
    top_reasons = cursor.fetchall()

    return top_users, top_reasons


def get_chat_stats(chat_id, limit=15):
    """Статистика одного чата.

    Возвращает (title, total, mutes, bans, top_users, top_reasons).
    top_users — строки (user_id, name, mutes, bans, total).
    """
    cursor = get_conn().cursor()

    cursor.execute('''
        SELECT
            (SELECT chat_title FROM actions a2 WHERE a2.chat_id = a.chat_id ORDER BY a2.id DESC LIMIT 1) as title,
            COUNT(*) as total,
            SUM(CASE WHEN action_type = 'mute' THEN 1 ELSE 0 END) as mutes,
            SUM(CASE WHEN action_type = 'ban' THEN 1 ELSE 0 END) as bans
        FROM actions a
        WHERE a.chat_id = ?
    ''', (chat_id,))
    title, total, mutes, bans = cursor.fetchone()
    mutes = mutes or 0
    bans = bans or 0

    cursor.execute('''
        SELECT
            user_id,
            COALESCE(victim_name, '@' || username, 'ID ' || user_id) as name,
            SUM(CASE WHEN action_type = 'mute' THEN 1 ELSE 0 END) as mutes,
            SUM(CASE WHEN action_type = 'ban' THEN 1 ELSE 0 END) as bans,
            COUNT(*) as total
        FROM actions
        WHERE chat_id = ?
        GROUP BY COALESCE(user_id, username, victim_name)
        ORDER BY total DESC
        LIMIT ?
    ''', (chat_id, limit))
    top_users = cursor.fetchall()

    cursor.execute('''
        SELECT reason, COUNT(*) as cnt
        FROM actions
        WHERE chat_id = ?
        GROUP BY reason
        ORDER BY cnt DESC
        LIMIT 5
    ''', (chat_id,))
    top_reasons = cursor.fetchall()

    return title, total, mutes, bans, top_users, top_reasons


def get_chats_summary():
    """Сводка по чатам: [(chat_id, title, total, mutes, bans), ...]."""
    cursor = get_conn().cursor()
    cursor.execute('''
        SELECT
            a.chat_id,
            (SELECT chat_title FROM actions a2 WHERE a2.chat_id = a.chat_id ORDER BY a2.id DESC LIMIT 1) as title,
            COUNT(*) as total,
            SUM(CASE WHEN action_type = 'mute' THEN 1 ELSE 0 END) as mutes,
            SUM(CASE WHEN action_type = 'ban' THEN 1 ELSE 0 END) as bans
        FROM actions a
        GROUP BY a.chat_id
        ORDER BY total DESC
    ''')
    return cursor.fetchall()
