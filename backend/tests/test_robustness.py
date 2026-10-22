"""Regression tests for races and failure modes found in review of the v2 rewrite."""
import asyncio
import json
import time
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.auth import verify_media, verify_session_token
from app.config import Settings, get_settings
from app.download.engine import Control, DownloadEngine, Interrupted, JobFailed
from app.download.manager import DownloadConflict
from app.download.paths import episode_path, part_path, passport_path, series_dir
from app.download.progress import JobStatus
from app.library.service import delete_entry
from app.rezka.client import RezkaAuthError, RezkaClient
from tests.fakes import MOVIE_URL, SERIES_URL, FakeClient
from tests.test_downloads import (  # noqa: F401 — fixtures
    SIZE,
    cdn,
    http,
    make_manager,
    movie_job,
    settings,
    small_files,
    wait_for,
)


async def test_retry_refuses_to_run_next_to_an_active_job(settings, cdn, monkeypatch):
    gate = asyncio.Event()

    async def blocked(self, job, control):
        await gate.wait()
        return JobStatus.SUCCESS

    monkeypatch.setattr(DownloadEngine, "run", blocked)
    manager = await make_manager(settings, FakeClient(cdn))
    failed = movie_job(id="old", status=JobStatus.ERROR, error="boom")
    manager._jobs[failed.id] = failed
    await manager.create(MOVIE_URL, "56", [], 1080, owner_id=1)  # allowed: the old one is finished
    with pytest.raises(DownloadConflict):
        manager.retry("old")
    gate.set()
    await manager.close()


async def test_cancelling_one_season_keeps_parts_of_another_running_job(settings, cdn, monkeypatch):
    settings.download_concurrency = 1
    gate = asyncio.Event()
    parts: list[Path] = []

    async def writes_a_part(self, job, control):
        destination = episode_path(series_dir(settings, job.name, job.year), job.seasons[0], 1)
        destination.parent.mkdir(parents=True, exist_ok=True)
        part_path(destination).write_bytes(b"x" * 1000)
        parts.append(part_path(destination))
        await gate.wait()
        return JobStatus.SUCCESS

    monkeypatch.setattr(DownloadEngine, "run", writes_a_part)
    manager = await make_manager(settings, FakeClient(cdn))
    await manager.create(SERIES_URL, "84", [1], 1080, owner_id=1)
    await wait_for(lambda: parts)
    queued = await manager.create(SERIES_URL, "84", [2], 1080, owner_id=1)
    assert manager.cancel(queued.id)
    await wait_for(lambda: queued.status == JobStatus.CANCELLED)
    assert parts[0].exists()
    gate.set()
    await manager.close()


async def test_brief_probe_outage_keeps_the_part_file(settings, cdn, http):
    cdn.add("1080.mp4", SIZE)
    cdn.add("720.mp4", SIZE // 2)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("1080.mp4")], "720p": [cdn.url("720.mp4")]})
    destination = Path(settings.media_dir) / "Матрица (1999).mp4"
    part_path(destination).write_bytes(cdn.files["1080.mp4"][: SIZE // 2])
    passport_path(destination).write_text(json.dumps({"label": "1080p", "size": SIZE}))
    cdn.broken.add("1080.mp4")

    engine = DownloadEngine(settings, http, client, lambda job: None)
    with pytest.raises(JobFailed, match="1080p"):
        await engine.run(movie_job(), Control())
    assert part_path(destination).exists() and passport_path(destination).exists()

    cdn.broken.discard("1080.mp4")  # mirror is back: the same encode is resumed, not restarted
    job = movie_job()
    assert await engine.run(job, Control()) == JobStatus.SUCCESS
    assert destination.read_bytes() == cdn.files["1080.mp4"] and job.quality == "1080p"
    assert ("1080.mp4", f"bytes={SIZE // 2}-") in cdn.hits


async def test_pause_interrupts_a_stalled_read_immediately(settings, cdn, http):
    cdn.add("m.mp4", SIZE)
    cdn.stall_after["m.mp4"] = 20_000
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    job, control = movie_job(), Control()
    task = asyncio.create_task(DownloadEngine(settings, http, client, lambda j: None).run(job, control))
    await wait_for(lambda: job.downloaded >= 20_000)
    started = time.monotonic()
    control.stop("pause")
    with pytest.raises(Interrupted):
        await asyncio.wait_for(task, timeout=2)
    assert time.monotonic() - started < 1


async def test_one_mirror_ignoring_range_does_not_restart_the_file(settings, cdn, http):
    body = cdn.add("a.mp4", SIZE)
    cdn.files["b.mp4"] = body
    cdn.ignore_range.add("a.mp4")
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("a.mp4"), cdn.url("b.mp4")]})
    destination = Path(settings.media_dir) / "Матрица (1999).mp4"
    part_path(destination).write_bytes(body[:150_000])
    passport_path(destination).write_text(json.dumps({"label": "1080p", "size": SIZE}))

    engine = DownloadEngine(settings, http, client, lambda job: None)
    assert await engine.run(movie_job(), Control()) == JobStatus.SUCCESS
    assert destination.read_bytes() == body
    assert ("b.mp4", "bytes=150000-") in cdn.hits


def test_subtitle_sidecars_with_glob_characters_are_deleted(tmp_path):
    video = tmp_path / "[REC] (2007).mp4"
    video.write_bytes(b"x")
    sidecar = tmp_path / "[REC] (2007).ru.vtt"
    sidecar.write_text("WEBVTT")
    delete_entry(video)
    assert not video.exists() and not sidecar.exists()


def test_non_ascii_signatures_are_rejected_not_crashing():
    settings = get_settings()
    assert verify_media("https://statichdrezka.ac/p.jpg", "аб", settings) is False
    import base64

    from fastapi import HTTPException

    token = base64.urlsafe_b64encode("123:9999999999:подпись".encode()).decode()
    with pytest.raises(HTTPException) as exc:
        verify_session_token(token, settings)
    assert exc.value.status_code == 401


# ── HDRezka client session handling ──


class FakeRezka:
    def __init__(self) -> None:
        self.login_ok = True
        self.logins = 0
        self.app = web.Application()
        self.app.router.add_post("/ajax/login/", self.login)

    async def login(self, request: web.Request) -> web.Response:
        self.logins += 1
        if not self.login_ok:
            return web.json_response({"success": False, "message": "Неверный пароль"})
        response = web.json_response({"success": True})
        response.set_cookie("dle_user_id", "42")
        response.set_cookie("dle_password", f"hash{self.logins}")
        return response


@pytest.fixture
async def rezka(tmp_path):
    fake = FakeRezka()
    server = TestServer(fake.app)
    await server.start_server()
    settings = Settings(
        HDREZKA_ORIGIN=str(server.make_url("")).rstrip("/"),
        HDREZKA_EMAIL="me@example.com",
        HDREZKA_PASSWORD="pw",
        DATA_DIR=str(tmp_path),
    )
    client = RezkaClient(settings)
    await client.start()
    yield fake, client
    await client.close()
    await server.close()


async def test_failed_relogin_keeps_the_working_session_and_backs_off(rezka):
    fake, client = rezka
    await client.login()
    assert client._cookies["dle_password"] == "hash1"

    fake.login_ok = False
    client._last_login -= 60  # pretend the session is old
    with pytest.raises(RezkaAuthError):
        await client.login(force=True)
    assert client._cookies["dle_password"] == "hash1"  # not wiped by the failed attempt

    with pytest.raises(RezkaAuthError):
        await client.login(force=True)
    assert fake.logins == 2  # backed off: no second POST to the login endpoint
