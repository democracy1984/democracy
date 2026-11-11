import asyncio
import os
import sys

# Корень проекта в sys.path при запуске python tools/getchatid.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient

from config import API_ID, API_HASH, MAIN_SESSION_NAME, SESSION_DIR


async def main():
    # Используем ту же сессию 'my_account' из secrets/, чтобы не логиниться заново
    async with TelegramClient(os.path.join(SESSION_DIR, MAIN_SESSION_NAME), API_ID, API_HASH) as client:
        try:
            os.chmod(client.session.filename, 0o600)
        except OSError:
            pass
        print("Список ваших групп и каналов:")
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                print(f"[{dialog.id}] {dialog.name}")

if __name__ == "__main__":
    asyncio.run(main())
