import asyncio
from uuid import uuid4

import aiohttp

from ..config import Settings
from ..logging_conf import get_logger
from ..rezka.session import RezkaGateway
from .engine import DownloadEngine
from .progress import TERMINAL_STATUSES, Job, JobReporter, JobStatus, ProgressHub

logger = get_logger("manager")


class DownloadManager:
    def __init__(self, settings: Settings, gateway: RezkaGateway) -> None:
        self._settings = settings
        self._gateway = gateway
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancels: dict[str, asyncio.Event] = {}
        self._paused: set[str] = set()
        self._semaphore = asyncio.Semaphore(settings.download_concurrency)
        self._http: aiohttp.ClientSession | None = None
        self.hub = ProgressHub()

    async def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            timeout = aiohttp.ClientTimeout(
                total=None,
                connect=self._settings.connect_timeout,
                sock_read=self._settings.read_timeout,
            )
            self._http = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": self._settings.user_agent},
            )
        return self._http

    async def create(
        self,
        url: str,
        translator_id: int,
        poster: str | None = None,
        seasons: list[int] | None = None,
    ) -> Job:
        details = await self._gateway.details(url)
        translator_name = next(
            (t.name for t in details.translators if t.id == translator_id),
            f"Перевод {translator_id}",
        )
        job = Job(
            id=uuid4().hex[:8],
            url=url,
            translator_id=translator_id,
            translator_name=translator_name,
            name=details.name,
            kind=details.kind,
            is_series=details.is_series,
            year=details.year,
            poster=poster,
            seasons=sorted(set(seasons or [])),
        )
        self._jobs[job.id] = job
        self._cancels[job.id] = asyncio.Event()
        self._tasks[job.id] = asyncio.create_task(self._run(job), name=f"dl_{job.id}")
        logger.info("Job %s created: %s (%s)", job.id, job.name, "series" if job.is_series else "movie")
        return job

    async def _run(self, job: Job) -> None:
        reporter = JobReporter(job, self.hub, self._settings.progress_interval)
        try:
            async with self._semaphore:
                if self._cancels[job.id].is_set():
                    reporter.status(JobStatus.PAUSED if job.id in self._paused else JobStatus.CANCELLED)
                    return
                reporter.status(JobStatus.RUNNING)
                api = await self._gateway.open_title(job.url)
                engine = DownloadEngine(self._settings, await self._session())
                await engine.run(api, job, reporter, lambda: self._cancels[job.id].is_set())
                if self._cancels[job.id].is_set() and job.id in self._paused:
                    reporter.status(JobStatus.PAUSED)
        except asyncio.CancelledError:
            reporter.status(JobStatus.CANCELLED)
            raise
        except Exception as exc:
            logger.exception("Job %s failed", job.id)
            reporter.status(JobStatus.ERROR, str(exc))
        finally:
            self._tasks.pop(job.id, None)

    def list_jobs(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _publish(self, job: Job) -> None:
        self.hub.publish({"type": "job", "job": job.snapshot()})

    def _is_active(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        return task is not None and not task.done()

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        self._paused.discard(job_id)
        event = self._cancels.get(job_id)
        if event:
            event.set()
        if not self._is_active(job_id):
            job.status = JobStatus.CANCELLED
            job.speed = 0.0
            self._publish(job)
        logger.info("Job %s cancelled", job_id)
        return True

    async def pause(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status not in (JobStatus.RUNNING, JobStatus.QUEUED):
            return False
        self._paused.add(job_id)
        event = self._cancels.get(job_id)
        if event:
            event.set()
        logger.info("Job %s paused", job_id)
        return True

    async def resume(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job_id not in self._paused:
            return None
        self._paused.discard(job_id)
        self._cancels[job_id] = asyncio.Event()
        job.status = JobStatus.QUEUED
        self._publish(job)
        self._tasks[job_id] = asyncio.create_task(self._run(job), name=f"dl_{job_id}")
        logger.info("Job %s resumed", job_id)
        return job

    async def retry(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return await self.create(job.url, job.translator_id, poster=job.poster, seasons=job.seasons)

    def remove(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        self._cancels.pop(job_id, None)
        self._jobs.pop(job_id, None)
        return True

    def clear_finished(self) -> list[Job]:
        for job_id in [jid for jid, job in self._jobs.items() if job.status in TERMINAL_STATUSES]:
            self._jobs.pop(job_id, None)
            self._cancels.pop(job_id, None)
            self._paused.discard(job_id)
        remaining = self.list_jobs()
        self.hub.publish({"type": "snapshot", "jobs": [job.snapshot() for job in remaining]})
        return remaining

    async def close(self) -> None:
        for event in self._cancels.values():
            event.set()
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._http and not self._http.closed:
            await self._http.close()
