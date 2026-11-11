from telethon.tl.types import MessageEntityMention, MessageEntityMentionName

from services.parsing import parse_moderation_message


class Message:
    def __init__(self, text, entities=None):
        self.message = text
        self.entities = entities or []


def mention_entity(text, needle, user_id):
    offset = text.index(needle)
    return MessageEntityMentionName(offset=offset, length=len(needle), user_id=user_id)


def mention(text, needle="@orgrobot"):
    offset = text.index(needle)
    return MessageEntityMention(offset=offset, length=len(needle))


def test_miss_rose_mute_with_entity():
    text = "Shhh... quiet now. Muted Mark for 1 hour. Reason: spam"
    parsed = parse_moderation_message(Message(text, [mention_entity(text, "Mark", 123)]))
    assert parsed == {
        "action_type": "mute",
        "user_id": 123,
        "username": None,
        "victim_name": "Mark",
        "duration": "1 hour",
        "reason": "spam",
    }


def test_miss_rose_ban():
    text = "Mark bites the dust! Reason: flood"
    parsed = parse_moderation_message(Message(text, [mention_entity(text, "Mark", 456)]))
    assert parsed["action_type"] == "ban"
    assert parsed["user_id"] == 456
    assert parsed["reason"] == "flood"


def test_thm_chatbot_ban():
    text = "Пользователь Иван (id 12345) был забанен. Причина: спам"
    parsed = parse_moderation_message(Message(text))
    assert parsed["action_type"] == "ban"
    assert parsed["user_id"] == 12345
    assert parsed["victim_name"] == "Иван"
    assert parsed["reason"] == "спам"


def test_iris_mute():
    text = "🔇 Maxim [1997673299] лишается права слова на 1 час"
    parsed = parse_moderation_message(Message(text))
    assert parsed["action_type"] == "mute"
    assert parsed["user_id"] == 1997673299
    assert parsed["duration"] == "1 час"
    assert parsed["victim_name"] == "Maxim"


def test_sentinel_prime_ban():
    text = "Пользователь @orgrobot не справился и был забанен."
    parsed = parse_moderation_message(Message(text, [mention(text, "@orgrobot")]))
    assert parsed["action_type"] == "ban"
    assert parsed["username"] == "orgrobot"
    assert parsed["victim_name"] == "@orgrobot"
    assert parsed["duration"] == "permanent"


def test_grouphelp_ban_with_username():
    text = "@bxjks67 [7973635085] bannato."
    parsed = parse_moderation_message(Message(text))
    assert parsed["action_type"] == "ban"
    assert parsed["user_id"] == 7973635085
    assert parsed["username"] == "bxjks67"
    assert parsed["victim_name"] == "@bxjks67"


def test_grouphelp_ban_without_username():
    text = "Mario Rossi [7973635085] bannato."
    parsed = parse_moderation_message(Message(text))
    assert parsed["action_type"] == "ban"
    assert parsed["user_id"] == 7973635085
    assert parsed["victim_name"] == "Mario Rossi"


def test_grouphelp_mute_with_duration_and_reason():
    text = "@bxjks67 [7973635085] mutato per 1 ora. Motivo: spam"
    parsed = parse_moderation_message(Message(text))
    assert parsed["action_type"] == "mute"
    assert parsed["duration"] == "1 ora"
    assert parsed["reason"] == "spam"


def test_grouphelp_silenced():
    text = "@bxjks67 [7973635085] silenziato per 30 minuti. Causa: flood"
    parsed = parse_moderation_message(Message(text))
    assert parsed["action_type"] == "mute"
    assert parsed["duration"] == "30 minuti"
    assert parsed["reason"] == "flood"


def test_negations_are_ignored():
    texts = [
        "@user [7973635085] sbannato.",
        "@user [7973635085] smutato.",
        "@user [7973635085] non bannato.",
        "@user [7973635085] non è stato bannato.",
        "User was not banned.",
        "User has not been muted.",
        "Пользователь не был забанен.",
        "Пользователь @x не забанен.",
    ]
    for text in texts:
        assert parse_moderation_message(Message(text)) is None, text


def test_info_messages_are_ignored():
    texts = [
        "This bot stops automatic spammers. How it works? Privacy policy.",
        "Hey, I am OrgRobot! I help to moderate new chatroom members. Documentation: tgdev.io",
        "You CAN control bot. Bot permissions: delete messages: OK",
        "@Pewpewus, добро пожаловать! Не забудьте ознакомиться с правилами.",
    ]
    for text in texts:
        assert parse_moderation_message(Message(text)) is None, text
