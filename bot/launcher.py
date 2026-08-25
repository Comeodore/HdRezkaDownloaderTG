import asyncio
import logging
import os

from dotenv import load_dotenv
from heartbeat import heartbeat_task
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("rezka.bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://rezka.comeodore.services")

# Cache-buster for Cloudflare/Telegram WebView: bump on each release so the
# mini app URL changes and clients re-fetch a fresh index.html.
APP_VERSION = os.getenv("APP_VERSION", "2")


def app_url() -> str:
    separator = "&" if "?" in MINI_APP_URL else "?"
    return f"{MINI_APP_URL}{separator}v={APP_VERSION}"


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🎬 Открыть Rezka", web_app=WebAppInfo(url=app_url()))]]
    )
    await update.message.reply_text(
        "Поиск и загрузка фильмов и сериалов — в приложении:",
        reply_markup=keyboard,
    )


async def on_error(_update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning("Transient network error: %s", error)
        return
    logger.error("Unhandled error: %s", error)


async def post_init(app: Application) -> None:
    await app.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Rezka", web_app=WebAppInfo(url=app_url()))
    )
    logger.info("Menu button set to %s", app_url())
    if os.environ.get("HEARTBEAT_URL"):
        asyncio.create_task(heartbeat_task(service_id="rezka-bot"))


def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_error_handler(on_error)
    logger.info("Rezka launcher bot started")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
