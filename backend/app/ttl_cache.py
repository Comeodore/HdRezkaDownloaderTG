import time
from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Tiny LRU cache with per-entry expiry — enough for a single-process app."""

    def __init__(self, ttl: float, max_size: int) -> None:
        self._ttl = ttl
        self._max_size = max_size
        self._data: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: K, value: V, ttl: float | None = None) -> None:
        self._data[key] = (time.monotonic() + (ttl if ttl is not None else self._ttl), value)
        self._data.move_to_end(key)
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)

    def pop(self, key: K) -> None:
        self._data.pop(key, None)
