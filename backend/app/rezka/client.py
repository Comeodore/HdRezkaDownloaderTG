import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp

from ..config import Settings
from ..logging_conf import get_logger
from ..ttl_cache import TTLCache
from . import parse
from .models import SearchPage, Stream, TitleDetails, Translator

logger = get_logger("rezka")

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_RELOGIN_INTERVAL = 30.0
_LOGIN_BACKOFF = 60.0


class RezkaError(Exception):
    status_code = 502

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RezkaUnavailable(RezkaError):
    status_code = 503


class RezkaNotFound(RezkaError):
    status_code = 404


class RezkaAuthError(RezkaError):
    status_code = 503


class BadTitleUrl(RezkaError):
    status_code = 400


class RezkaClient:
    """Async HDRezka client: one keep-alive session, hard timeouts, transparent re-login.

    Replaces the synchronous ``HdRezkaApi`` package, which had no request
    timeouts, walked every search page and every translator up front, and
    dropped the director/camrip flags needed to fetch the right cut.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._origin = settings.hdrezka_origin.rstrip("/")
        self._cookie_file = Path(settings.data_dir) / "rezka_cookies.json"
        self._cookies: dict[str, str] = {"hdmbbs": "1"}
        self._http: aiohttp.ClientSession | None = None
        self._login_lock = asyncio.Lock()
        self._last_login = 0.0
        self._generation = 0  # bumps on every successful login
        self._login_blocked_until = 0.0
        self._login_error = ""
        self._limiter = asyncio.Semaphore(settings.rezka_concurrency)
        self._titles: TTLCache[str, TitleDetails] = TTLCache(ttl=600, max_size=128)
        self._searches: TTLCache[tuple[str, int], SearchPage] = TTLCache(ttl=300, max_size=64)
        self._episodes: TTLCache[tuple[int, str], dict[int, list[int]]] = TTLCache(ttl=600, max_size=128)

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=25, connect=10),
            headers={"User-Agent": self._settings.user_agent, "Accept-Language": "ru-RU,ru;q=0.9"},
            cookie_jar=aiohttp.DummyCookieJar(),
        )
        try:
            saved = json.loads(self._cookie_file.read_text())
            if isinstance(saved, dict) and saved.get("dle_user_id"):
                self._cookies.update({str(k): str(v) for k, v in saved.items()})
                logger.info("Restored HDRezka session for user %s", saved.get("dle_user_id"))
        except (OSError, ValueError):
            pass

    async def close(self) -> None:
        if self._http is not None:
            await self._http.close()

    @property
    def logged_in(self) -> bool:
        return "dle_user_id" in self._cookies

    @property
    def origin(self) -> str:
        return self._origin

    # ── transport ────────────────────────────────────────────────────────────

    def normalize(self, url: str) -> str:
        """Pin any mirror URL to the configured origin; reject anything that isn't a title page."""
        path = urlparse(url.strip()).path
        if not parse.TITLE_PATH_RE.match(path):
            raise BadTitleUrl("Это не ссылка на фильм или сериал HDRezka")
        return f"{self._origin}{path}"

    async def _send(
        self, method: str, url: str, *, cookies: dict[str, str] | None = None, **kwargs: Any
    ) -> tuple[int, str, aiohttp.ClientResponse]:
        assert self._http is not None, "client not started"
        jar = self._cookies if cookies is None else cookies
        cookie = "; ".join(f"{key}={value}" for key, value in jar.items())
        headers = {"Cookie": cookie, "Referer": f"{self._origin}/", **kwargs.pop("headers", {})}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with self._limiter, self._http.request(method, url, headers=headers, **kwargs) as response:
                    body = await response.text()
                    if response.status in _RETRY_STATUSES and attempt < 2:
                        last_error = RezkaUnavailable(f"HDRezka ответила {response.status}")
                    else:
                        return response.status, body, response
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
            await asyncio.sleep(0.6 * (attempt + 1))
        logger.warning("%s %s failed: %r", method, url, last_error)
        raise RezkaUnavailable("HDRezka не отвечает, попробуйте позже") from last_error

    async def _page(self, url: str, **kwargs: Any) -> str:
        for attempt in range(2):
            generation = self._generation
            status, body, _ = await self._send("GET", url, **kwargs)
            if status == 404:
                raise RezkaNotFound("Страница не найдена на HDRezka")
            if status >= 400:
                raise RezkaUnavailable(f"HDRezka ответила {status}")
            try:
                parse.detect_wall(body)
            except parse.LoginRequired:
                if attempt == 0 and await self._refresh_session(generation, auth_failure=True):
                    continue
                raise RezkaAuthError("HDRezka требует вход — проверьте логин и пароль") from None
            except parse.CaptchaRequired:
                raise RezkaUnavailable(
                    "HDRezka включила проверку «не бот» — попробуйте позже или другое зеркало (HDREZKA_ORIGIN)"
                ) from None
            return body
        raise RezkaAuthError("HDRezka требует вход")

    async def _ajax(self, path: str, data: dict[str, Any]) -> dict:
        url = f"{self._origin}{path}?t={int(time.time() * 1000)}"
        for attempt in range(2):
            generation = self._generation
            status, body, _ = await self._send(
                "POST", url, data=data, headers={"X-Requested-With": "XMLHttpRequest"}
            )
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            if isinstance(payload, dict) and payload.get("success"):
                return payload
            message = payload.get("message") if isinstance(payload, dict) else None
            # an expired session surfaces here only as success=false, indistinguishable from a real error
            if attempt == 0 and await self._refresh_session(generation, auth_failure=False):
                continue
            raise RezkaError(message or f"HDRezka вернула ошибку ({status})")
        raise RezkaError("HDRezka вернула ошибку")

    # ── auth ─────────────────────────────────────────────────────────────────

    async def _refresh_session(self, seen_generation: int, auth_failure: bool) -> bool:
        """Re-login after a failed request; True when retrying the request makes sense.

        If the session changed while the request was in flight, just retry.
        A failure right after a successful login is not an auth problem
        (unless the page itself was the sign-in wall), so don't hammer the
        login endpoint for it.
        """
        if self._generation != seen_generation:
            return True
        if not auth_failure and time.monotonic() - self._last_login < _RELOGIN_INTERVAL:
            return False
        try:
            await self.login(force=True)
        except RezkaError:
            return False
        return self._generation != seen_generation

    async def login(self, force: bool = False) -> None:
        email, password = self._settings.hdrezka_email, self._settings.hdrezka_password
        async with self._login_lock:
            if self.logged_in and not force:
                return
            if force and time.monotonic() - self._last_login < 5:
                return  # another request has just refreshed the session
            if time.monotonic() < self._login_blocked_until:
                raise RezkaAuthError(self._login_error)
            if not email or not password:
                logger.warning("HDREZKA_EMAIL/HDREZKA_PASSWORD not set — anonymous session")
                return
            try:
                status, body, response = await self._send(
                    "POST",
                    f"{self._origin}/ajax/login/",
                    cookies={"hdmbbs": "1"},  # the current session stays usable until the new one exists
                    data={"login_name": email, "login_password": password, "login_not_save": "0"},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                try:
                    payload = json.loads(body)
                except ValueError:
                    payload = {}
                if not payload.get("success"):
                    logger.error("HDRezka login failed (%s): %s", status, payload.get("message"))
                    raise RezkaAuthError(f"Не удалось войти в HDRezka: {payload.get('message') or status}")
            except RezkaError as exc:
                self._login_blocked_until = time.monotonic() + _LOGIN_BACKOFF
                self._login_error = exc.message
                raise
            self._cookies = {"hdmbbs": "1", **{name: morsel.value for name, morsel in response.cookies.items()}}
            self._generation += 1
            self._last_login = time.monotonic()
            self._persist_cookies()
            logger.info("Logged in to %s", self._origin)

    def _persist_cookies(self) -> None:
        try:
            self._cookie_file.parent.mkdir(parents=True, exist_ok=True)
            temp = self._cookie_file.with_suffix(".tmp")
            temp.write_text(json.dumps(self._cookies))
            os.chmod(temp, 0o600)
            os.replace(temp, self._cookie_file)
        except OSError as exc:
            logger.warning("Could not persist HDRezka cookies: %s", exc)

    async def _ensure_login(self) -> None:
        if not self.logged_in:
            await self.login()

    # ── public API ───────────────────────────────────────────────────────────

    async def search(self, query: str, page: int = 1) -> SearchPage:
        key = (query.strip().lower(), page)
        if (cached := self._searches.get(key)) is not None:
            return cached
        await self._ensure_login()
        html = await self._page(
            f"{self._origin}/search/",
            params={"do": "search", "subaction": "search", "q": query.strip(), "page": page},
        )
        items, has_next = parse.parse_search(html)
        result = SearchPage(items=items, page=page, has_next=has_next)
        self._searches.set(key, result)
        return result

    async def title(self, url: str) -> TitleDetails:
        normalized = self.normalize(url)
        if (cached := self._titles.get(normalized)) is not None:
            return cached
        await self._ensure_login()
        html = await self._page(normalized)
        try:
            details = parse.parse_title(html, normalized)
        except parse.ParseError as exc:
            raise RezkaError(str(exc)) from exc
        self._titles.set(normalized, details)
        return details

    async def episodes(self, title: TitleDetails, translator: Translator) -> dict[int, list[int]]:
        key = (title.id, translator.key)
        if (cached := self._episodes.get(key)) is not None:
            return cached
        payload = await self._ajax(
            "/ajax/get_cdn_series/",
            {"id": title.id, "translator_id": translator.id, "favs": title.favs or "", "action": "get_episodes"},
        )
        episodes = parse.parse_episodes(payload.get("episodes") or "")
        self._episodes.set(key, episodes)
        return episodes

    async def stream(
        self,
        title: TitleDetails,
        translator: Translator,
        season: int | None = None,
        episode: int | None = None,
    ) -> Stream:
        data: dict[str, Any] = {"id": title.id, "translator_id": translator.id, "favs": title.favs or ""}
        if title.is_series:
            if season is None or episode is None:
                raise ValueError("season and episode are required for series")
            data.update(season=season, episode=episode, action="get_stream")
        else:
            data.update(
                is_camrip=int(translator.camrip),
                is_ads=int(translator.ads),
                is_director=int(translator.director),
                action="get_movie",
            )
        payload = await self._ajax("/ajax/get_cdn_series/", data)
        try:
            return parse.parse_stream(payload)
        except parse.ParseError as exc:
            raise RezkaError(str(exc)) from exc
