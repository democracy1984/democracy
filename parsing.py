"""Разбор сообщений ботов-модераторов (список ботов — в bots.py).

Единственная реализация парсера в проекте (копия из scraper.py удалена).
"""

import re

from telethon.tl.types import MessageEntityMentionName, MessageEntityMention


def parse_moderation_message(message):
    """Глубокий и гибкий разбор сообщений от Роуз и THM Chatbot на любых языках."""
    text = message.message or ""
    text_lower = text.lower().replace('ё', 'е')
    action_type = None
    duration = "permanent"
    reason = "Не указана"

    # Негации и служебные ответы ботов («не забанен», «право слова вернули») — не наказания
    if any(w in text_lower for w in ["не забанен", "не заблокирован", "не заглушен", "вернули право слова", "снят бан"]):
        return None

    # Информационные сообщения ботов (описания, инструкции) — не наказания
    if any(w in text_lower for w in [
        "how it works?", "privacy policy", "you add this bot", "this bot stops",
        "bot permissions:", "i help to moderate", "you can control bot",
        "you can not control bot", "you cannot control bot", "documentation:",
    ]):
        return None

    if any(w in text_lower for w in ["shhh", "quiet now", "помолчи", "заглушен", "мутирован", "тссс", "лишается права слова"]):
        action_type = "mute"
    elif any(w in text_lower for w in ["bites the dust", "укусил пыль", "забанен", "banned", "заблокирован"]):
        action_type = "ban"
    else:
        return None

    reason_match = re.search(r'(?:Reason|Причина):\s*(.*)', text, re.DOTALL | re.IGNORECASE)
    if reason_match:
        reason = reason_match.group(1).strip().strip('"')

    victim_id = None
    victim_username = None
    victim_name = None

    thm_match = re.search(r'Пользователь\s+(.*?)\s+\(id\s+(\d+)\)', text, re.IGNORECASE)
    if thm_match:
        victim_name = thm_match.group(1).strip()
        try:
            victim_id = int(thm_match.group(2))
        except ValueError:
            pass
    else:
        if message.entities:
            for entity in message.entities:
                entity_text = text[entity.offset:entity.offset+entity.length]
                if isinstance(entity, MessageEntityMentionName):
                    victim_id = entity.user_id
                    victim_name = entity_text
                    break
                elif hasattr(entity, 'url') and entity.url and 'tg://user?id=' in entity.url:
                    try:
                        victim_id = int(entity.url.split('id=')[-1])
                        victim_name = entity_text
                    except ValueError:
                        pass
                    break
                elif isinstance(entity, MessageEntityMention):
                    victim_username = entity_text.replace('@', '').strip()
                    victim_name = entity_text
                    break

    if not victim_name:
        lines = text.split('\n')
        if len(lines) > 1:
            for line in lines:
                line_clean = line.lower().replace('ё', 'е')
                if any(w in line_clean for w in ["заглушен", "мутирован", "забанен", "muted", "banned"]):
                    victim_name = line.split()[0].strip()
                    break

    if not victim_name or not victim_name.strip('\u200b\u200c\u200d \ufe0f'):
        if victim_id:
            victim_name = f"ID {victim_id}"
        else:
            victim_name = "Неизвестный"

    if action_type == "mute":
        match_dur = re.search(r'(?:for|на)\s+(.*?)(?:\s+Причина|\s+Reason|,|\.|\n|$)', text, re.IGNORECASE)
        if match_dur:
            duration = match_dur.group(1).strip()
        else:
            duration = "indefinitely"

    return {
        'action_type': action_type,
        'user_id': victim_id,
        'username': victim_username,
        'victim_name': victim_name,
        'duration': duration,
        'reason': reason
    }
