"""Хендлер команд: /stats, /top, /progress, /help, /chats, /stopspamming.

Вынесено из main.py без изменений логики.
"""

import html
from collections import defaultdict

from telethon import events

import state
from achievements import ACHIEVEMENTS
from client import client
from config import MATRIX_BG_PATH, USER_COOLDOWN_SECONDS
from database import (
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


@client.on(events.NewMessage)
async def handle_commands(event):
    """Обработка команд /stats, /top, /progress и /help."""
    if not event.text:
        return

    command_text = event.text.strip().lower()

    if event.is_private:
        if not (command_text.startswith('/stats') or
                command_text.startswith('/top') or
                command_text.startswith('/progress') or
                command_text.startswith('/help') or
                command_text.startswith('/chats') or
                command_text.startswith('/stopspamming')):
            return
    else:
        if not (command_text.startswith('/stats') or command_text.startswith('/top')):
            return

    sender = await event.get_sender()
    if not sender:
        return

    user_key = f"id_{sender.id}"
    if not event.is_private and check_and_update_cooldown(user_key):
        print(f"[*] Пропуск команды от пользователя {user_key} (кулдаун {USER_COOLDOWN_SECONDS} сек)")
        return

    # --- КОМАНДА /top ---
    if command_text.startswith('/top'):
        top_users, top_reasons = get_global_top()

        # Показываем актуальные имена из Telegram, а не сохранённые при наказании,
        # и заодно обновляем ими записи в БД
        fresh = await resolve_current_names([row[0] for row in top_users])
        for entity in fresh.values():
            sync_target_identity(entity)
        top_users = [
            (build_display_name(fresh[row[0]]) if row[0] in fresh else row[1],) + tuple(row[2:])
            for row in top_users
        ]

        users_list = ""
        for idx, (name, mutes, bans, total) in enumerate(top_users, 1):
            users_list += f"{idx}. <b>{html.escape(name)}</b> — Всего: <code>{total}</code> (🔇 {mutes} | 🚫 {bans})<br>"
        if not users_list:
            users_list = "• Нет данных о нарушителях"

        reasons_list = ""
        for idx, (reason, cnt) in enumerate(top_reasons, 1):
            reasons_list += f"{idx}. <i>{html.escape(reason)}</i> — <code>{cnt}</code> раз(а)<br>"
        if not reasons_list:
            reasons_list = "• Нет данных о причинах"

        if event.is_private:
            response = (
                f"<b>🏆 ТОП-15 нарушителей за всё время:</b>\n"
                f"<blockquote expandable>{users_list.replace('<br>', '\n').strip()}</blockquote>\n\n"
                f"<b>📋 ТОП-5 причин наказаний:</b>\n"
                f"<blockquote>{reasons_list.replace('<br>', '\n').strip()}</blockquote>"
            )
            await event.reply(response, parse_mode='html')
        else:
            user_lines = [
                f"{idx}. {name} - Всего: {total} (муты: {mutes} | баны: {bans})"
                for idx, (name, mutes, bans, total) in enumerate(top_users, 1)
            ] or ['Нет данных о нарушителях']
            reason_lines = [
                f"{idx}. {reason} - {cnt} раз(а)"
                for idx, (reason, cnt) in enumerate(top_reasons, 1)
            ] or ['Нет данных о причинах']
            img_bio = render_telegram_bubble('ТОП Нарушителей', [
                ('ТОП-15 нарушителей за всё время', user_lines),
                ('ТОП-5 причин наказаний', reason_lines),
            ])
            await client.send_file(event.chat_id, img_bio, reply_to=event.id)
            print(f"[+] {get_time_str()} Отправлена картинка /top в публичный чат {event.chat_id}")

    # --- КОМАНДА /stats ---
    elif command_text.startswith('/stats'):
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
    elif command_text.startswith('/progress') and event.is_private:
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
    elif command_text.startswith('/help') and event.is_private:
        response = (
            f"<b>ℹ️ Доступные команды:</b>\n\n"
            f"📊 /stats — Посмотреть свою статистику нарушений\n"
            f"🏆 /top — ТОП-15 нарушителей и ТОП-5 причин наказаний\n"
            f"⭐ /progress — Ваши достижения\n"
            f"❓ /help — Список всех доступных команд\n"
            f"🗂 /chats — Список чатов, в которых состоит бот\n"
            f"🔕 /stopspamming — Больше не получать уведомления в ЛС\n"
        )
        await event.reply(response, parse_mode='html')

    # --- КОМАНДА /chats (СПИСОК ЧАТОВ - ТОЛЬКО В ЛС) ---
    elif command_text.startswith('/chats') and event.is_private:
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
    elif command_text.startswith('/stopspamming') and event.is_private:
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
