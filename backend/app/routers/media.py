import base64
import binascii
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..auth import require_token_user
from ..config import Settings, get_settings

router = APIRouter(prefix="/api", tags=["media"])


def _decode(encoded: str) -> str:
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise HTTPException(400, "Bad url") from exc


def _is_allowed(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.netloc.lower()
    return "rezka" in host or "hdrezka" in host


@router.get("/image")
async def image(
    u: str = Query(min_length=1),
    _uid: int = Depends(require_token_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    target = _decode(u)
    if not _is_allowed(target):
        raise HTTPException(400, "Host not allowed")

    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": settings.user_agent}) as http:
            async with http.get(target) as response:
                if response.status != 200:
                    raise HTTPException(502, "Upstream error")
                content = await response.read()
                content_type = response.headers.get("content-type", "image/jpeg")
    except aiohttp.ClientError as exc:
        raise HTTPException(502, "Fetch failed") from exc

    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=604800"},
    )
