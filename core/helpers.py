"""Мелкие общие хелперы: время и кулдаун пользователей."""

import time
from datetime import datetime

from config import USER_COOLDOWN_SECONDS

user_last_action_time = {}


def check_and_update_cooldown(user_key, cooldown=USER_COOLDOWN_SECONDS):
    """
    Проверяет, находится ли пользователь на кулдауне.
    Возвращает True, если с последнего действия пользователя прошло меньше `cooldown` секунд (нужно пропустить).
    Возвращает False, если кулдаун истек или действия еще не было (можно обрабатывать).
    """
    if not user_key:
        return False

    now = time.time()

    if len(user_last_action_time) > 1000:
        expired_keys = [k for k, t in user_last_action_time.items() if now - t > cooldown]
        for k in expired_keys:
            del user_last_action_time[k]

    last_time = user_last_action_time.get(user_key, 0)
    if now - last_time < cooldown:
        return True

    user_last_action_time[user_key] = now
    return False


def get_time_str():
    """Возвращает текущую метку времени в формате [ГГГГ-ММ-ДД ЧЧ:ММ:СС]."""
    return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"
