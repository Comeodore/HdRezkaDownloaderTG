import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..auth import require_token_user
from ..config import Settings, get_settings
from ..deps import get_client, get_resolver
from ..download.quality import pick_cheapest
from ..logging_conf import get_logger
from ..rezka.client import RezkaClient
from ..streams import StreamResolver

logger = get_logger("preview")

router = APIRouter(prefix="/api", tags=["preview"])

_PASSTHROUGH = ("Content-Length", "Content-Range", "Content-Type")


@router.get("/preview")
async def preview(
    request: Request,
    url: str = Query(min_length=1),
    translator: str = Query(min_length=1),
    _uid: int = Depends(require_token_user),
    client: RezkaClient = Depends(get_client),
    resolver: StreamResolver = Depends(get_resolver),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Range-aware proxy of the cheapest real quality — the WebView can seek freely."""
    title = await client.title(url)
    voice = title.translator(translator)
    if voice is None:
        raise HTTPException(404, "Озвучка не найдена")
    choice = pick_cheapest(await resolver.resolve(title, voice))
    if choice is None:
        resolver.forget(title, voice)
        raise HTTPException(502, "Зеркала видео недоступны")

    headers = {"User-Agent": settings.user_agent}
    if range_header := request.headers.get("range"):
        headers["Range"] = range_header

    upstream: aiohttp.ClientResponse | None = None
    for mirror in choice.urls:
        try:
            response = await resolver.http.get(mirror, headers=headers)
        except (aiohttp.ClientError, TimeoutError):
            continue
        if response.status in (200, 206):
            upstream = response
            break
        response.close()
    if upstream is None:
        resolver.forget(title, voice)  # links may have expired — re-resolve next time
        raise HTTPException(502, "Не удалось получить видео")

    passthrough = {name: upstream.headers[name] for name in _PASSTHROUGH if name in upstream.headers}
    passthrough.setdefault("Content-Type", "video/mp4")
    passthrough["Accept-Ranges"] = "bytes"
    passthrough["Cache-Control"] = "no-store"

    async def body():
        try:
            async for chunk in upstream.content.iter_chunked(256 * 1024):
                yield chunk
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.debug("Preview upstream closed: %s", exc)
        finally:
            upstream.close()

    return StreamingResponse(body(), status_code=upstream.status, headers=passthrough)
