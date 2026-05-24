import asyncio
import config
from telethon import TelegramClient

async def auth():
    async with TelegramClient(config.TELEGRAM_SESSION,
                               config.TELEGRAM_API_ID,
                               config.TELEGRAM_API_HASH) as c:
        me = await c.get_me()
        print(f"Authorised as @{me.username} ({me.first_name})")

asyncio.run(auth())
