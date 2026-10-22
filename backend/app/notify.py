import asyncio
import html

import aiohttp

from .config import Settings
from .download.progress import Job, JobStatus
from .logging_conf import get_logger

logger = get_logger("notify")


def _size(value: int) -> str:
    gb = value / 1024**3
    return f"{gb:.1f} ГБ".replace(".", ",") if gb >= 1 else f"{value / 1024**2:.0f} МБ"


def finish_message(job: Job) -> str | None:
    title = html.escape(f"{job.name} ({job.year})" if job.year else job.name)
    if job.status == JobStatus.SUCCESS:
        details = f"{job.done_episodes} серий · " if job.is_series and job.total_episodes else ""
        size = _size(job.bytes_done) if job.bytes_done else ""
        return f"✅ <b>{title}</b> скачан\n{details}{size}".strip()
    if job.status == JobStatus.PARTIAL:
        return (
            f"⚠️ <b>{title}</b> скачан частично: {job.done_episodes} из {job.total_episodes} серий\n"
            f"{html.escape(job.error or '')}"
        ).strip()
    if job.status == JobStatus.ERROR:
        return f"❌ <b>{title}</b> не скачался\n{html.escape(job.error or 'Неизвестная ошибка')}"
    return None


class Notifier:
    """Sends the job owner a Telegram message when a download finishes."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tasks: set[asyncio.Task] = set()

    def job_finished(self, job: Job) -> None:
        if not (self._settings.notify and self._settings.bot_token and job.owner_id):
            return
        text = finish_message(job)
        if text:
            task = asyncio.create_task(self._send(job.owner_id, text))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _send(self, chat_id: int, text: str) -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_notification": False,
            "reply_markup": {
                "inline_keyboard": [[{"text": "Открыть загрузки", "web_app": {"url": self._settings.mini_app_url}}]]
            },
        }
        url = f"https://api.telegram.org/bot{self._settings.bot_token}/sendMessage"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
                async with http.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.warning("Telegram notify failed: %s %s", response.status, await response.text())
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Telegram notify failed: %s", exc)
