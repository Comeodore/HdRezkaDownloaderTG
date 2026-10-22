import os
import re
from pathlib import Path

from ..config import Settings
from ..logging_conf import get_logger

logger = get_logger("paths")

_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_SPACES_RE = re.compile(r"\s+")


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """Make a title safe for every SMB client: no reserved chars, no trailing dots/spaces."""
    cleaned = _SPACES_RE.sub(" ", _FORBIDDEN_RE.sub("_", name)).strip().rstrip(". ")
    if len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 1].rstrip(". ") + "…"
    return cleaned or "Без названия"


def display_name(name: str, year: int | None) -> str:
    return f"{name} ({year})" if year else name


def set_owner(path: str | Path, settings: Settings) -> None:
    try:
        os.chown(path, settings.samba_uid, settings.samba_gid)
    except OSError as exc:
        logger.debug("chown failed for %s: %s", path, exc)


def movie_path(settings: Settings, name: str, year: int | None) -> Path:
    return Path(settings.media_dir) / f"{sanitize_filename(display_name(name, year))}.mp4"


def existing_movie(settings: Settings, name: str, year: int | None) -> Path | None:
    """The movie file if it is already in the library (pre-v2 files were saved without the year)."""
    for candidate in (movie_path(settings, name, year), Path(settings.media_dir) / f"{sanitize_filename(name)}.mp4"):
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def series_dir(settings: Settings, name: str, year: int | None) -> Path:
    """``Title (Year)`` for new shows; an existing pre-v2 ``Title`` folder keeps being used."""
    root = Path(settings.media_dir)
    preferred = root / sanitize_filename(display_name(name, year))
    legacy = root / sanitize_filename(name)
    if not preferred.exists() and legacy.is_dir():
        return legacy
    return preferred


def episode_path(series_root: Path, season: int, episode: int) -> Path:
    return series_root / f"Сезон {season}" / f"S{season:02d}E{episode:02d}.mp4"


def subtitle_path(video: Path, lang: str) -> Path:
    safe = re.sub(r"[^\w-]", "", lang)[:12] or "sub"
    return video.with_name(f"{video.stem}.{safe}.vtt")


def part_path(destination: Path) -> Path:
    return destination.with_name(destination.name + ".part")


def passport_path(destination: Path) -> Path:
    """Records which encode a ``.part`` belongs to, so a resume never mixes two files."""
    return destination.with_name(destination.name + ".part.json")
