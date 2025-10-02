import os
import asyncio
from aiogram import Bot, Dispatcher

from dotenv import load_dotenv
from handlers import router
from db import init_db

async def main():
    load_dotenv()
    bot = Bot(token=os.getenv('TG_TOKEN', ''))
    dp = Dispatcher()
    dp.startup.register(startup)
    dp.shutdown.register(shutdown)
    dp.include_router(router)
    await dp.start_polling(bot)

async def startup(dispatcher: Dispatcher):
    await init_db()
    print('Starting...')


async def shutdown(dispatcher: Dispatcher):
    print('Shutting...')

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')