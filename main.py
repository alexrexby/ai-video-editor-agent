import asyncio
import logging
import sys
import socket
from urllib.parse import urlparse
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.client.telegram import TelegramAPIServer
from tg_bot.config import BOT_TOKEN, LOCAL_BOT_API_URL, USE_LOCAL_BOT_API
from tg_bot.handlers.router import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

def is_local_api_available(url: str) -> bool:
    """Checks if the local Telegram Bot API server port is responding."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except Exception:
        return False

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.error("BOT_TOKEN не задан! Проверьте tg_bot/config.py или .env")
        return

    # Check if local Bot API server is available (lifts file limit to 2000 MB)
    if USE_LOCAL_BOT_API and is_local_api_available(LOCAL_BOT_API_URL):
        logger.info(f"⚡️ Подключение к локальному Telegram Bot API: {LOCAL_BOT_API_URL} (лимит 2 ГБ)")
        api_server = TelegramAPIServer.from_base(LOCAL_BOT_API_URL, is_local=True)
        session = AiohttpSession(api=api_server, timeout=600.0)
    else:
        logger.info("🌐 Подключение к облачному Telegram Bot API (api.telegram.org, лимит 20 МБ)")
        session = AiohttpSession(timeout=180.0)

    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("🚀 Бот команды Амалии запущен и готов к приему сообщений!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
