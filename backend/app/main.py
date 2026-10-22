import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .download.engine import JobFailed
from .download.manager import DownloadConflict, DownloadManager
from .heartbeat import heartbeat_task
from .library.service import LibraryEnricher, LibraryMeta
from .logging_conf import configure_logging, get_logger
from .notify import Notifier
from .rezka.client import RezkaClient, RezkaError
from .routers import downloads, library, media, preview, search
from .streams import StreamResolver

logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(logging.INFO)
    if settings.dev_fake_user_id:
        logger.warning("DEV_FAKE_USER_ID=%s — requests without Telegram auth are accepted!", settings.dev_fake_user_id)

    client = RezkaClient(settings)
    resolver = StreamResolver(settings, client)
    meta = LibraryMeta(settings)
    manager = DownloadManager(settings, client, meta, Notifier(settings))
    await client.start()
    await resolver.start()
    await manager.start()
    app.state.client, app.state.resolver, app.state.meta, app.state.manager = client, resolver, meta, manager
    app.state.enricher = LibraryEnricher(meta, client)

    heartbeat = None
    if os.environ.get("HEARTBEAT_URL"):
        heartbeat = asyncio.create_task(heartbeat_task(service_id=os.environ.get("HEARTBEAT_ID", "rezka-backend")))

    logger.info("Backend ready (media=%s, allowlist=%s)", settings.media_dir, sorted(settings.allowed_ids) or "open")
    try:
        yield
    finally:
        if heartbeat:
            heartbeat.cancel()
        await manager.close()
        await resolver.close()
        await client.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Rezka Mini App", version="2.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.exception_handler(RezkaError)
    async def rezka_error(_request: Request, exc: RezkaError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    @app.exception_handler(JobFailed)
    async def job_failed(_request: Request, exc: JobFailed) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=400)

    @app.exception_handler(DownloadConflict)
    async def conflict(_request: Request, exc: DownloadConflict) -> JSONResponse:
        return JSONResponse({"detail": exc.message, "job_id": exc.job.id}, status_code=409)

    @app.get("/api/health", include_in_schema=False)
    async def health(request: Request) -> dict:
        state = request.app.state
        return {"ok": True, "rezka_session": state.client.logged_in, "active_downloads": state.manager.active_count()}

    for module in (search, downloads, library, media, preview):
        app.include_router(module.router)
    _mount_frontend(app, settings)
    return app


class HashedStaticFiles(StaticFiles):
    """Vite emits content-hashed filenames — cache them forever."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    static_dir = Path(settings.frontend_dir).resolve()
    index_file = static_dir / "index.html"
    if not index_file.is_file():
        logger.warning("Frontend dir %s not found — serving API only", static_dir)
        return

    if (static_dir / "assets").is_dir():
        app.mount("/assets", HashedStaticFiles(directory=static_dir / "assets"), name="assets")

    # no-cache = revalidate on every load, so Cloudflare and the Telegram
    # WebView pick up a new index.html right after a deploy.
    revalidate = {"Cache-Control": "no-cache"}

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (static_dir / full_path).resolve()
        # resolve() + is_relative_to() blocks `..%2F` traversal out of the static dir
        if full_path and candidate.is_relative_to(static_dir) and candidate.is_file():
            return FileResponse(candidate, headers=revalidate)
        return FileResponse(index_file, headers=revalidate)


app = create_app()
