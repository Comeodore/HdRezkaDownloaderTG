import os
from pathlib import Path

from ..config import Settings
from ..logging_conf import get_logger

logger = get_logger("paths")

_REPLACEMENTS = {
    "/": "_", "\\": "_", ":": "_", "*": "_", "?": "_",
    '"': "_", "<": "_", ">": "_", "|": "_", "\n": " ", "\r": " ",
}


def sanitize_filename(name: str, max_length: int = 100) -> str:
    for char, replacement in _REPLACEMENTS.items():
        name = name.replace(char, replacement)
    name = name.strip()
    if len(name) > max_length:
        return name[: max_length - 3] + "..."
    return name


def set_owner(path: str | Path, settings: Settings) -> None:
    try:
        os.chown(path, settings.samba_uid, settings.samba_gid)
    except OSError as exc:
        logger.debug("chown failed for %s: %s", path, exc)


def movie_path(settings: Settings, name: str) -> Path:
    return Path(settings.media_dir) / f"{sanitize_filename(name)}.mp4"


def series_dir(settings: Settings, name: str) -> Path:
    return Path(settings.media_dir) / sanitize_filename(name)


def episode_path(series_root: Path, season: int, episode: int) -> Path:
    return series_root / f"Сезон {season}" / f"S{season:02d}E{episode:02d}.mp4"
