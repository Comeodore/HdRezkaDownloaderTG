from fastapi import APIRouter, Depends, Query

from ..auth import require_user
from ..deps import get_gateway
from ..rezka.session import RezkaGateway

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(min_length=1),
    _user: dict = Depends(require_user),
    gateway: RezkaGateway = Depends(get_gateway),
) -> dict:
    items = await gateway.search(q.strip())
    return {"results": [item.model_dump() for item in items]}


@router.get("/title")
async def title(
    url: str = Query(min_length=1),
    _user: dict = Depends(require_user),
    gateway: RezkaGateway = Depends(get_gateway),
) -> dict:
    details = await gateway.details(url)
    return details.model_dump()


@router.get("/seasons")
async def seasons(
    url: str = Query(min_length=1),
    translator_id: int = Query(...),
    _user: dict = Depends(require_user),
    gateway: RezkaGateway = Depends(get_gateway),
) -> dict:
    items = await gateway.seasons(url, translator_id)
    return {"seasons": [item.model_dump() for item in items]}
