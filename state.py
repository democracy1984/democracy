"""Изменяемое состояние процесса (бывшие глобальные переменные main.py).

ВАЖНО: EAGLE_STICKER и PIGEON_STICKER переприсваиваются в main().
Обращаться к ним нужно через `import state` / `state.EAGLE_STICKER`,
а не через `from state import EAGLE_STICKER` — иначе получите старое значение.
"""

# id пользователей, которые отписались от рассылки в ЛС
PM_OPT_OUT: set = set()

# id пользователей, с которыми у аккаунта уже есть личный диалог (неважно, кто его начал)
PM_DIALOG_USER_IDS: set = set()

EAGLE_STICKER = None
PIGEON_STICKER = None
