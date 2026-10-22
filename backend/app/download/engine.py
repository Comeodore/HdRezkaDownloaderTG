import asyncio
import contextlib
import json
import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

import aiohttp

from ..config import Settings
from ..logging_conf import get_logger
from ..rezka.client import RezkaClient, RezkaError
from ..rezka.models import Stream, Subtitle, TitleDetails, Translator
from .paths import episode_path, movie_path, part_path, passport_path, series_dir, set_owner, subtitle_path
from .progress import Job, JobStatus, SpeedMeter
from .quality import Probed, pick_best, probe, total_size

logger = get_logger("engine")

Emit = Callable[[Job], None]
Refresh = Callable[[], Awaitable["Probed | None"]]
T = TypeVar("T")

_PASSPORT_RETRIES = 3
PREMIUM_ONLY = "HDRezka отдаёт только заставку — сейчас это доступно лишь премиум-аккаунтам"


class Interrupted(Exception):
    """The job was paused, cancelled or the app is shutting down."""


class JobFailed(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NoSpace(JobFailed):
    def __init__(self) -> None:
        super().__init__("Недостаточно места на диске")


class MirrorError(Exception):
    pass


class RangeIgnored(MirrorError):
    """The mirror answered a ranged request with the whole file."""


class Control:
    """Stop signal shared between the manager and a running job."""

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.mode: str | None = None  # "pause" | "cancel" | "shutdown"

    def stop(self, mode: str) -> None:
        self.mode = mode
        self.event.set()

    @property
    def stopped(self) -> bool:
        return self.event.is_set()

    def check(self) -> None:
        if self.event.is_set():
            raise Interrupted(self.mode)

    async def sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return
        raise Interrupted(self.mode)

    async def race(self, awaitable: Awaitable[T]) -> T:
        """Await ``awaitable`` but give up the moment the job is stopped.

        Network reads can stall for the whole read timeout; pause/cancel must
        not wait for that.
        """
        self.check()
        task = asyncio.ensure_future(awaitable)
        stop = asyncio.ensure_future(self.event.wait())
        try:
            await asyncio.wait({task, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
        if task.done():
            return task.result()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        raise Interrupted(self.mode)


class DownloadEngine:
    def __init__(self, settings: Settings, http: aiohttp.ClientSession, client: RezkaClient, emit: Emit) -> None:
        self._settings = settings
        self._http = http
        self._client = client
        self._emit = emit

    async def run(self, job: Job, control: Control) -> JobStatus:
        title = await self._client.title(job.url)
        translator = title.translator(job.translator_key)
        if translator is None:
            raise JobFailed("Эта озвучка больше недоступна на HDRezka")
        if title.is_series:
            return await self._series(job, title, translator, control)
        return await self._movie(job, title, translator, control)

    # ── movie ────────────────────────────────────────────────────────────────

    async def _movie(self, job: Job, title: TitleDetails, translator: Translator, control: Control) -> JobStatus:
        destination = movie_path(self._settings, title.name, title.year)
        job.target = destination.name
        job.current = title.name
        if destination.is_file() and destination.stat().st_size > 0:
            job.total = job.downloaded = job.bytes_done = destination.stat().st_size
            return JobStatus.SUCCESS

        stream, choice = await self._select(title, translator, job.max_height, destination, control)
        job.quality = choice.label
        self._ensure_space(choice.size, destination)

        async def refresh() -> Probed | None:
            return await self._same_encode(title, translator, choice.label)

        await self._fetch(choice, destination, job, control, refresh)
        job.bytes_done = destination.stat().st_size
        await self._subtitles(stream.subtitles, destination)
        return JobStatus.SUCCESS

    # ── series ───────────────────────────────────────────────────────────────

    async def _series(self, job: Job, title: TitleDetails, translator: Translator, control: Control) -> JobStatus:
        available = await self._client.episodes(title, translator)
        plan = [
            (season, episode)
            for season, episodes in available.items()
            if not job.seasons or season in job.seasons
            for episode in episodes
        ]
        if not plan:
            raise JobFailed("Для этой озвучки нет доступных серий")

        root = series_dir(self._settings, title.name, title.year)
        root.mkdir(parents=True, exist_ok=True)
        set_owner(root, self._settings)
        job.target = root.name
        job.total_episodes = len(plan)
        job.done_episodes = 0
        job.failed = []
        job.bytes_done = 0
        self._emit(job)

        for season, episode in plan:
            control.check()
            label = f"S{season:02d}E{episode:02d}"
            destination = episode_path(root, season, episode)
            job.current = label
            job.downloaded = job.total = 0
            if destination.is_file() and destination.stat().st_size > 0:
                job.done_episodes += 1
                job.bytes_done += destination.stat().st_size
                self._emit(job)
                continue
            try:
                stream, choice = await self._select(
                    title, translator, job.max_height, destination, control, season, episode
                )
                job.quality = choice.label

                async def refresh(s: int = season, e: int = episode, q: str = choice.label) -> Probed | None:
                    return await self._same_encode(title, translator, q, s, e)

                self._ensure_space(choice.size, destination)
                await self._fetch(choice, destination, job, control, refresh)
                await self._subtitles(stream.subtitles, destination)
                job.done_episodes += 1
                job.bytes_done += destination.stat().st_size
            except (Interrupted, NoSpace):
                raise
            except (JobFailed, RezkaError, OSError) as exc:
                logger.warning("Episode %s of %s failed: %s", label, title.name, exc)
                job.failed.append(label)
            self._emit(job)

        job.current = ""
        job.downloaded = job.total = 0
        if job.failed and job.done_episodes == 0:
            raise JobFailed("Не удалось скачать ни одной серии")
        if job.failed:
            job.error = f"Не скачались: {', '.join(job.failed[:8])}{'…' if len(job.failed) > 8 else ''}"
            return JobStatus.PARTIAL
        return JobStatus.SUCCESS

    # ── choosing what to download ────────────────────────────────────────────

    async def _probe(
        self, title: TitleDetails, translator: Translator, season: int | None, episode: int | None
    ) -> tuple[Stream, list[Probed]]:
        stream = await self._client.stream(title, translator, season, episode)
        return stream, await probe(self._http, stream.qualities, self._settings.user_agent)

    async def _select(
        self,
        title: TitleDetails,
        translator: Translator,
        max_height: int,
        destination: Path,
        control: Control,
        season: int | None = None,
        episode: int | None = None,
    ) -> tuple[Stream, Probed]:
        """Pick the encode to download, honouring an existing ``.part``.

        Stream links are re-resolved on every (re)start and the CDN may offer a
        different set of qualities; appending another encode to a ``.part``
        would corrupt the file. The ``.part.json`` passport records the encode,
        and the part is only dropped when that encode verifiably changed.
        """
        part, passport = part_path(destination), passport_path(destination)
        saved: dict = {}
        if part.exists():
            try:
                saved = json.loads(passport.read_text())
            except (OSError, ValueError):
                logger.info("Discarding %s: no passport (left by an older version)", part.name)
                part.unlink(missing_ok=True)
        else:
            passport.unlink(missing_ok=True)

        for attempt in range(_PASSPORT_RETRIES if saved else 1):
            stream, probed = await self._probe(title, translator, season, episode)
            if stream.gated:
                raise JobFailed(PREMIUM_ONLY)
            if not saved:
                break
            same = next((p for p in probed if p.label == saved.get("label")), None)
            if same is not None and same.size == saved.get("size"):
                return stream, same
            if same is not None:
                logger.info("%s changed upstream (%s → %s bytes), restarting", part.name, saved.get("size"), same.size)
                part.unlink(missing_ok=True)
                passport.unlink(missing_ok=True)
                break
            if attempt < _PASSPORT_RETRIES - 1:
                await control.sleep(self._settings.retry_delay)
        else:
            # the encode of the part is temporarily unreachable — keep the part for a later retry
            raise JobFailed(f"Качество {saved.get('label')} сейчас недоступно на зеркалах, повторите позже")

        choice = pick_best(probed, max_height)
        if choice is None:
            if stream.qualities and all(q.premium for q in stream.qualities):
                raise JobFailed(PREMIUM_ONLY)
            raise JobFailed("Зеркала HDRezka не отдают видео, попробуйте позже")
        logger.info("%s%s: %s (%.0f MB)", title.name, f" S{season}E{episode}" if season else "", choice.label,
                    choice.size / 1024**2)
        return stream, choice

    async def _same_encode(
        self,
        title: TitleDetails,
        translator: Translator,
        label: str,
        season: int | None = None,
        episode: int | None = None,
    ) -> Probed | None:
        """Fresh links for the encode being downloaded (links expire); None if it is unreachable now."""
        try:
            _, probed = await self._probe(title, translator, season, episode)
        except (JobFailed, RezkaError) as exc:
            logger.warning("Could not refresh links: %s", exc)
            return None
        return next((p for p in probed if p.label == label), None)

    def _ensure_space(self, size: int, destination: Path) -> None:
        part = part_path(destination)
        needed = size - (part.stat().st_size if part.exists() else 0)
        free = shutil.disk_usage(self._settings.media_dir).free
        if free - needed < self._settings.min_free_space:
            raise NoSpace()

    # ── transfer ─────────────────────────────────────────────────────────────

    async def _fetch(self, choice: Probed, destination: Path, job: Job, control: Control, refresh: Refresh) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        set_owner(destination.parent, self._settings)
        part, passport = part_path(destination), passport_path(destination)
        urls, size = choice.urls, choice.size

        offset = part.stat().st_size if part.exists() else 0
        if offset > size:
            part.unlink()
            offset = 0
        passport.write_text(json.dumps({"label": choice.label, "size": size}))
        job.total, job.downloaded = size, offset
        meter = SpeedMeter()

        failures = 0
        allow_restart = False
        while offset < size:
            control.check()
            round_start = offset
            ignored_range = 0
            for url in urls:
                try:
                    offset = await self._stream_into(url, part, offset, size, job, meter, control, allow_restart)
                except RangeIgnored:
                    ignored_range += 1
                except (MirrorError, aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                    logger.warning("Mirror failed for %s at %d/%d: %r", job.current, offset, size, exc)
                    offset = part.stat().st_size if part.exists() else 0
                    continue
                if offset >= size:
                    break
            if offset >= size:
                break
            # every mirror refused to resume — only then start the file over
            allow_restart = ignored_range == len(urls)
            failures = 0 if offset > round_start else failures + 1
            if failures >= self._settings.max_retries:
                raise JobFailed("Не удалось скачать файл — зеркала обрывают соединение")
            job.speed = 0.0
            self._emit(job)
            await control.sleep(self._settings.retry_delay * max(1, failures))
            fresh = await refresh()  # stream links expire — get new ones for the same encode
            if fresh is None:
                continue
            if fresh.size != size:
                logger.warning("Remote size changed %d → %d, restarting file", size, fresh.size)
                part.unlink(missing_ok=True)
                offset, size = 0, fresh.size
                passport.write_text(json.dumps({"label": fresh.label, "size": size}))
                job.total, job.downloaded = size, 0
            urls = fresh.urls

        try:
            os.replace(part, destination)
        except OSError as exc:
            raise JobFailed(f"Не удалось сохранить файл: {exc.strerror or exc}") from exc
        passport.unlink(missing_ok=True)
        set_owner(destination, self._settings)

    async def _stream_into(
        self,
        url: str,
        part: Path,
        offset: int,
        size: int,
        job: Job,
        meter: SpeedMeter,
        control: Control,
        allow_restart: bool,
    ) -> int:
        if offset >= size:
            return offset
        headers = {"User-Agent": self._settings.user_agent}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        response = await control.race(self._http.get(url, headers=headers))
        try:
            if response.status == 200 and offset:
                if not allow_restart:
                    raise RangeIgnored(url)
                logger.info("No mirror resumes %s — restarting from 0", job.current)
                offset = 0
            elif response.status == 206:
                start = response.headers.get("Content-Range", "").removeprefix("bytes ").split("-", 1)[0]
                if not start.isdigit() or int(start) != offset:
                    raise MirrorError(f"unexpected Content-Range {response.headers.get('Content-Range')}")
            elif response.status != 200:
                raise MirrorError(f"HTTP {response.status}")
            remote = total_size(response)
            if remote and remote != size:
                raise MirrorError(f"size {remote} != expected {size}")

            loop = asyncio.get_running_loop()
            chunks = response.content.iter_chunked(self._settings.chunk_size).__aiter__()
            with open(part, "r+b" if offset else "wb") as handle:
                handle.seek(offset)
                handle.truncate()
                while True:
                    try:
                        chunk = await control.race(chunks.__anext__())
                    except StopAsyncIteration:
                        break
                    await loop.run_in_executor(None, handle.write, chunk)
                    offset += len(chunk)
                    job.downloaded = offset
                    job.speed = meter.add(len(chunk))
                    self._emit(job)
            return offset
        finally:
            response.close()

    async def _subtitles(self, subtitles: list[Subtitle], video: Path) -> None:
        for subtitle in subtitles:
            target = subtitle_path(video, subtitle.lang)
            try:
                async with self._http.get(subtitle.url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        continue
                    content = await response.read()
                target.write_bytes(content)
                set_owner(target, self._settings)
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                logger.info("Subtitle %s skipped: %s", subtitle.lang, exc)
