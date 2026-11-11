"""Изменяемое состояние процесса (бывшие глобальные переменные main.py).

ВАЖНО: EAGLE_STICKER и PIGEON_STICKER переприсваиваются в main().
Обращаться к ним нужно через `from core import state` (или
`import core.state as state`) и `state.EAGLE_STICKER`, а не через
`from core.state import EAGLE_STICKER` — иначе получите старое значение.
"""

# id пользователей, которые отписались от рассылки в ЛС
PM_OPT_OUT: set = set()

# id пользователей, с которыми у аккаунта уже есть личный диалог (неважно, кто его начал)
PM_DIALOG_USER_IDS: set = set()

# id пользователей, которым уже отправляли первое сообщение в ЛС
# (используется, чтобы приписка про /stopspamming не повторялась)
PM_INTRO_SENT: set = set()

EAGLE_STICKER = None
PIGEON_STICKER = None
