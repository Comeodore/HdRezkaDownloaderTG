import asyncio
import logging
import os

from dotenv import load_dotenv
from heartbeat import heartbeat_task
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("rezka.bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://rezka.comeodore.services")
# Bump on releases: a new URL makes the Telegram WebView drop its cached index.html.
APP_VERSION = os.getenv("APP_VERSION", "3")
ALLOWED_IDS = {int(part) for part in os.getenv("ALLOWED_TELEGRAM_IDS", "").replace(";", ",").split(",")
               if part.strip().lstrip("-").isdigit()}


def app_url() -> str:
    return f"{MINI_APP_URL}{'&' if '?' in MINI_APP_URL else '?'}v={APP_VERSION}"


def app_button(text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, web_app=WebAppInfo(url=app_url()))]])


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if ALLOWED_IDS and (user is None or user.id not in ALLOWED_IDS):
        await update.message.reply_text("Это личный бот — доступ закрыт.")
        logger.info("Rejected /start from %s", user.id if user else "?")
        return
    await update.message.reply_text(
        "Ищите фильмы и сериалы на HDRezka и качайте их прямо на домашний сервер.\n"
        "Когда загрузка закончится, я пришлю сообщение.",
        reply_markup=app_button("🎬 Открыть Rezka"),
    )


async def on_error(_update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning("Transient network error: %s", context.error)
        return
    logger.error("Unhandled error: %s", context.error, exc_info=context.error)


async def post_init(app: Application) -> None:
    await app.bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Rezka", web_app=WebAppInfo(url=app_url())))
    await app.bot.set_my_commands([BotCommand("start", "Открыть приложение")])
    logger.info("Menu button set to %s", app_url())
    if os.environ.get("HEARTBEAT_URL"):
        app.bot_data["heartbeat"] = asyncio.create_task(heartbeat_task(service_id="rezka-bot"))


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
