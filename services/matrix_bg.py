"""Фоновая гифка Matrix: определение пользователя и разовое скачивание."""

import os
import urllib.request

from config import MATRIX_BG_PATH, MATRIX_BG_URL, MATRIX_USER_ID, MATRIX_USERNAME
from core.helpers import get_time_str


def is_matrix_user(sender):
    """Matrix определяется по стабильному ID, username — запасной вариант.

    Имя/фамилия не используются: их можно поставить любыми и обойти проверку.
    """
    if getattr(sender, 'id', None) == MATRIX_USER_ID:
        return True
    username = (getattr(sender, 'username', '') or '').lower()
    return username == MATRIX_USERNAME.lower()


def ensure_matrix_bg():
    """Скачивает фоновую гифку для Matrix при старте (один раз, кэш в файл)."""
    if os.path.exists(MATRIX_BG_PATH):
        return
    try:
        urllib.request.urlretrieve(MATRIX_BG_URL, MATRIX_BG_PATH)
        print(f"[+] {get_time_str()} Фоновая гифка Matrix скачана ({os.path.getsize(MATRIX_BG_PATH)} байт)")
    except Exception as e:
        print(f"[-] Ошибка скачивания фоновой гифки Matrix: {e}")
