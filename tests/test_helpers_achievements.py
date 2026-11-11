import re

from core import helpers
from services.achievements import ACHIEVEMENTS, check_new_achievements


def test_cooldown(monkeypatch):
    times = iter([100.0, 100.0, 111.0])
    monkeypatch.setattr(helpers.time, "time", lambda: next(times))

    assert helpers.check_and_update_cooldown("user", 10) is False
    assert helpers.check_and_update_cooldown("user", 10) is True
    assert helpers.check_and_update_cooldown("user", 10) is False


def test_cooldown_empty_key():
    assert helpers.check_and_update_cooldown(None) is False


def test_time_str_format():
    assert re.fullmatch(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]", helpers.get_time_str())


def test_achievement_first_blood():
    unlocked = check_new_achievements(1, 0, "mute")
    assert [item["title"] for item in unlocked] == [ACHIEVEMENTS["first_blood"]["title"]]
    assert check_new_achievements(1, 0, "ban")[0]["title"] == ACHIEVEMENTS["first_blood"]["title"]


def test_achievement_mute_thresholds():
    cases = {
        10: "beginner_democrat",
        25: "democracy_veteran",
        50: "freedom_lover",
        100: "tribune",
        500: "resistance_leader",
        1984: "democracy_no_choice",
    }
    for mutes, key in cases.items():
        unlocked = check_new_achievements(mutes, 0, "mute")
        assert [item["title"] for item in unlocked] == [ACHIEVEMENTS[key]["title"]], mutes


def test_achievement_ban_thresholds():
    assert [item["title"] for item in check_new_achievements(0, 5, "ban")] == [
        ACHIEVEMENTS["servant_of_people"]["title"]
    ]
    assert [item["title"] for item in check_new_achievements(0, 10, "ban")] == [
        ACHIEVEMENTS["invincible_democrat"]["title"]
    ]


def test_achievement_not_on_arbitrary_values():
    assert check_new_achievements(0, 0, "mute") == []
    assert check_new_achievements(11, 0, "mute") == []
    assert check_new_achievements(0, 6, "ban") == []
