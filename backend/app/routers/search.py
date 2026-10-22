import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_user
from ..config import Settings, get_settings
from ..deps import get_client, get_resolver
from ..library.service import disk_usage, local_state
from ..rezka.client import RezkaClient
from ..rezka.models import TitleDetails, Translator
from ..streams import PremiumOnly, StreamResolver
from .media import image_url

router = APIRouter(prefix="/api", tags=["catalog"])


async def _title_and_voice(client: RezkaClient, url: str, translator: str) -> tuple[TitleDetails, Translator]:
    title = await client.title(url)
    voice = title.translator(translator)
    if voice is None:
        raise HTTPException(404, "Озвучка не найдена")
    return title, voice


@router.get("/search")
async def search(
    q: str = Query(min_length=1, max_length=120),
    page: int = Query(default=1, ge=1, le=50),
    _user: dict = Depends(require_user),
    client: RezkaClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = await client.search(q, page)
    items = [{**item.model_dump(), "poster": image_url(item.poster, settings)} for item in result.items]
    return {"items": items, "page": result.page, "has_next": result.has_next}


@router.get("/title")
async def title(
    url: str = Query(min_length=1),
    _user: dict = Depends(require_user),
    client: RezkaClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    details = await client.title(url)
    local = await asyncio.to_thread(local_state, settings, details.name, details.year, details.is_series)
    data = details.model_dump(exclude={"favs"})
    data["poster"] = image_url(details.poster, settings)
    data["poster_hq"] = image_url(details.poster_hq, settings)
    data["local"] = local
    data["disk_free"] = (await asyncio.to_thread(disk_usage, settings))["free"]
    return data


@router.get("/episodes")
async def episodes(
    url: str = Query(min_length=1),
    translator: str = Query(min_length=1),
    _user: dict = Depends(require_user),
    client: RezkaClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    details, voice = await _title_and_voice(client, url, translator)
    if not details.is_series:
        return {"seasons": []}
    available = await client.episodes(details, voice)
    local = await asyncio.to_thread(local_state, settings, details.name, details.year, True)
    return {
        "seasons": [
            {"number": number, "episodes": len(items), "local": local["episodes"].get(number, 0)}
            for number, items in available.items()
        ]
    }


@router.get("/qualities")
async def qualities(
    url: str = Query(min_length=1),
    translator: str = Query(min_length=1),
    _user: dict = Depends(require_user),
    client: RezkaClient = Depends(get_client),
    resolver: StreamResolver = Depends(get_resolver),
) -> dict:
    """Available qualities with measured sizes (per episode for series)."""
    details, voice = await _title_and_voice(client, url, translator)
    try:
        probed = await resolver.resolve(details, voice)
    except PremiumOnly as exc:
        return {"items": [], "premium_only": exc.message}
    return {"items": [{"label": p.label, "height": p.height, "size": p.size} for p in probed], "premium_only": None}
