from core.database import (
    format_display_name,
    get_chat_stats,
    get_chats_summary,
    get_chats_top,
    get_global_top,
    get_user_actions_total,
    get_user_chat_ids,
    get_user_stats,
)


A = -1001737370533
B = -1002338569737


def test_empty_and_save_action(db):
    assert db.check_db_empty() is True
    db.save_action(A, "Chat A", 1, None, "User One", "mute", "1 hour", "spam")
    assert db.check_db_empty() is False

    mutes, bans, chats, reasons = get_user_stats(1, None)
    assert (mutes, bans) == (1, 0)
    assert chats[0][0] == "Chat A"
    assert reasons[0] == ("spam", 1)


def test_stats_and_tops(db):
    db.save_batch_actions([
        (A, "Chat A", 1, None, "User One", "mute", "1h", "spam"),
        (A, "Chat A", 1, None, "User One", "mute", "1h", "spam"),
        (A, "Chat A", 2, None, "User Two", "ban", "permanent", "flood"),
        (B, "Chat B", 1, None, "User One", "ban", "permanent", "ads"),
    ])

    title, total, mutes, bans, top_users, top_reasons = get_chat_stats(A)
    assert (title, total, mutes, bans) == ("Chat A", 3, 2, 1)
    assert top_users[0][1] == "User One" and top_users[0][4] == 2

    summary = get_chats_summary()
    assert {row[0] for row in summary} == {A, B}

    top_users, top_reasons = get_global_top()
    assert top_users[0][1] == "User One"
    assert top_users[0][4] == 3

    only_a_users, only_a_reasons = get_chats_top([A])
    assert {row[1] for row in only_a_users} == {"User One", "User Two"}
    assert {reason for reason, _ in only_a_reasons} == {"spam", "flood"}


def test_user_chat_ids(db):
    db.save_batch_actions([
        (A, "Chat A", 10, None, "User", "mute", "1h", "x"),
        (B, "Chat B", 10, None, "User", "ban", "permanent", "x"),
        (B, "Chat B", 11, None, "Other", "mute", "1h", "x"),
    ])
    assert set(get_user_chat_ids(10)) == {A, B}
    assert get_user_chat_ids(99) == []


def test_sync_and_format_identity(db):
    db.save_batch_actions([
        (A, "Chat A", 42, None, "Old One", "mute", "1h", "x"),
        (B, "Chat B", 42, None, "Old Two", "ban", "permanent", "x"),
    ])
    assert db.sync_victim_identity(42, "New Name", "new_nick") == 2
    names = db.get_conn().execute(
        "SELECT DISTINCT victim_name, username FROM actions WHERE user_id=42"
    ).fetchall()
    assert names == [("New Name", "new_nick")]
    assert db.sync_victim_identity(42, "New Name", "new_nick") == 0

    assert format_display_name("Иван", "Петров", "ivan", 1) == "Иван Петров"
    assert format_display_name(None, None, "ivan", 1) == "@ivan"
    assert format_display_name(None, None, None, 7) == "ID 7"


def test_lookup_and_backfill(db):
    db.save_batch_actions([
        (A, "Chat A", None, None, "Unique", "mute", "1h", "x"),
        (A, "Chat A", 500, None, "Unique", "mute", "1h", "x"),
        (A, "Chat A", None, None, "Ambiguous", "mute", "1h", "x"),
        (A, "Chat A", 501, None, "Ambiguous", "mute", "1h", "x"),
        (A, "Chat A", 502, None, "Ambiguous", "mute", "1h", "x"),
    ])
    assert db.lookup_user_by_victim_name("Unique") == 500
    assert db.lookup_user_by_victim_name("Ambiguous") is None
    assert db.lookup_user_by_victim_name(".") is None

    assert db.backfill_victim_user_id("Unique", 500) == 1
    assert db.get_conn().execute(
        "SELECT COUNT(*) FROM actions WHERE victim_name='Unique' AND user_id IS NULL"
    ).fetchone()[0] == 0
    assert db.backfill_victim_user_id("Ambiguous", 501) == 0


def test_pm_tables(db):
    assert db.load_pm_opt_out() == set()
    db.save_pm_opt_out(7)
    assert db.load_pm_opt_out() == {7}
    db.remove_pm_opt_out(7)
    assert db.load_pm_opt_out() == set()

    assert db.load_pm_intro_sent() == set()
    db.save_pm_intro_sent(8)
    db.save_pm_intro_sent(8)
    assert db.load_pm_intro_sent() == {8}


def test_background_crud(db):
    assert db.get_user_background(1) is None
    db.set_user_background(1, "media/user_bg/1.gif")
    assert db.get_user_background(1) == "media/user_bg/1.gif"
    assert db.remove_user_background(1) == "media/user_bg/1.gif"
    assert db.get_user_background(1) is None
    assert db.remove_user_background(1) is None


def test_get_user_actions_total_is_id_only(db):
    db.save_action(A, "Chat A", None, "legacy", "Legacy", "mute", "1h", "x")
    db.save_action(A, "Chat A", 5, None, "User", "mute", "1h", "x")
    db.save_action(A, "Chat A", 5, None, "User", "ban", "permanent", "x")
    assert get_user_actions_total(5) == 2


def test_update_title_and_migration(db):
    db.save_action(1737370533, "Legacy Title", 1, None, "User", "mute", "1h", "x")
    db.migrate_legacy_chat_ids()
    row = db.get_conn().execute(
        "SELECT chat_id, chat_title FROM actions WHERE user_id=1"
    ).fetchone()
    assert row == (-1001737370533, "Legacy Title")

    db.update_chat_title(A, "Renamed")
    db.save_action(A, "Chat A", 2, None, "User", "mute", "1h", "x")
    db.update_chat_title(A, "Renamed Again")
    titles = db.get_conn().execute(
        "SELECT DISTINCT chat_title FROM actions WHERE chat_id=?", (A,)
    ).fetchall()
    assert titles == [("Renamed Again",)]
