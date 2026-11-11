"""Модуль достижений.

Вынесено из main.py без изменений.
"""

ACHIEVEMENTS = {
    'first_blood': {
        'title': '🩸 Первый удар режима',
        'desc': 'Получить первый мут или бан',
        'check': lambda mutes, bans: (mutes + bans) >= 1
    },
    'beginner_democrat': {
        'title': '🌱 Растущая угроза режиму',
        'desc': 'Получить 10 мутов',
        'check': lambda mutes, bans: mutes >= 10
    },
    'democracy_veteran': {
        'title': '🎖 Ветеран подполья',
        'desc': 'Получить 25 мутов',
        'check': lambda mutes, bans: mutes >= 25
    },
    'freedom_lover': {
        'title': '🗽 Голос свободы',
        'desc': 'Получить 50 мутов',
        'check': lambda mutes, bans: mutes >= 50
    },
    'tribune': {
        'title': '🏛 Трибун пощади',
        'desc': 'Получить 100 мутов',
        'check': lambda mutes, bans: mutes >= 100
    },
    'resistance_leader': {
        'title': '🏆 Лидер сопротивления',
        'desc': 'Получить 500 мутов',
        'check': lambda mutes, bans: mutes >= 500
    },
    'democracy_no_choice': {
        'title': '1️⃣9️⃣8️⃣4️⃣ Демократия Выборов нет',
        'desc': 'Получить 1984 мута',
        'check': lambda mutes, bans: mutes >= 1984
    },
    'servant_of_people': {
        'title': '🚪 Изгнанник режима',
        'desc': 'Получить 5 банов',
        'check': lambda mutes, bans: bans >= 5
    },
    'invincible_democrat': {
        'title': '🦾 Несгибаемый оппозиционер',
        'desc': 'Получить 10 банов',
        'check': lambda mutes, bans: bans >= 10
    }
}


def check_new_achievements(mutes, bans, action_type):
    """Определяет, какие достижения были разблокированы именно этим событием."""
    unlocked = []
    total = mutes + bans
    if total == 1:
        unlocked.append(ACHIEVEMENTS['first_blood'])

    if action_type == 'mute':
        if mutes == 10:
            unlocked.append(ACHIEVEMENTS['beginner_democrat'])
        elif mutes == 25:
            unlocked.append(ACHIEVEMENTS['democracy_veteran'])
        elif mutes == 50:
            unlocked.append(ACHIEVEMENTS['freedom_lover'])
        elif mutes == 100:
            unlocked.append(ACHIEVEMENTS['tribune'])
        elif mutes == 500:
            unlocked.append(ACHIEVEMENTS['resistance_leader'])
        elif mutes == 1984:
            unlocked.append(ACHIEVEMENTS['democracy_no_choice'])
    elif action_type == 'ban':
        if bans == 5:
            unlocked.append(ACHIEVEMENTS['servant_of_people'])
        elif bans == 10:
            unlocked.append(ACHIEVEMENTS['invincible_democrat'])

    return unlocked
