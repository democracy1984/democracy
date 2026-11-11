"""Точка входа юзербота.

Клиент создаётся в core/client.py, состояние — в core/state.py,
список мониторируемых ботов — в core/bots.py, хендлеры регистрируются
при импорте пакета handlers. Логика запуска не менялась по сравнению
с прежним монолитным main.py.
"""

import asyncio
import os

from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputStickerSetShortName

from core import state
from services.backgrounds import ffmpeg_status
from core.bots import MODS_TO_RESOLVE, bots_label
from core.client import client
from config import ALLOWED_MODS, STICKER_PACK_NAME
from core.database import check_db_empty, init_db, load_pm_intro_sent, load_pm_opt_out
from core.helpers import get_time_str
from services.matrix_bg import ensure_matrix_bg
from services.scraping import auto_scrape_history

# Импорт хендлеров регистрирует их на клиенте.
# Порядок сохранён таким же, как был в прежнем main.py.
from handlers import chat_actions  # noqa: F401
from handlers import moderation  # noqa: F401
from handlers import commands  # noqa: F401
from handlers import custom_bg  # noqa: F401
from handlers import pm_dialogs  # noqa: F401
from handlers import reactions  # noqa: F401


async def main():
    print("[*] Запуск клиента Telegram...")
    await client.start()

    # Файл сессии содержит полный доступ к аккаунту — закрываем его от других
    try:
        os.chmod(client.session.filename, 0o600)
    except OSError:
        pass

    print(f"[*] {ffmpeg_status()}")

    # Инициализируем БД структуру
    init_db()

    # Загружаем opt-out список из БД
    state.PM_OPT_OUT.update(load_pm_opt_out())
    print(f"[*] Загружено {len(state.PM_OPT_OUT)} opt-out записей из БД")

    # Загружаем тех, кому уже отправляли первое ЛС (приписка не повторяется)
    state.PM_INTRO_SENT.update(load_pm_intro_sent())
    print(f"[*] Загружено {len(state.PM_INTRO_SENT)} записей о первом ЛС")

    # Фоновая гифка для Matrix (скачивается один раз)
    await asyncio.to_thread(ensure_matrix_bg)

    # Динамически резолвим ID ботов из core/bots.py (например, MissRose),
    # у которых в конфиге задан только username
    for bot in MODS_TO_RESOLVE:
        try:
            entity = await client.get_entity(bot['bot_username'])
            if entity.id not in ALLOWED_MODS:
                ALLOWED_MODS.append(entity.id)
                print(f"[+] ID {bot['bot_name']} ({bot['bot_username']}) добавлен: {entity.id}")
        except Exception as e:
            print(f"[-] Не удалось получить ID {bot['bot_name']} ({bot['bot_username']}): {e}")

    # Кэширование птиц из стикерпака
    try:
        pack = await client(GetStickerSetRequest(
            stickerset=InputStickerSetShortName(short_name=STICKER_PACK_NAME),
            hash=0
        ))
        for doc in pack.documents:
            for attr in doc.attributes:
                if hasattr(attr, 'alt'):
                    clean_alt = attr.alt.replace('\ufe0f', '').strip()
                    if "🦅" in clean_alt and not state.EAGLE_STICKER:
                        state.EAGLE_STICKER = doc
                    if "🕊" in clean_alt and not state.PIGEON_STICKER:
                        state.PIGEON_STICKER = doc
        if state.EAGLE_STICKER: print(f"[+] {get_time_str()} Стикер орла 🦅 загружен.")
        if state.PIGEON_STICKER: print(f"[+] {get_time_str()} Стикер голубя 🕊 загружен.")
    except Exception as e:
        print(f"[-] Ошибка при инициализации стикерпака: {e}")

    # УМНАЯ ПРОВЕРКА БАЗЫ ДАННЫХ ПРИ СТАРТЕ
    if check_db_empty():
        # Если логов нет — запускаем внутренний глубокий скрапер перед включением онлайна
        await auto_scrape_history()
    else:
        print("[*] База данных уже содержит логи. Пропуск исторического скрапинга.")

    print(f"[*] Юзербот запущен и ведет скрытый мультиязычный мониторинг {bots_label()} в реальном времени!")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
