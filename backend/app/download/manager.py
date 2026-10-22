import asyncio
import time
from pathlib import Path
from uuid import uuid4

import aiohttp

from ..config import Settings
from ..library.service import LibraryMeta
from ..logging_conf import get_logger
from ..notify import Notifier
from ..rezka.client import RezkaClient, RezkaError
from ..storage import JsonFile
from .engine import Control, DownloadEngine, Interrupted, JobFailed
from .paths import movie_path, part_path, passport_path, series_dir
from .progress import ACTIVE_STATUSES, TERMINAL_STATUSES, Job, JobStatus, ProgressHub

logger = get_logger("manager")

_HISTORY_LIMIT = 200
_PUBLISH_INTERVAL = 1.0
_SAVE_INTERVAL = 15.0


class DownloadConflict(Exception):
    def __init__(self, message: str, job: Job) -> None:
        super().__init__(message)
        self.message = message
        self.job = job


class DownloadManager:
    """Owns the job queue: persistence across restarts, concurrency, pause/resume, notifications."""

    def __init__(self, settings: Settings, client: RezkaClient, meta: LibraryMeta, notifier: Notifier) -> None:
        self._settings = settings
        self._client = client
        self._meta = meta
        self._notifier = notifier
        self._store = JsonFile(Path(settings.data_dir) / "jobs.json", [])
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._controls: dict[str, Control] = {}
        self._semaphore = asyncio.Semaphore(settings.download_concurrency)
        self._http: aiohttp.ClientSession | None = None
        self._last_publish: dict[str, float] = {}
        self._last_save = 0.0
        self.hub = ProgressHub()

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=None, connect=self._settings.connect_timeout, sock_read=self._settings.read_timeout
            ),
            connector=aiohttp.TCPConnector(limit=16, ttl_dns_cache=300),
            headers={"User-Agent": self._settings.user_agent},
        )
        for raw in self._store.load():
            try:
                job = Job.from_dict(raw)
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping unreadable job record: %s", exc)
                continue
            job.speed = 0.0
            self._jobs[job.id] = job
        resumed = 0
        for job in self._jobs.values():
            if job.status in ACTIVE_STATUSES:
                job.status = JobStatus.QUEUED
                self._spawn(job)
                resumed += 1
        if resumed:
            logger.info("Resuming %d unfinished download(s)", resumed)

    async def close(self) -> None:
        for control in self._controls.values():
            control.stop("shutdown")
        tasks = [task for task in self._tasks.values() if not task.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=10)
        self._save(force=True)
        if self._http is not None:
            await self._http.close()

    # ── queries ──────────────────────────────────────────────────────────────

    def list_jobs(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def busy_targets(self) -> set[str]:
        return {job.target for job in self._jobs.values() if job.target and job.status in ACTIVE_STATUSES}

    def active_count(self) -> int:
        return sum(1 for job in self._jobs.values() if job.status in ACTIVE_STATUSES)

    # ── commands ─────────────────────────────────────────────────────────────

    async def create(
        self, url: str, translator_key: str, seasons: list[int], max_height: int, owner_id: int
    ) -> Job:
        title = await self._client.title(url)
        translator = title.translator(translator_key)
        if translator is None:
            raise JobFailed("Неизвестная озвучка")
        wanted = sorted(set(seasons)) if title.is_series else []
        self._check_conflict(title.url, title.is_series, wanted)

        job = Job(
            id=uuid4().hex[:10],
            url=title.url,
            name=title.name,
            year=title.year,
            kind=title.kind,
            is_series=title.is_series,
            poster=title.poster,
            translator_key=translator.key,
            translator_name=translator.name,
            max_height=max_height,
            seasons=wanted,
            owner_id=owner_id,
        )
        self._jobs[job.id] = job
        self._trim_history()
        self._changed(job, force=True)
        self._spawn(job)
        logger.info("Job %s created: %s [%s] seasons=%s ≤%dp", job.id, job.name, translator.name, wanted or "all",
                    max_height)
        return job

    def _check_conflict(self, url: str, is_series: bool, seasons: list[int], exclude: str | None = None) -> None:
        """Two jobs must never write the same files: same movie, or overlapping seasons."""
        for existing in self._jobs.values():
            if existing.id == exclude or existing.url != url:
                continue
            if existing.status not in ACTIVE_STATUSES | {JobStatus.PAUSED} and not self._is_running(existing.id):
                continue
            if not is_series or not seasons or not existing.seasons or set(seasons) & set(existing.seasons):
                raise DownloadConflict("Этот тайтл уже в загрузках", existing)

    def pause(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        control = self._controls.get(job_id)
        if job is None or control is None or job.status not in ACTIVE_STATUSES:
            return False
        control.stop("pause")
        return True

    def resume(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job.status != JobStatus.PAUSED or self._is_running(job_id):
            return None
        self._check_conflict(job.url, job.is_series, job.seasons, exclude=job.id)
        job.status = JobStatus.QUEUED
        self._changed(job, force=True)
        self._spawn(job)
        return job

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return False
        if self._is_running(job_id):
            self._controls[job_id].stop("cancel")
        else:
            self._discard_parts(job)
            self._finish(job, JobStatus.CANCELLED)
        return True

    def retry(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job.status not in TERMINAL_STATUSES or self._is_running(job_id):
            return None
        self._check_conflict(job.url, job.is_series, job.seasons, exclude=job.id)
        job.status = JobStatus.QUEUED
        job.error = None
        job.failed = []
        job.finished_at = None
        job.created_at = time.time()
        self._changed(job, force=True)
        self._spawn(job)
        return job

    def remove(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in ACTIVE_STATUSES or self._is_running(job_id):
            return False
        if job.status == JobStatus.PAUSED:
            self._discard_parts(job)
        self._jobs.pop(job_id, None)
        self._controls.pop(job_id, None)
        self._publish_snapshot()
        self._save(force=True)
        return True

    def clear_finished(self) -> None:
        for job_id in [jid for jid, job in self._jobs.items() if job.status in TERMINAL_STATUSES]:
            self._jobs.pop(job_id, None)
            self._controls.pop(job_id, None)
        self._publish_snapshot()
        self._save(force=True)

    # ── execution ────────────────────────────────────────────────────────────

    def _is_running(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        return task is not None and not task.done()

    def _spawn(self, job: Job) -> None:
        control = Control()
        self._controls[job.id] = control
        self._tasks[job.id] = asyncio.create_task(self._run(job, control), name=f"download-{job.id}")

    async def _run(self, job: Job, control: Control) -> None:
        assert self._http is not None
        engine = DownloadEngine(self._settings, self._http, self._client, self._changed)
        try:
            await self._acquire_slot(control)
            try:
                job.status = JobStatus.RUNNING
                job.error = None
                self._changed(job, force=True)
                outcome = await engine.run(job, control)
            finally:
                self._semaphore.release()
            self._finish(job, outcome)
        except Interrupted:
            if control.mode == "pause":
                job.status = JobStatus.PAUSED
                self._changed(job, force=True)
            elif control.mode == "cancel":
                self._discard_parts(job)
                self._finish(job, JobStatus.CANCELLED)
            else:  # shutdown — keep it queued so the next start resumes it
                job.status = JobStatus.QUEUED
        except (JobFailed, RezkaError) as exc:
            self._finish(job, JobStatus.ERROR, exc.message)
        except asyncio.CancelledError:
            job.status = JobStatus.QUEUED
            raise
        except Exception as exc:  # noqa: BLE001 — a job must never die silently
            logger.exception("Job %s crashed", job.id)
            self._finish(job, JobStatus.ERROR, f"Внутренняя ошибка: {exc}")
        finally:
            job.speed = 0.0
            self._tasks.pop(job.id, None)
            self._save(force=True)

    async def _acquire_slot(self, control: Control) -> None:
        """Wait for a free download slot, but let pause/cancel interrupt a queued job."""
        control.check()
        acquire = asyncio.ensure_future(self._semaphore.acquire())
        stop = asyncio.ensure_future(control.event.wait())
        try:
            await asyncio.wait({acquire, stop}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            stop.cancel()
            if acquire.done() and not acquire.cancelled():
                self._semaphore.release()
            else:
                acquire.cancel()
            raise
        stop.cancel()
        if not acquire.done():
            acquire.cancel()
        elif not control.stopped:
            return
        else:
            self._semaphore.release()
        raise Interrupted(control.mode)

    def _finish(self, job: Job, status: JobStatus, error: str | None = None) -> None:
        job.status = status
        job.speed = 0.0
        if error:
            job.error = error
        job.finished_at = time.time()
        self._changed(job, force=True)
        logger.info("Job %s %s: %s %s", job.id, status.value, job.name, error or "")
        if status in (JobStatus.SUCCESS, JobStatus.PARTIAL) and job.target:
            self._meta.record(job.target, title=job.name, year=job.year, url=job.url, poster=job.poster, kind=job.kind)
        if status != JobStatus.CANCELLED:
            self._notifier.job_finished(job)

    def _discard_parts(self, job: Job) -> None:
        if job.is_series:
            # only this job's seasons: another job may be downloading other seasons right now
            root = series_dir(self._settings, job.name, job.year)
            folders = [root / f"Сезон {season}" for season in job.seasons] if job.seasons else [root]
            parts = [
                path
                for folder in folders
                if folder.is_dir()
                for pattern in ("*.part", "*.part.json")
                for path in folder.rglob(pattern)
            ]
        else:
            movie = movie_path(self._settings, job.name, job.year)
            parts = [part_path(movie), passport_path(movie)]
        for part in parts:
            part.unlink(missing_ok=True)

    # ── events & persistence ─────────────────────────────────────────────────

    def _changed(self, job: Job, force: bool = False) -> None:
        job.version += 1  # lets clients drop responses older than an event they already have
        now = time.monotonic()
        if force or now - self._last_publish.get(job.id, 0.0) >= _PUBLISH_INTERVAL:
            self._last_publish[job.id] = now
            self.hub.publish({"type": "job", "job": job})
        self._save(force=force)

    def _publish_snapshot(self) -> None:
        self.hub.publish({"type": "snapshot", "jobs": self.list_jobs()})

    def _save(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_save < _SAVE_INTERVAL:
            return
        self._last_save = now
        self._store.save([job.to_dict() for job in self.list_jobs()])

    def _trim_history(self) -> None:
        finished = [job for job in self.list_jobs() if job.status in TERMINAL_STATUSES]
        for job in finished[_HISTORY_LIMIT:]:
            self._jobs.pop(job.id, None)
