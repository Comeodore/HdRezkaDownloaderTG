import asyncio
import time
from dataclasses import asdict, dataclass, field, fields
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    CANCELLED = "cancelled"


ACTIVE_STATUSES = {JobStatus.QUEUED, JobStatus.RUNNING}
TERMINAL_STATUSES = {JobStatus.SUCCESS, JobStatus.PARTIAL, JobStatus.ERROR, JobStatus.CANCELLED}


@dataclass
class Job:
    id: str
    url: str
    name: str
    kind: str
    is_series: bool
    translator_key: str
    translator_name: str
    year: int | None = None
    poster: str | None = None
    max_height: int = 1080
    seasons: list[int] = field(default_factory=list)
    owner_id: int = 0
    status: JobStatus = JobStatus.QUEUED
    quality: str | None = None
    # current file
    current: str = ""
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0  # bytes/s
    # series aggregate
    done_episodes: int = 0
    total_episodes: int = 0
    failed: list[str] = field(default_factory=list)
    bytes_done: int = 0  # finished files of this job
    error: str | None = None
    target: str | None = None  # library entry name (file or folder)
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    version: int = 0

    @property
    def percent(self) -> float:
        current = self.downloaded / self.total if self.total else 0.0
        if self.is_series:
            if not self.total_episodes:
                return 0.0
            return min(100.0, (self.done_episodes + current) / self.total_episodes * 100)
        if self.status == JobStatus.SUCCESS:
            return 100.0
        return min(100.0, current * 100)

    @property
    def eta(self) -> int | None:
        if self.status != JobStatus.RUNNING or self.speed <= 0 or not self.total:
            return None
        remaining = max(0, self.total - self.downloaded)
        if self.is_series and self.total_episodes:
            left = self.total_episodes - self.done_episodes - 1
            remaining += max(0, left) * self.total  # assume similar episode sizes
        return int(remaining / self.speed)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        known = {f.name for f in fields(cls)}
        values = {key: value for key, value in data.items() if key in known}
        values["status"] = JobStatus(values.get("status", "queued"))
        return cls(**values)


class ProgressHub:
    """Fan-out of job events to SSE subscribers; slow consumers drop events, never block."""

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


class SpeedMeter:
    """Exponential moving average of throughput, robust to bursty chunk arrival."""

    def __init__(self, smoothing: float = 0.3) -> None:
        self._smoothing = smoothing
        self._last_time = time.monotonic()
        self._pending = 0
        self.value = 0.0

    def add(self, size: int) -> float:
        self._pending += size
        now = time.monotonic()
        elapsed = now - self._last_time
        if elapsed >= 1.0:
            sample = self._pending / elapsed
            self.value = sample if self.value == 0 else self.value + self._smoothing * (sample - self.value)
            self._pending = 0
            self._last_time = now
        return self.value
