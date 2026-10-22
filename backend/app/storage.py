import json
import os
from pathlib import Path
from typing import Any

from .logging_conf import get_logger

logger = get_logger("storage")


class JsonFile:
    """Atomic JSON persistence for small state (jobs, library metadata)."""

    def __init__(self, path: Path, default: Any) -> None:
        self._path = path
        self._default = default

    def load(self) -> Any:
        try:
            return json.loads(self._path.read_text())
        except FileNotFoundError:
            return self._default
        except (OSError, ValueError) as exc:
            logger.error("Could not read %s (%s) — starting empty", self._path, exc)
            return self._default

    def save(self, data: Any) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._path.with_suffix(self._path.suffix + ".tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False))
            os.replace(temp, self._path)
        except OSError as exc:
            logger.error("Could not write %s: %s", self._path, exc)
