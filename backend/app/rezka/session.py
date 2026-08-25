import asyncio
import hashlib
import re
from typing import Callable, TypeVar
from urllib.parse import urlparse

from HdRezkaApi import HdRezkaApi
from HdRezkaApi.session import HdRezkaSession
from HdRezkaApi.types import TVSeries

from ..config import Settings
from ..logging_conf import get_logger
from .models import SearchItem, SeasonInfo, TitleDetails, Translator
from .ratings import external_rating

logger = get_logger("gateway")

_YEAR_RE = re.compile(r"-(\d{4})\.html$")
_CATEGORY_KIND = {"film": "movie", "series": "series", "cartoon": "cartoon", "animation": "anime"}

T = TypeVar("T")


def year_from_url(url: str) -> str | None:
    match = _YEAR_RE.search(url)
    return match.group(1) if match else None


def item_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def _kind_from_category(category: object) -> str:
    name = getattr(category, "name", None)
    return _CATEGORY_KIND.get(name, "unknown")


class RezkaGateway:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._session: HdRezkaSession | None = None
        self._lock = asyncio.Lock()

    async def _get_session(self, relogin: bool = False) -> HdRezkaSession:
        async with self._lock:
            if self._session is not None and not relogin:
                return self._session

            def build() -> HdRezkaSession:
                session = HdRezkaSession(origin=self._settings.hdrezka_origin)
                if self._settings.hdrezka_email and self._settings.hdrezka_password:
                    session.login(self._settings.hdrezka_email, self._settings.hdrezka_password)
                    logger.info("Logged in to %s", self._settings.hdrezka_origin)
                else:
                    logger.warning("HDREZKA credentials missing — anonymous session, expect login walls")
                return session

            self._session = await asyncio.to_thread(build)
            return self._session

    def build_api(self, session: HdRezkaSession, url: str) -> HdRezkaApi:
        path = urlparse(url).path
        origin = self._settings.hdrezka_origin.rstrip("/")
        normalized = f"{origin}/{path.lstrip('/')}" if path else url
        return HdRezkaApi(
            normalized,
            cookies=session.cookies,
            headers=session.HEADERS,
            proxy=session.proxy,
        )

    async def _threaded(self, fn: Callable[[HdRezkaSession], T]) -> T:
        session = await self._get_session()
        try:
            return await asyncio.to_thread(fn, session)
        except Exception as exc:
            logger.warning("Rezka call failed (%s) — retrying after relogin", exc)
            session = await self._get_session(relogin=True)
            return await asyncio.to_thread(fn, session)

    async def open_title(self, url: str) -> HdRezkaApi:
        def fn(session: HdRezkaSession) -> HdRezkaApi:
            api = self.build_api(session, url)
            if not api.ok:
                raise RuntimeError(str(getattr(api, "exception", "title not available")))
            return api

        return await self._threaded(fn)

    async def search(self, query: str) -> list[SearchItem]:
        def fn(session: HdRezkaSession) -> list[dict]:
            result = session.search(query, find_all=True)
            return list(result.all) if result else []

        raw = await self._threaded(fn)
        items: list[SearchItem] = []
        for entry in raw:
            url = entry.get("url")
            if not url:
                continue
            items.append(
                SearchItem(
                    id=item_id(url),
                    title=(entry.get("title") or "Без названия").strip(),
                    url=url,
                    year=year_from_url(url),
                    poster=entry.get("image"),
                    kind=_kind_from_category(entry.get("category")),
                )
            )
        return items

    async def details(self, url: str) -> TitleDetails:
        api = await self.open_title(url)

        def extract(api: HdRezkaApi) -> TitleDetails:
            translators = api.translators or {}
            rating_obj = getattr(api, "rating", None)
            rating_value = getattr(rating_obj, "value", None)
            is_series = api.type == TVSeries
            return TitleDetails(
                url=url,
                name=api.name,
                kind="series" if is_series else "movie",
                is_series=is_series,
                year=year_from_url(url),
                rating=float(rating_value) if rating_value else None,
                rating_imdb=external_rating(api.soup, "imdb"),
                rating_kp=external_rating(api.soup, "kp"),
                translators=[
                    Translator(id=int(tid), name=(info.get("name") or f"Перевод {tid}"))
                    for tid, info in translators.items()
                ],
            )

        return await asyncio.to_thread(extract, api)

    async def seasons(self, url: str, translator_id: int) -> list[SeasonInfo]:
        api = await self.open_title(url)

        def extract(api: HdRezkaApi) -> list[SeasonInfo]:
            series_info = api.seriesInfo or {}
            info = series_info.get(translator_id) or series_info.get(str(translator_id))
            if not info:
                return []
            seasons = info.get("seasons") or {}
            episodes = info.get("episodes") or {}
            result: list[SeasonInfo] = []
            for key in sorted(seasons.keys(), key=lambda value: int(value)):
                result.append(SeasonInfo(number=int(key), episodes=len(episodes.get(key) or {})))
            return result

        return await asyncio.to_thread(extract, api)
