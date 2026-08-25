import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .download.manager import DownloadManager
from .heartbeat import heartbeat_task
from .logging_conf import configure_logging, get_logger
from .rezka.session import RezkaGateway
from .routers import downloads, library, media, preview, search

logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(logging.INFO)
    app.state.settings = settings
    app.state.gateway = RezkaGateway(settings)
    app.state.manager = DownloadManager(settings, app.state.gateway)

    heartbeat = None
    if os.environ.get("HEARTBEAT_URL"):
        heartbeat = asyncio.create_task(heartbeat_task(service_id=os.environ.get("HEARTBEAT_ID", "rezka-backend")))

    logger.info("Backend ready (media=%s, allowlist=%s)", settings.media_dir, sorted(settings.allowed_ids) or "open")
    try:
        yield
    finally:
        if heartbeat:
            heartbeat.cancel()
        await app.state.manager.close()
        await preview.close_http()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Rezka Mini App", version="1.0.0", lifespan=lifespan)
    app.include_router(search.router)
    app.include_router(downloads.router)
    app.include_router(library.router)
    app.include_router(media.router)
    app.include_router(preview.router)
    _mount_frontend(app, settings)
    return app


class HashedStaticFiles(StaticFiles):
    """Vite emits content-hashed filenames — cache them forever."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    static_dir = Path(settings.frontend_dir)
    if not static_dir.is_dir():
        logger.warning("Frontend dir %s not found — serving API only", static_dir)
        return

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", HashedStaticFiles(directory=assets_dir), name="assets")

    index_file = static_dir / "index.html"
    # no-cache = revalidate with the origin on every load, so Cloudflare and the
    # Telegram WebView pick up a new index.html right after a deploy.
    revalidate = {"Cache-Control": "no-cache"}

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate, headers=revalidate)
        return FileResponse(index_file, headers=revalidate)


app = create_app()
