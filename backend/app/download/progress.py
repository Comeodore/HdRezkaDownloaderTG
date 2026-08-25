import asyncio
import time
from dataclasses import asdict, dataclass, field
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {JobStatus.SUCCESS, JobStatus.PARTIAL, JobStatus.ERROR, JobStatus.CANCELLED}
RESTING_STATUSES = TERMINAL_STATUSES | {JobStatus.PAUSED}


@dataclass
class Job:
    id: str
    url: str
    translator_id: int
    translator_name: str
    name: str
    kind: str
    is_series: bool
    year: str | None = None
    poster: str | None = None
    quality: str | None = None
    seasons: list[int] = field(default_factory=list)
    status: JobStatus = JobStatus.QUEUED
    percent: float = 0.0
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    current: str = ""
    done_episodes: int = 0
    total_episodes: int = 0
    error: str | None = None
    created_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class ProgressHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass


class JobReporter:
    def __init__(self, job: Job, hub: ProgressHub, interval: float) -> None:
        self._job = job
        self._hub = hub
        self._interval = interval
        self._last_emit = 0.0
        self._last_key: tuple | None = None

    def _emit(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_emit) < self._interval:
            return
        self._last_emit = now
        self._hub.publish({"type": "job", "job": self._job.snapshot()})

    def progress(self, downloaded: int, total: int, speed: float, current: str = "") -> None:
        self._job.downloaded = downloaded
        self._job.total = total
        self._job.speed = speed
        self._job.percent = round(min(100.0, downloaded / total * 100), 1) if total else 0.0
        if current:
            self._job.current = current
        self._emit()

    def episodes(self, done: int, total: int) -> None:
        self._job.done_episodes = done
        self._job.total_episodes = total
        self._emit(force=True)

    def quality(self, quality: str | None) -> None:
        self._job.quality = quality
        self._emit(force=True)

    def status(self, status: JobStatus, error: str | None = None) -> None:
        self._job.status = status
        if error:
            self._job.error = error
        if status in RESTING_STATUSES:
            self._job.speed = 0.0
        self._emit(force=True)
