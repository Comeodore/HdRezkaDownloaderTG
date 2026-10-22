import asyncio

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_user
from ..config import Settings, get_settings
from ..deps import get_enricher, get_manager, get_meta
from ..download.manager import DownloadManager
from ..library import service
from ..library.service import LibraryEnricher, LibraryMeta
from ..logging_conf import get_logger
from .media import image_url

router = APIRouter(prefix="/api/library", tags=["library"])
logger = get_logger("library")


@router.get("")
async def list_library(
    _user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
    meta: LibraryMeta = Depends(get_meta),
    manager: DownloadManager = Depends(get_manager),
    enricher: LibraryEnricher = Depends(get_enricher),
) -> dict:
    items, disk = await asyncio.gather(
        asyncio.to_thread(service.list_items, settings, meta),
        asyncio.to_thread(service.disk_usage, settings),
    )
    busy = manager.busy_targets()
    enriching = enricher.schedule(items)
    for item in items:
        item["poster"] = image_url(item.get("poster"), settings)
        item["downloading"] = item["entry"] in busy
    return {"items": items, "disk": disk, "enriching": enriching}


@router.delete("/{item_id}")
async def delete_library_item(
    item_id: str,
    user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
    meta: LibraryMeta = Depends(get_meta),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    entry = await asyncio.to_thread(service.find_entry, settings, item_id)
    if entry is None:
        raise HTTPException(404, "Не найдено")
    if entry.name in manager.busy_targets():
        raise HTTPException(409, "Сейчас идёт загрузка в эту папку — сначала отмените её")
    try:
        await asyncio.to_thread(service.delete_entry, entry)
    except OSError as exc:
        raise HTTPException(500, f"Не удалось удалить: {exc.strerror or exc}") from exc
    meta.forget(entry.name)
    logger.info("User %s deleted %s", user.get("id"), entry.name)
    return {"ok": True}
