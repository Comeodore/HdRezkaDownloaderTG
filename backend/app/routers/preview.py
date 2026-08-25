import asyncio
import re
import time

import aiohttp
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from HdRezkaApi import HdRezkaApi
from HdRezkaApi.types import TVSeries

from ..auth import require_token_user
from ..config import Settings, get_settings
from ..deps import get_gateway
from ..download.quality import preview_qualities
from ..logging_conf import get_logger
from ..rezka.session import RezkaGateway

logger = get_logger("preview")

router = APIRouter(prefix="/api", tags=["preview"])

_TTL = 900
_MIN_REAL_SIZE = 10 * 1024 * 1024  # below this the mirror is a broken placeholder
_PROBE_TIMEOUT = 6
_TAG_RE = re.compile(r"<[^>]*>")
_cache: dict[tuple[str, int], tuple[list[str], float]] = {}
_lock = asyncio.Lock()
_http: aiohttp.ClientSession | None = None


def _session() -> aiohttp.ClientSession:
    """Shared upstream session — connection reuse cuts seek latency a lot."""
    global _http
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, connect=15, sock_read=90),
            connector=aiohttp.TCPConnector(limit=32, ttl_dns_cache=600, keepalive_timeout=60),
        )
    return _http


async def close_http() -> None:
    global _http
    if _http is not None and not _http.closed:
        await _http.close()
    _http = None


def _cdn_ajax(api: HdRezkaApi, payload: dict) -> dict:
    response = requests.post(
        f"{api.origin}/ajax/get_cdn_series/",
        data={"id": api.id, **payload},
        headers=api.HEADERS,
        proxies=api.proxy,
        cookies=api.cookies,
        timeout=30,
    )
    return response.json()


def _first_episode(api: HdRezkaApi, translator_id: int) -> tuple[int, int]:
    """First available episode of one translator — a single ajax call.

    ``api.getStream`` for series walks every translator (one request each), which
    is far too slow for an interactive preview.
    """
    data = _cdn_ajax(api, {"translator_id": translator_id, "action": "get_episodes"})
    if not data.get("success"):
        raise HTTPException(404, "Нет эпизодов для этой озвучки")
    _, episodes = HdRezkaApi.getEpisodes(data["seasons"], data["episodes"])
    for season in sorted(episodes.keys(), key=int):
        season_episodes = episodes.get(season) or {}
        if season_episodes:
            return int(season), int(sorted(season_episodes.keys(), key=int)[0])
    raise HTTPException(404, "Нет эпизодов для этой озвучки")


def parse_videos(decoded: str) -> dict[str, list[str]]:
    """Parse the decoded stream string: ``[360p]url or url,[720p]url…``."""
    videos: dict[str, list[str]] = {}
    for chunk in decoded.split(","):
        if "[" not in chunk or "]" not in chunk:
            continue
        label, _, tail = chunk.partition("[")[2].partition("]")
        quality = _TAG_RE.sub("", label).strip()
        links = [link for link in tail.split(" or ") if link.endswith(".mp4")]
        if quality and links:
            videos.setdefault(quality, []).extend(links)
    return videos


def _series_videos(api: HdRezkaApi, translator_id: int) -> dict[str, list[str]]:
    season, episode = _first_episode(api, translator_id)
    data = _cdn_ajax(
        api,
        {"translator_id": translator_id, "season": season, "episode": episode, "action": "get_stream"},
    )
    if not (data.get("success") and data.get("url")):
        raise HTTPException(404, "Не удалось получить ссылки на видео")
    return parse_videos(HdRezkaApi.clearTrash(data["url"]))


def _total_size(response: aiohttp.ClientResponse) -> int:
    content_range = response.headers.get("content-range")
    if content_range and "/" in content_range:
        total = content_range.rsplit("/", 1)[-1]
        if total.isdigit():
            return int(total)
    if response.status == 200:
        length = response.headers.get("content-length")
        if length and length.isdigit():
            return int(length)
    return 0


async def _probe(settings: Settings, candidates: list[tuple[str, list[str]]]) -> list[str]:
    """Probe every mirror of every quality concurrently, pick cheapest real one."""
    headers = {"User-Agent": settings.user_agent, "Range": "bytes=0-0"}
    session = _session()

    async def measure(url: str) -> int:
        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=_PROBE_TIMEOUT)
            ) as response:
                return _total_size(response)
        except Exception:
            return 0

    flat = [url for _, urls in candidates for url in urls]
    results = await asyncio.gather(*(measure(url) for url in flat))
    sizes = dict(zip(flat, results))

    fallback: list[str] | None = None
    for quality, urls in candidates:  # already cheapest-first
        real = [url for url in urls if sizes.get(url, 0) >= _MIN_REAL_SIZE]
        if real:
            logger.info("Preview quality %s (%.0f MB)", quality, sizes[real[0]] / 1024 / 1024)
            return real + [url for url in urls if url not in real]
        working = [url for url in urls if sizes.get(url, 0) > 0]
        if working and fallback is None:
            fallback = working + [url for url in urls if url not in working]
    if fallback:
        return fallback
    raise HTTPException(502, "Зеркала видео недоступны")


async def _resolve(gateway: RezkaGateway, settings: Settings, url: str, translator_id: int) -> list[str]:
    key = (url, translator_id)
    cached = _cache.get(key)
    if cached and cached[1] > time.monotonic():
        return cached[0]

    async with _lock:
        cached = _cache.get(key)
        if cached and cached[1] > time.monotonic():
            return cached[0]

        api = await gateway.open_title(url)

        def videos() -> dict:
            if api.type == TVSeries:
                return _series_videos(api, translator_id)
            stream = api.getStream(translation=translator_id)
            return getattr(stream, "videos", None) or {}

        candidates = preview_qualities(await asyncio.to_thread(videos))
        if not candidates:
            raise HTTPException(404, "Не удалось получить ссылки на видео")

        urls = await _probe(settings, candidates)
        now = time.monotonic()
        _cache[key] = (urls, now + _TTL)
        for stale in [k for k, (_, expires) in _cache.items() if expires <= now]:
            _cache.pop(stale, None)
        return urls


@router.get("/preview/stream")
async def preview_stream(
    request: Request,
    url: str = Query(min_length=1),
    translator_id: int = Query(...),
    _uid: int = Depends(require_token_user),
    gateway: RezkaGateway = Depends(get_gateway),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    mirrors = await _resolve(gateway, settings, url, translator_id)

    headers = {"User-Agent": settings.user_agent}
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    session = _session()
    upstream: aiohttp.ClientResponse | None = None
    for mirror in mirrors:
        try:
            response = await session.get(mirror, headers=headers)
        except aiohttp.ClientError:
            continue
        if response.status in (200, 206):
            upstream = response
            break
        response.close()
    if upstream is None:
        raise HTTPException(502, "Не удалось получить видео")

    passthrough = {
        name: upstream.headers[name]
        for name in ("Content-Length", "Content-Range", "Content-Type")
        if name in upstream.headers
    }
    passthrough.setdefault("Content-Type", "video/mp4")
    passthrough["Accept-Ranges"] = "bytes"
    passthrough["Cache-Control"] = "no-store"

    async def body():
        try:
            async for chunk in upstream.content.iter_chunked(settings.chunk_size):
                yield chunk
        finally:
            upstream.close()

    return StreamingResponse(body(), status_code=upstream.status, headers=passthrough)
