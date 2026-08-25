import hashlib
import shutil
from pathlib import Path

from ..config import Settings

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".webm"}


def _entry_id(path: Path) -> str:
    return hashlib.sha1(path.name.encode()).hexdigest()[:12]


def list_items(settings: Settings) -> list[dict]:
    root = Path(settings.media_dir)
    if not root.exists():
        return []

    items: list[dict] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix.lower() in VIDEO_EXTS:
            items.append({
                "id": _entry_id(entry),
                "name": entry.stem,
                "kind": "movie",
                "size": entry.stat().st_size,
            })
        elif entry.is_dir():
            files = [f for f in entry.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXTS]
            if not files:
                continue
            items.append({
                "id": _entry_id(entry),
                "name": entry.name,
                "kind": "series",
                "size": sum(f.stat().st_size for f in files),
                "episodes": len(files),
                "seasons": len({f.parent.name for f in files}),
            })
    return items


def delete_item(settings: Settings, item_id: str) -> bool:
    root = Path(settings.media_dir)
    if not root.exists():
        return False
    for entry in root.iterdir():
        if entry.name.startswith("."):
            continue
        if _entry_id(entry) == item_id:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            return True
    return False
