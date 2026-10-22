import asyncio
from dataclasses import dataclass

import aiohttp

from ..rezka.models import Quality

# Below this a mirror is serving HDRezka's placeholder clip (≈7.6 MB) or a broken file.
MIN_REAL_SIZE = 10 * 1024 * 1024
QUALITY_CHOICES = (1080, 720, 480, 360)


@dataclass
class Probed:
    label: str
    height: int
    size: int
    urls: list[str]


def total_size(response: aiohttp.ClientResponse) -> int:
    content_range = response.headers.get("Content-Range", "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[-1]
        if total.isdigit():
            return int(total)
    if response.status == 200:
        length = response.headers.get("Content-Length", "")
        if length.isdigit():
            return int(length)
    return 0


async def probe(http: aiohttp.ClientSession, qualities: list[Quality], user_agent: str) -> list[Probed]:
    """Find a working mirror for every non-premium quality, all in parallel.

    Each quality settles as soon as its first mirror answers with a real
    file, so one dead mirror cannot stall the whole lookup. Returns
    qualities best first, the confirmed mirror leading its list.
    """
    headers = {"User-Agent": user_agent, "Range": "bytes=0-0"}
    timeout = aiohttp.ClientTimeout(total=8, connect=5)

    async def measure(url: str) -> tuple[str, int]:
        try:
            async with http.get(url, headers=headers, timeout=timeout) as response:
                return url, total_size(response) if response.status in (200, 206) else 0
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return url, 0

    async def first_working(quality: Quality) -> Probed | None:
        pending = {asyncio.ensure_future(measure(url)) for url in quality.urls}
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    url, size = task.result()
                    if size >= MIN_REAL_SIZE:
                        urls = [url] + [other for other in quality.urls if other != url]
                        return Probed(label=quality.label, height=quality.height, size=size, urls=urls)
            return None
        finally:
            for task in pending:
                task.cancel()

    usable = [q for q in qualities if not q.premium and q.height]
    result = [p for p in await asyncio.gather(*(first_working(q) for q in usable)) if p is not None]
    result.sort(key=lambda p: p.height, reverse=True)
    return result


def pick_best(probed: list[Probed], max_height: int) -> Probed | None:
    """Highest allowed quality that is a genuine file.

    A higher label whose file is smaller than a lower one is a broken encode
    on the CDN — skip it in favour of the lower label.
    """
    allowed = [p for p in probed if p.height <= max_height] or probed[-1:]
    for index, candidate in enumerate(allowed):
        lower = allowed[index + 1 :]
        if all(candidate.size >= other.size * 0.9 for other in lower):
            return candidate
    return allowed[0] if allowed else None


def pick_cheapest(probed: list[Probed]) -> Probed | None:
    return min(probed, key=lambda p: p.height) if probed else None
