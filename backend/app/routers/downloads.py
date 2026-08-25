import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import issue_session_token, require_token_user, require_user
from ..config import Settings, get_settings
from ..deps import get_manager
from ..download.manager import DownloadManager

router = APIRouter(prefix="/api", tags=["downloads"])


class CreateDownload(BaseModel):
    url: str
    translator_id: int
    poster: str | None = None
    seasons: list[int] = []


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/session")
async def session(
    user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    token = issue_session_token(int(user["id"]), settings)
    return {
        "token": token,
        "user": {
            "id": user.get("id"),
            "first_name": user.get("first_name"),
            "username": user.get("username"),
        },
    }


@router.post("/downloads")
async def create_download(
    body: CreateDownload,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    job = await manager.create(body.url, body.translator_id, poster=body.poster, seasons=body.seasons)
    return {"job": job.snapshot()}


@router.get("/downloads")
async def list_downloads(
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    return {"jobs": [job.snapshot() for job in manager.list_jobs()]}


@router.delete("/downloads")
async def clear_downloads(
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    return {"jobs": [job.snapshot() for job in manager.clear_finished()]}


@router.get("/downloads/events")
async def download_events(
    _uid: int = Depends(require_token_user),
    manager: DownloadManager = Depends(get_manager),
) -> StreamingResponse:
    async def stream():
        queue = manager.hub.subscribe()
        try:
            yield _sse({"type": "snapshot", "jobs": [job.snapshot() for job in manager.list_jobs()]})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield _sse(event)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            manager.hub.unsubscribe(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/downloads/{job_id}/pause")
async def pause_download(
    job_id: str,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    if not await manager.pause(job_id):
        raise HTTPException(409, "Cannot pause")
    return {"ok": True}


@router.post("/downloads/{job_id}/resume")
async def resume_download(
    job_id: str,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    job = await manager.resume(job_id)
    if job is None:
        raise HTTPException(409, "Cannot resume")
    return {"job": job.snapshot()}


@router.delete("/downloads/{job_id}")
async def cancel_download(
    job_id: str,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    if not await manager.cancel(job_id):
        raise HTTPException(404, "Job not found")
    return {"ok": True}


@router.post("/downloads/{job_id}/retry")
async def retry_download(
    job_id: str,
    _user: dict = Depends(require_user),
    manager: DownloadManager = Depends(get_manager),
) -> dict:
    job = await manager.retry(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return {"job": job.snapshot()}
