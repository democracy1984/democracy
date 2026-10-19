"""Хендлер команд: /stats, /top, /globaltop, /progress, /help, /chats, /stopspamming.

/top в чате показывает топ этого чата, в ЛС — список чатов аккаунта,
/top <название|ID> — статистика конкретного чата, /globaltop — общий топ.
"""

import html
from collections import defaultdict

from telethon import events

import state
from achievements import ACHIEVEMENTS
from client import client
from config import MATRIX_BG_PATH, USER_COOLDOWN_SECONDS
from database import (
    get_chat_stats,
    get_chats_summary,
    get_global_top,
    get_user_stats,
    remove_pm_opt_out,
    save_pm_opt_out,
)
from helpers import check_and_update_cooldown, get_time_str
from identity import build_display_name, sync_target_identity
from matrix_bg import is_matrix_user
from rendering import render_telegram_bubble


async def resolve_current_names(user_ids):
    """Свежие сущности пользователей из Telegram: {user_id: entity}.

    Ошибка резолва отдельного ID (нет в кэше сессии, удалённый аккаунт,
    FloodWait) не роняет команду — для него останется сохранённое имя.
    """
    entities = {}
    for uid in {uid for uid in user_ids if uid}:
        try:
            entities[uid] = await client.get_entity(uid)
        except Exception:
            continue
    return entities


async def refresh_top_names(top_users):
    """Подставляет актуальные имена из Telegram и синхронизирует их в БД."""
    fresh = await resolve_current_names([row[0] for row in top_users])
    for entity in fresh.values():
        sync_target_identity(entity)
    return [
        (row[0], build_display_name(fresh[row[0]]) if row[0] in fresh else row[1]) + tuple(row[2:])
        for row in top_users
    ]


async def get_account_chats():
    """Группы и каналы аккаунта: [{'id', 'title', 'username'}]."""
    chats = []
    try:
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                chats.append({
                    'id': dialog.id,
                    'title': dialog.name or '—',
                    'username': getattr(dialog.entity, 'username', None),
                })
    except Exception as e:
        print(f"[-] Не удалось получить список чатов аккаунта: {e}")
    return chats


def merge_chat_stats(chats, summary):
    """Добавляет к чатам аккаунта счётчики из БД и добирает чаты, которых нет в диалогах."""
    stats = {row[0]: row for row in summary}
    merged = []
    for chat in chats:
        row = stats.pop(chat['id'], None)
        merged.append({
            'id': chat['id'],
            'title': chat['title'] or (row[1] if row else '—'),
            'username': chat.get('username'),
            'total': row[2] if row else 0,
            'mutes': row[3] if row else 0,
            'bans': row[4] if row else 0,
        })
    for chat_id, title, total, mutes, bans in stats.values():
        merged.append({
            'id': chat_id,
            'title': title or '—',
            'username': None,
            'total': total,
            'mutes': mutes,
            'bans': bans,
        })
    merged.sort(key=lambda chat: chat['total'], reverse=True)
    return merged


def match_chat(chats, query):
    """Поиск чата по ID, названию или @username."""
    query = query.strip()
    if not query:
        return []

    try:
        value = int(query)
    except ValueError:
        value = None
    if value is not None:
        candidates = {value}
        if value > 0:
            candidates.add(-(1000000000000 + value))
            candidates.add(-value)
        by_id = [chat for chat in chats if chat['id'] in candidates]
        if by_id:
            return by_id

    needle = query.casefold().lstrip('@')
    return [
        chat for chat in chats
        if needle in (chat['title'] or '').casefold()
        or (chat.get('username') and needle == chat['username'].casefold())
    ]


def format_top_user_lines(top_users):
    """Строки топа нарушителей для текста и картинки."""
    return [
        f"{idx}. {name} — Всего: {total} (🔇 {mutes} | 🚫 {bans})"
        for idx, (_, name, mutes, bans, total) in enumerate(top_users, 1)
    ] or ["Нет данных о нарушителях"]


def format_reason_lines(top_reasons):
    """Строки топа причин для текста и картинки."""
    return [
        f"{idx}. {reason} — {cnt} раз(а)"
        for idx, (reason, cnt) in enumerate(top_reasons, 1)
    ] or ["Нет данных о причинах"]


async def send_global_top(event):
    """Глобальный топ по всем чатам (бывшее поведение /top)."""
    top_users, top_reasons = get_global_top()
    top_users = await refresh_top_names(top_users)

    if event.is_private:
        users_lines = [
            f"{idx}. <b>{html.escape(name)}</b> — Всего: <code>{total}</code> (🔇 {mutes} | 🚫 {bans})"
            for idx, (_, name, mutes, bans, total) in enumerate(top_users, 1)
        ] or ["• Нет данных о нарушителях"]
        reasons_lines = [
            f"{idx}. <i>{html.escape(reason)}</i> — <code>{cnt}</code> раз(а)"
            for idx, (reason, cnt) in enumerate(top_reasons, 1)
        ] or ["• Нет данных о причинах"]
        response = (
            f"<b>🌍 ГЛОБАЛЬНЫЙ ТОП-15 нарушителей:</b>\n"
            f"<blockquote expandable>{chr(10).join(users_lines)}</blockquote>\n\n"
            f"<b>📋 ТОП-5 причин наказаний:</b>\n"
            f"<blockquote>{chr(10).join(reasons_lines)}</blockquote>"
        )
        await event.reply(response, parse_mode='html')
    else:
        img_bio = render_telegram_bubble('Глобальный ТОП', [
            ('ТОП-15 нарушителей за всё время', format_top_user_lines(top_users)),
            ('ТОП-5 причин наказаний', format_reason_lines(top_reasons)),
        ])
        await client.send_file(event.chat_id, img_bio, reply_to=event.id)
        print(f"[+] {get_time_str()} Отправлена картинка /globaltop в чат {event.chat_id}")


async def send_chat_top(event, chat_id, fallback_title=None):
    """Топ одного чата."""
    title, total, mutes, bans, top_users, top_reasons = get_chat_stats(chat_id)
    title = fallback_title or title or f"Чат {chat_id}"
    top_users = await refresh_top_names(top_users)

    if event.is_private:
        users_lines = [
            f"{idx}. <b>{html.escape(name)}</b> — Всего: <code>{total}</code> (🔇 {mutes} | 🚫 {bans})"
            for idx, (_, name, mutes, bans, total) in enumerate(top_users, 1)
        ] or ["• Нет данных о нарушителях"]
        reasons_lines = [
            f"{idx}. <i>{html.escape(reason)}</i> — <code>{cnt}</code> раз(а)"
            for idx, (reason, cnt) in enumerate(top_reasons, 1)
        ] or ["• Нет данных о причинах"]
        response = (
            f"<b>🗂 {html.escape(title)}</b>\n"
            f"🆔 <code>{chat_id}</code>\n\n"
            f"Всего наказаний: <code>{total}</code>\n"
            f"🔇 Мутов: <code>{mutes}</code> | 🚫 Банов: <code>{bans}</code>\n\n"
            f"<b>🏆 ТОП-15 нарушителей:</b>\n"
            f"<blockquote expandable>{chr(10).join(users_lines)}</blockquote>\n\n"
            f"<b>📋 ТОП-5 причин:</b>\n"
            f"<blockquote>{chr(10).join(reasons_lines)}</blockquote>"
        )
        await event.reply(response, parse_mode='html')
    else:
        img_bio = render_telegram_bubble('ТОП чата', [
            ('Чат', [title, f'ID {chat_id}']),
            ('Статистика', [f'Всего: {total}', f'Мутов: {mutes}', f'Банов: {bans}']),
            ('ТОП-15 нарушителей', format_top_user_lines(top_users)),
            ('ТОП-5 причин', format_reason_lines(top_reasons)),
        ])
        await client.send_file(event.chat_id, img_bio, reply_to=event.id)
        print(f"[+] {get_time_str()} Отправлена картинка /top по чату {chat_id} в чат {event.chat_id}")


async def send_chat_list(event):
    """Список всех чатов аккаунта с накопленной статистикой (для ЛС)."""
    chats = merge_chat_stats(await get_account_chats(), get_chats_summary())
    if not chats:
        await event.reply("<i>Аккаунт не состоит ни в одном чате.</i>", parse_mode='html')
        return

    lines = [
        f"{idx}. <b>{html.escape(chat['title'])}</b> — Всего: <code>{chat['total']}</code> "
        f"(🔇 {chat['mutes']} | 🚫 {chat['bans']})"
        for idx, chat in enumerate(chats[:50], 1)
    ]
    await event.reply(
        f"<b>🗂 Чаты аккаунта — топ по наказаниям:</b>\n\n"
        f"<blockquote expandable>{chr(10).join(lines)}</blockquote>\n\n"
        f"💡 Детали: <code>/top название</code> или <code>/top ID</code>",
        parse_mode='html',
    )


async def send_chat_by_query(event, query):
    """Детали чата по названию или ID."""
    chats = merge_chat_stats(await get_account_chats(), get_chats_summary())
    matches = match_chat(chats, query)

    if not matches:
        await event.reply(f"❌ Чат «{html.escape(query)}» не найден.", parse_mode='html')
        return

    if len(matches) > 1:
        lines = [
            f"• <b>{html.escape(chat['title'])}</b> — <code>{chat['id']}</code>"
            for chat in matches[:10]
        ]
        await event.reply(
            "🔎 Найдено несколько чатов, уточни название или ID:\n\n" + "\n".join(lines),
            parse_mode='html',
        )
        return

    chat = matches[0]
    await send_chat_top(event, chat['id'], fallback_title=chat['title'])


@client.on(events.NewMessage)
async def handle_commands(event):
    """Обработка команд /stats, /top, /globaltop, /progress и /help."""
    if not event.text:
        return

    raw_text = event.text.strip()
    parts = raw_text.split(maxsplit=1)
    command = parts[0].split('@', 1)[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ''

    if event.is_private:
        if command not in ('/stats', '/top', '/globaltop', '/progress', '/help', '/chats', '/stopspamming'):
            return
    else:
        if command not in ('/stats', '/top', '/globaltop'):
            return

    sender = await event.get_sender()
    if not sender:
        return

    user_key = f"id_{sender.id}"
    if not event.is_private and check_and_update_cooldown(user_key):
        print(f"[*] Пропуск команды от пользователя {user_key} (кулдаун {USER_COOLDOWN_SECONDS} сек)")
        return

    # --- КОМАНДЫ /top и /globaltop ---
    if command == '/globaltop':
        await send_global_top(event)
    elif command == '/top':
        if arg:
            await send_chat_by_query(event, arg)
        elif event.is_private:
            await send_chat_list(event)
        else:
            await send_chat_top(
                event, event.chat_id,
                fallback_title=getattr(event.chat, 'title', None),
            )

    # --- КОМАНДА /stats ---
    elif command == '/stats':
        # Если /stats отправлен как ответ на чужое сообщение — статистика автора ответа
        target = sender
        if event.is_reply:
            try:
                reply = await event.get_reply_message()
                if reply is not None and getattr(reply, 'sender_id', None) and reply.sender_id != sender.id:
                    reply_sender = await reply.get_sender()
                    if reply_sender is not None and getattr(reply_sender, 'id', None):
                        target = reply_sender
            except Exception as e:
                print(f"[-] Не удалось получить автора сообщения для /stats: {e}")

        target_id = target.id
        target_username = getattr(target, 'username', None)

        # Актуальное имя из Telegram + синхронизация старых записей в БД
        display_name = build_display_name(target)
        sync_target_identity(target)

        mutes, bans, chats, reasons = get_user_stats(target_id, target_username)

        if event.is_private:
            display_name_esc = html.escape(display_name)

            if mutes == 0 and bans == 0:
                response = (
                    f"<b>📊 Статистика для {display_name_esc}:</b>\n\n"
                    f"<i>Нарушений в базе нет.</i>"
                )
            else:
                merged_chats = defaultdict(int)
                for chat_name, cnt in chats:
                    normalized_chat_name = (chat_name or "Неизвестный чат").strip()
                    merged_chats[normalized_chat_name] += cnt

                chats_list = ""
                for chat_name, cnt in sorted(merged_chats.items(), key=lambda item: item[1], reverse=True):
                    chats_list += f"• {html.escape(chat_name)}: <code>{cnt}</code> раз(а)\n"

                reasons_list = ""
                for reason, cnt in reasons:
                    reasons_list += f"• <i>{html.escape(reason)}</i>: <code>{cnt}</code> раз(а)\n"

                response = (
                    f"<b>📊 Статистика нарушений для {display_name_esc}</b>\n\n"
                    f"🔇 Мутов: <code>{mutes}</code>\n"
                    f"🚫 Банов: <code>{bans}</code>\n\n"
                    f"🏢 <b>Активность по чатам:</b>\n"
                    f"<blockquote>{chats_list.strip()}</blockquote>\n\n"
                    f"⚠️ <b>Основные причины:</b>\n"
                    f"<blockquote expandable>{reasons_list.strip()}</blockquote>"
                )
            await event.reply(response, parse_mode='html')
        else:
            if mutes == 0 and bans == 0:
                img_bio = render_telegram_bubble('Статистика', [
                    (f'Статистика для {display_name}', ['Нарушений в базе нет.']),
                ], strip_gif_path=MATRIX_BG_PATH if is_matrix_user(sender) else None,
                   strip_heading=f'Статистика для {display_name}')
            else:
                merged_chats = defaultdict(int)
                for chat_name, cnt in chats:
                    normalized_chat_name = (chat_name or "Неизвестный чат").strip()
                    merged_chats[normalized_chat_name] += cnt

                chat_lines = [
                    f'{chat_name}: {cnt} раз(а)'
                    for chat_name, cnt in sorted(merged_chats.items(), key=lambda item: item[1], reverse=True)
                ]
                reason_lines = [f'{reason}: {cnt} раз(а)' for reason, cnt in reasons]
                img_bio = render_telegram_bubble('Статистика', [
                    (f'Нарушения: {display_name}', [f'Мутов: {mutes}', f'Банов: {bans}']),
                    ('Активность по чатам', chat_lines),
                    ('Основные причины', reason_lines),
                ], strip_gif_path=MATRIX_BG_PATH if is_matrix_user(sender) else None,
                   strip_heading=f'Нарушения: {display_name}')
            await client.send_file(event.chat_id, img_bio, reply_to=event.id)
            print(f"[+] {get_time_str()} Отправлена картинка /stats в публичный чат {event.chat_id}")

    # --- КОМАНДА /progress (ДОСТИЖЕНИЯ - ТОЛЬКО В ЛС) ---
    elif command == '/progress' and event.is_private:
        target_id = sender.id
        target_username = getattr(sender, 'username', None)
        mutes, bans, _, _ = get_user_stats(target_id, target_username)

        ach_list = []
        for key, ach in ACHIEVEMENTS.items():
            unlocked = ach['check'](mutes, bans)
            status_icon = "🟢" if unlocked else "🔒"
            status_text = "<b>Разблокировано</b>" if unlocked else "<i>Заблокировано</i>"
            ach_list.append(f"{status_icon} {ach['title']}\n┗ {ach['desc']} — {status_text}")

        response = (
            f"<b>🏆 Ваша шкала достижений:</b>\n\n"
            + "\n\n".join(ach_list)
        )
        await event.reply(response, parse_mode='html')

    # --- КОМАНДА /help (ПОМОЩЬ - ТОЛЬКО В ЛС) ---
    elif command == '/help' and event.is_private:
        response = (
            f"<b>ℹ️ Доступные команды:</b>\n\n"
            f"📊 /stats — Посмотреть свою статистику нарушений\n"
            f"🏆 /top — В чате: топ этого чата. В ЛС: список чатов аккаунта\n"
            f"🔎 /top &lt;название|ID&gt; — Статистика конкретного чата\n"
            f"🌍 /globaltop — Общий топ-15 нарушителей по всем чатам\n"
            f"⭐ /progress — Ваши достижения\n"
            f"❓ /help — Список всех доступных команд\n"
            f"🗂 /chats — Список чатов, в которых состоит бот\n"
            f"🔕 /stopspamming — Больше не получать уведомления в ЛС\n"
        )
        await event.reply(response, parse_mode='html')

    # --- КОМАНДА /chats (СПИСОК ЧАТОВ - ТОЛЬКО В ЛС) ---
    elif command == '/chats' and event.is_private:
        chats_lines = []
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                title = getattr(dialog.entity, 'title', '—')
                chats_lines.append(f"• {html.escape(title)}")

        if chats_lines:
            response = f"<b>🗂 Чаты бота ({len(chats_lines)}):</b>\n\n" + "\n".join(chats_lines)
        else:
            response = "<i>Бот не состоит ни в одном чате.</i>"

        await event.reply(response, parse_mode='html')
    # --- КОМАНДА /stopspamming (ОТПИСКА ОТ ЛС - ТОЛЬКО В ЛС) ---
    elif command == '/stopspamming' and event.is_private:
        uid = sender.id

        if uid in state.PM_OPT_OUT:
            state.PM_OPT_OUT.discard(uid)
            remove_pm_opt_out(uid)
            await event.reply(
                "🔔 <b>Ладно, я продолжу вас уведомлять.</b>",
                parse_mode='html'
            )
            return

        state.PM_OPT_OUT.add(uid)
        save_pm_opt_out(uid)
        await event.reply(
            "🔕 <b>Готово!</b> Теперь я больше не буду писать вам в ЛС.\n",
            parse_mode='html'
        )
        print(f"[*] Пользователь {uid} отписался от ЛС через /stopspamming")
