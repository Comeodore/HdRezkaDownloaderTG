import asyncio
import glob
import hashlib
import re
import shutil
import time
from pathlib import Path

from ..config import Settings
from ..download.paths import existing_movie, series_dir
from ..rezka.client import RezkaClient
from ..storage import JsonFile

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".webm", ".m4v", ".mov"}
_EPISODE_RE = re.compile(r"S(\d+)E(\d+)", re.I)


def entry_id(name: str) -> str:
    return hashlib.sha1(name.encode()).hexdigest()[:12]


class LibraryMeta:
    """Remembers where library entries came from, so the list can show posters and links."""

    def __init__(self, settings: Settings) -> None:
        self._file = JsonFile(Path(settings.data_dir) / "library.json", {})
        self._data: dict[str, dict] = self._file.load()

    def get(self, name: str) -> dict:
        return self._data.get(name, {})

    def record(self, name: str, **meta: object) -> None:
        self._data[name] = {**self._data.get(name, {}), **meta, "updated_at": time.time()}
        self._file.save(self._data)

    def forget(self, name: str) -> None:
        if self._data.pop(name, None) is not None:
            self._file.save(self._data)


def _videos(folder: Path) -> list[Path]:
    return [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXTS and not f.name.startswith(".")]


def list_items(settings: Settings, meta: LibraryMeta) -> list[dict]:
    root = Path(settings.media_dir)
    if not root.is_dir():
        return []

    items: list[dict] = []
    for entry in root.iterdir():
        if entry.name.startswith((".", "@", "#")):
            continue
        info = meta.get(entry.name)
        base = {
            "id": entry_id(entry.name),
            "entry": entry.name,
            "name": entry.stem if entry.is_file() else entry.name,
            "title": info.get("title"),
            "year": info.get("year"),
            "url": info.get("url"),
            "poster": info.get("poster"),
        }
        if entry.is_file() and entry.suffix.lower() in VIDEO_EXTS:
            stat = entry.stat()
            items.append({**base, "kind": "movie", "size": stat.st_size, "modified": stat.st_mtime})
        elif entry.is_dir():
            files = _videos(entry)
            if not files:
                continue
            stats = [f.stat() for f in files]
            episodic = [f for f in files if _EPISODE_RE.search(f.name)]
            items.append({
                **base,
                "kind": "series" if episodic or len(files) > 1 else "movie",
                "size": sum(s.st_size for s in stats),
                "modified": max(s.st_mtime for s in stats),
                "episodes": len(episodic) or len(files),
                "seasons": len({f.parent for f in files}),
            })
    items.sort(key=lambda item: item["modified"], reverse=True)
    return items


def find_entry(settings: Settings, item_id: str) -> Path | None:
    root = Path(settings.media_dir)
    if not root.is_dir():
        return None
    return next((e for e in root.iterdir() if not e.name.startswith(".") and entry_id(e.name) == item_id), None)


def delete_entry(entry: Path) -> None:
    if entry.is_dir():
        shutil.rmtree(entry)
    else:
        entry.unlink(missing_ok=True)
        for sidecar in entry.parent.glob(f"{glob.escape(entry.stem)}.*.vtt"):
            sidecar.unlink(missing_ok=True)


def disk_usage(settings: Settings) -> dict:
    try:
        usage = shutil.disk_usage(settings.media_dir)
    except OSError:
        return {"total": 0, "used": 0, "free": 0}
    return {"total": usage.total, "used": usage.used, "free": usage.free}


def local_state(settings: Settings, name: str, year: int | None, is_series: bool) -> dict:
    """What of this title is already on disk — drives the «в медиатеке» hints."""
    if not is_series:
        found = existing_movie(settings, name, year)
        return {"exists": found is not None, "episodes": {}}
    root = series_dir(settings, name, year)
    episodes: dict[int, int] = {}
    if root.is_dir():
        for video in _videos(root):
            match = _EPISODE_RE.search(video.name)
            if match and video.stat().st_size > 0:
                season = int(match.group(1))
                episodes[season] = episodes.get(season, 0) + 1
    return {"exists": bool(episodes), "episodes": episodes}


_YEAR_SUFFIX_RE = re.compile(r"\s*\((\d{4})\)$")


def _split_year(name: str) -> tuple[str, int | None]:
    match = _YEAR_SUFFIX_RE.search(name)
    return (name[: match.start()], int(match.group(1))) if match else (name, None)


class LibraryEnricher:
    """Finds posters and HDRezka links for library entries that predate v2 metadata.

    Runs in the background, once per entry: only an exact title match of a
    compatible kind is accepted, so ambiguous names stay without a poster
    rather than getting a wrong one.
    """

    def __init__(self, meta: LibraryMeta, client: RezkaClient) -> None:
        self._meta = meta
        self._client = client
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def missing(self, items: list[dict]) -> list[dict]:
        return [item for item in items if not item.get("url") and not self._meta.get(item["entry"]).get("lookup_at")]

    def schedule(self, items: list[dict]) -> bool:
        pending = self.missing(items)
        if not pending or self.running:
            return self.running
        self._task = asyncio.create_task(self._run(pending))
        return True

    async def _run(self, items: list[dict]) -> None:
        for item in items:
            title, year = _split_year(item["name"])
            key = item["entry"]
            try:
                page = await self._client.search(title)
            except Exception:  # noqa: BLE001 — best effort, retried on a later visit
                continue
            wanted = {"movie", "cartoon", "anime"} if item["kind"] == "movie" else {"series", "cartoon", "anime"}
            matches = [
                found for found in page.items
                if found.title.casefold() == title.casefold() and found.kind in wanted
                and (year is None or (found.year or "").startswith(str(year)))
            ]
            if len(matches) == 1 or (matches and year):
                found = matches[0]
                found_year = int(found.year[:4]) if found.year and found.year[:4].isdigit() else None
                self._meta.record(key, title=found.title, year=found_year, url=found.url, poster=found.poster,
                                  kind=found.kind, guessed=True, lookup_at=time.time())
            else:
                self._meta.record(key, lookup_at=time.time())
            await asyncio.sleep(0.5)
