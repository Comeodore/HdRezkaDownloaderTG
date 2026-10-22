import base64
import binascii
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..auth import sign_media, verify_media
from ..config import Settings, get_settings
from ..ttl_cache import TTLCache

router = APIRouter(prefix="/api", tags=["media"])

_MAX_BYTES = 4 * 1024 * 1024
_cache: TTLCache[str, tuple[bytes, str]] = TTLCache(ttl=6 * 3600, max_size=400)


def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _unb64(value: str) -> str:
    try:
        return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode()).decode()
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise HTTPException(400, "Bad url") from exc


def is_allowed_image_host(url: str) -> bool:
    """HDRezka's own domains only (rezka.fi, statichdrezka.ac, static.hdrezka.ac, …).

    Proxy URLs are HMAC-signed anyway; this is defence in depth against
    signing something that did not come from an HDRezka page.
    """
    parsed = urlparse(url)
    domain = ".".join((parsed.hostname or "").lower().split(".")[-2:])
    return parsed.scheme in ("http", "https") and "rezka" in domain


def image_url(remote: str | None, settings: Settings) -> str | None:
    """Stable, signed proxy URL for a poster — cacheable by the WebView and Cloudflare."""
    if not remote or not is_allowed_image_host(remote):
        return None
    return f"/api/img/{sign_media(remote, settings)}/{_b64(remote)}.jpg"


@router.get("/img/{signature}/{payload}.jpg")
async def image(
    signature: str,
    payload: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    target = _unb64(payload)
    if not verify_media(target, signature, settings) or not is_allowed_image_host(target):
        raise HTTPException(403, "Bad signature")

    headers = {"Cache-Control": "public, max-age=2592000, immutable"}
    if (cached := _cache.get(target)) is not None:
        return Response(content=cached[0], media_type=cached[1], headers=headers)

    http: aiohttp.ClientSession = request.app.state.resolver.http
    try:
        async with http.get(target, timeout=aiohttp.ClientTimeout(total=15)) as response:
            content_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0]
            if response.status != 200 or not content_type.startswith("image/"):
                raise HTTPException(502, "Upstream error")
            if (response.content_length or 0) > _MAX_BYTES:
                raise HTTPException(502, "Image too large")
            # StreamReader.read(n) may return a partial buffer — collect until EOF
            body = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                body.extend(chunk)
                if len(body) > _MAX_BYTES:
                    raise HTTPException(502, "Image too large")
            content = bytes(body)
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise HTTPException(502, "Fetch failed") from exc
    if response.content_length is not None and len(content) != response.content_length:
        raise HTTPException(502, "Truncated image")
    _cache.set(target, (content, content_type))
    return Response(content=content, media_type=content_type, headers=headers)
