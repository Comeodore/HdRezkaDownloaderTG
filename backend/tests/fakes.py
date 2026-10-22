"""A fake HDRezka (catalog + CDN) for engine and API tests."""
import asyncio
import os
from dataclasses import dataclass, field

from aiohttp import web

from app.rezka.client import RezkaError
from app.rezka.models import Quality, SearchItem, SearchPage, Stream, TitleDetails, Translator

MOVIE_URL = "https://rezka.fi/films/fiction/981-matrica-1999-latest.html"
SERIES_URL = "https://rezka.fi/series/comedy/1733-druzya-1994-latest.html"


@dataclass
class Cdn:
    """In-process CDN: byte payloads per path with switchable misbehaviour."""

    files: dict[str, bytes] = field(default_factory=dict)
    broken: set[str] = field(default_factory=set)  # always 500
    ignore_range: set[str] = field(default_factory=set)  # answer 200 with the full body
    cut_after: dict[str, int] = field(default_factory=dict)  # drop the connection after N bytes once
    stall_after: dict[str, int] = field(default_factory=dict)  # send N bytes, then hang
    hits: list[tuple[str, str | None]] = field(default_factory=list)
    base: str = ""

    def add(self, path: str, size: int) -> bytes:
        self.files[path] = os.urandom(size)
        return self.files[path]

    def url(self, path: str) -> str:
        return f"{self.base}/{path}"

    async def handle(self, request: web.Request) -> web.StreamResponse:
        path = request.match_info["path"]
        range_header = request.headers.get("Range")
        self.hits.append((path, range_header))
        if path in self.broken or path not in self.files:
            return web.Response(status=500)
        body = self.files[path]
        start, end = 0, len(body) - 1
        status = 200
        if range_header and path not in self.ignore_range:
            first, _, last = range_header.removeprefix("bytes=").partition("-")
            start = int(first)
            end = int(last) if last else end
            if start >= len(body):
                return web.Response(status=416, headers={"Content-Range": f"bytes */{len(body)}"})
            status = 206
        chunk = body[start : end + 1]
        content_type = "image/jpeg" if path.endswith(".jpg") else "video/mp4"
        headers = {"Content-Type": content_type, "Accept-Ranges": "bytes"}
        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{len(body)}"
        response = web.StreamResponse(status=status, headers=headers)
        response.content_length = len(chunk)
        await response.prepare(request)
        stall = self.stall_after.get(path) if range_header != "bytes=0-0" else None
        if stall is not None:
            await response.write(chunk[:stall])
            await asyncio.sleep(3600)  # a mirror that stops sending mid-file
        limit = self.cut_after.pop(path, None) if range_header != "bytes=0-0" else None
        if limit is not None:
            await response.write(chunk[:limit])
            await asyncio.sleep(0.2)  # let the client consume what was sent before the drop
            request.transport.close()
            return response
        await response.write(chunk)
        await response.write_eof()
        return response


def cdn_app(cdn: Cdn) -> web.Application:
    app = web.Application()
    app.router.add_get("/{path:.+}", cdn.handle)
    return app


def movie_title(**overrides) -> TitleDetails:
    data = dict(
        id=981,
        url=MOVIE_URL,
        name="Матрица",
        kind="movie",
        is_series=False,
        year=1999,
        poster="https://statichdrezka.ac/i/poster.jpg",
        translators=[
            Translator(key="56", id=56, name="Дубляж"),
            Translator(key="80-dir", id=80, name="Гоблин (реж. версия)", director=True),
        ],
        default_translator="56",
    )
    data.update(overrides)
    return TitleDetails(**data)


def series_title() -> TitleDetails:
    return TitleDetails(
        id=1733,
        url=SERIES_URL,
        name="Друзья",
        kind="series",
        is_series=True,
        year=1994,
        translators=[Translator(key="84", id=84, name="СТС")],
        default_translator="84",
    )


class FakeClient:
    def __init__(self, cdn: Cdn | None = None) -> None:
        self.cdn = cdn
        self.titles = {MOVIE_URL: movie_title(), SERIES_URL: series_title()}
        self.episode_map = {1: [1, 2], 2: [1, 2]}
        self.streams: dict[tuple, list[Quality]] = {}
        self.stream_calls: list[tuple] = []
        self.logged_in = True

    def set_stream(self, key: tuple, qualities: dict[str, list[str]], premium: set[str] = frozenset()) -> None:
        from app.rezka.parse import quality_height

        self.streams[key] = [
            Quality(label=label, height=quality_height(label), premium=label in premium, urls=urls)
            for label, urls in qualities.items()
        ]

    async def search(self, query: str, page: int = 1) -> SearchPage:
        return SearchPage(
            items=[SearchItem(url=MOVIE_URL, title="Матрица", kind="movie", year="1999",
                              poster="https://statichdrezka.ac/i/poster.jpg")],
            page=page,
            has_next=page < 2,
        )

    async def title(self, url: str) -> TitleDetails:
        if url not in self.titles:
            raise RezkaError("not found")
        return self.titles[url]

    async def episodes(self, title: TitleDetails, translator: Translator) -> dict[int, list[int]]:
        return self.episode_map

    async def stream(self, title, translator, season=None, episode=None) -> Stream:
        key = (title.id, translator.key, season, episode)
        self.stream_calls.append(key)
        qualities = self.streams.get(key) or self.streams.get((title.id, translator.key, None, None))
        if qualities is None:
            raise RezkaError("no stream")
        from app.rezka.parse import is_gated

        return Stream(qualities=qualities, gated=is_gated(qualities))
