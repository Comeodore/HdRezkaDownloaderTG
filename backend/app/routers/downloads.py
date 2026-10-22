import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth import issue_session_token, require_token_user, require_user
from ..config import Settings, get_settings
from ..deps import get_manager
from ..download.manager import DownloadManager
from ..download.progress import Job
from ..download.quality import QUALITY_CHOICES
from .media import image_url

router = APIRouter(prefix="/api", tags=["downloads"])

_PRIVATE_FIELDS = ("owner_id", "translator_key")


class CreateDownload(BaseModel):
    url: str = Field(min_length=1)
    translator: str = Field(min_length=1)
    seasons: list[int] = []
    max_height: int = 1080


def job_view(job: Job, settings: Settings) -> dict:
    data = job.to_dict()
    for name in _PRIVATE_FIELDS:
        data.pop(name, None)
    data["percent"] = round(job.percent, 1)
    data["eta"] = job.eta
    data["poster"] = image_url(job.poster, settings)
    data["speed"] = round(job.speed)
    return data


def _event(payload: dict, settings: Settings) -> str:
    if payload.get("type") == "job":
        payload = {"type": "job", "job": job_view(payload["job"], settings)}
    elif payload.get("type") == "snapshot":
        payload = {"type": "snapshot", "jobs": [job_view(job, settings) for job in payload["jobs"]]}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/session")
async def session(user: dict = Depends(require_user), settings: Settings = Depends(get_settings)) -> dict:
    return {
        "token": issue_session_token(int(user["id"]), settings),
        "user": {"id": user.get("id"), "first_name": user.get("first_name"), "username": user.get("username")},
    }


@router.post("/downloads")
async def create_download(
    body: CreateDownload,
    user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
    settings: Settings = Depends(get_settings),
) -> dict:
    if body.max_height not in QUALITY_CHOICES:
        raise HTTPException(422, "Неподдерживаемое качество")
    job = await manager.create(body.url, body.translator, body.seasons, body.max_height, int(user["id"]))
    return {"job": job_view(job, settings)}


@router.get("/downloads")
async def list_downloads(
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {"jobs": [job_view(job, settings) for job in manager.list_jobs()]}


@router.delete("/downloads")
async def clear_downloads(
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
    settings: Settings = Depends(get_settings),
) -> dict:
    manager.clear_finished()
    return {"jobs": [job_view(job, settings) for job in manager.list_jobs()]}


@router.get("/downloads/events")
async def download_events(
    _uid: int = Depends(require_token_user),
    manager: DownloadManager = Depends(get_manager),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    async def stream():
        queue = manager.hub.subscribe()
        try:
            yield "retry: 3000\n\n"
            yield _event({"type": "snapshot", "jobs": manager.list_jobs()}, settings)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield _event(event, settings)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            manager.hub.unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def _job_or_404(manager: DownloadManager, job_id: str) -> Job:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Загрузка не найдена")
    return job


@router.post("/downloads/{job_id}/pause")
async def pause_download(
    job_id: str,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    _job_or_404(manager, job_id)
    if not manager.pause(job_id):
        raise HTTPException(409, "Эту загрузку нельзя поставить на паузу")
    return {"ok": True}


@router.post("/downloads/{job_id}/resume")
async def resume_download(
    job_id: str,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
    settings: Settings = Depends(get_settings),
) -> dict:
    _job_or_404(manager, job_id)
    job = manager.resume(job_id)
    if job is None:
        raise HTTPException(409, "Эту загрузку нельзя продолжить")
    return {"job": job_view(job, settings)}


@router.post("/downloads/{job_id}/cancel")
async def cancel_download(
    job_id: str,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    _job_or_404(manager, job_id)
    if not manager.cancel(job_id):
        raise HTTPException(409, "Загрузка уже завершена")
    return {"ok": True}


@router.post("/downloads/{job_id}/retry")
async def retry_download(
    job_id: str,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
    settings: Settings = Depends(get_settings),
) -> dict:
    _job_or_404(manager, job_id)
    job = manager.retry(job_id)
    if job is None:
        raise HTTPException(409, "Эту загрузку нельзя повторить")
    return {"job": job_view(job, settings)}


@router.delete("/downloads/{job_id}")
async def remove_download(
    job_id: str,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    _job_or_404(manager, job_id)
    if not manager.remove(job_id):
        raise HTTPException(409, "Сначала отмените загрузку")
    return {"ok": True}
