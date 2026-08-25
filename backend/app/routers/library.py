from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_user
from ..config import Settings, get_settings
from ..library import service

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("")
async def list_library(
    _user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {"items": service.list_items(settings)}


@router.delete("/{item_id}")
async def delete_library_item(
    item_id: str,
    _user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not service.delete_item(settings, item_id):
        raise HTTPException(404, "Not found")
    return {"ok": True}
