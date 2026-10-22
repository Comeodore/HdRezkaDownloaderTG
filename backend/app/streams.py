import asyncio

import aiohttp

from .config import Settings
from .download.engine import PREMIUM_ONLY
from .download.quality import Probed, probe
from .rezka.client import RezkaClient, RezkaError
from .rezka.models import TitleDetails, Translator
from .ttl_cache import TTLCache


class PremiumOnly(RezkaError):
    status_code = 403


class StreamResolver:
    """Resolves and probes playable mirrors for a title+voice (first episode for series).

    Shared by the quality picker and the preview player; results are cached
    because the frontend warms them up as soon as a voice is selected.
    """

    def __init__(self, settings: Settings, client: RezkaClient) -> None:
        self._settings = settings
        self._client = client
        self._cache: TTLCache[tuple[str, str], list[Probed]] = TTLCache(ttl=900, max_size=64)
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._http: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, connect=15, sock_read=60),
            connector=aiohttp.TCPConnector(limit=32, ttl_dns_cache=600, keepalive_timeout=60),
            headers={"User-Agent": self._settings.user_agent},
        )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.close()

    @property
    def http(self) -> aiohttp.ClientSession:
        assert self._http is not None, "resolver not started"
        return self._http

    async def resolve(self, title: TitleDetails, translator: Translator) -> list[Probed]:
        key = (title.url, translator.key)
        if (cached := self._cache.get(key)) is not None:
            return cached
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if (cached := self._cache.get(key)) is not None:
                return cached
            season = episode = None
            if title.is_series:
                episodes = await self._client.episodes(title, translator)
                if not episodes:
                    raise RezkaError("Для этой озвучки нет серий")
                season = next(iter(episodes))
                episode = episodes[season][0]
            stream = await self._client.stream(title, translator, season, episode)
            if stream.gated:
                raise PremiumOnly(PREMIUM_ONLY)
            probed = await probe(self.http, stream.qualities, self._settings.user_agent)
            self._cache.set(key, probed, ttl=900 if probed else 60)
            self._locks.pop(key, None)
            return probed

    def forget(self, title: TitleDetails, translator: Translator) -> None:
        self._cache.pop((title.url, translator.key))
