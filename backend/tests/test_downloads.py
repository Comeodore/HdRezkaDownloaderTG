import asyncio
import json
from pathlib import Path

import aiohttp
import pytest
from aiohttp.test_utils import TestServer

from app.config import Settings
from app.download import quality
from app.download.engine import Control, DownloadEngine, Interrupted, JobFailed
from app.download.manager import DownloadConflict, DownloadManager
from app.download.paths import part_path, passport_path
from app.download.progress import Job, JobStatus
from app.library.service import LibraryMeta
from app.notify import finish_message
from tests.fakes import MOVIE_URL, SERIES_URL, Cdn, FakeClient, cdn_app

SIZE = 300_000


@pytest.fixture(autouse=True)
def small_files(monkeypatch):
    # real HDRezka placeholders are ~8 MB; scale the threshold down for test payloads
    monkeypatch.setattr(quality, "MIN_REAL_SIZE", 50_000)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    media, data = tmp_path / "media", tmp_path / "data"
    media.mkdir()
    s = Settings(MEDIA_DIR=str(media), DATA_DIR=str(data), NOTIFY_ON_FINISH=False)
    s.retry_delay = 0.01
    s.min_free_space = 0
    s.chunk_size = 64 * 1024
    return s


@pytest.fixture
async def cdn():
    cdn = Cdn()
    server = TestServer(cdn_app(cdn))
    await server.start_server()
    cdn.base = str(server.make_url("")).rstrip("/")
    yield cdn
    await server.close()


@pytest.fixture
async def http():
    async with aiohttp.ClientSession() as session:
        yield session


def movie_job(**overrides) -> Job:
    data = dict(id="j1", url=MOVIE_URL, name="Матрица", year=1999, kind="movie", is_series=False,
                translator_key="56", translator_name="Дубляж")
    data.update(overrides)
    return Job(**data)


def series_job(**overrides) -> Job:
    data = dict(id="s1", url=SERIES_URL, name="Друзья", year=1994, kind="series", is_series=True,
                translator_key="84", translator_name="СТС")
    data.update(overrides)
    return Job(**data)


async def run_engine(settings, http, client, job, control=None):
    engine = DownloadEngine(settings, http, client, lambda _job: None)
    return await engine.run(job, control or Control())


# ── quality choice ──


def test_pick_best_skips_broken_higher_label():
    probed = [
        quality.Probed("1080p", 1080, 60_000_000, ["a"]),  # broken encode, smaller than 720p
        quality.Probed("720p", 720, 800_000_000, ["b"]),
        quality.Probed("480p", 480, 400_000_000, ["c"]),
    ]
    assert quality.pick_best(probed, 1080).label == "720p"


def test_pick_best_respects_max_height():
    probed = [
        quality.Probed("1080p", 1080, 2_000_000_000, ["a"]),
        quality.Probed("720p", 720, 800_000_000, ["b"]),
    ]
    assert quality.pick_best(probed, 720).label == "720p"
    assert quality.pick_best(probed, 1080).label == "1080p"
    assert quality.pick_best(probed, 480).label == "720p"  # nothing ≤480 → lowest available
    assert quality.pick_best([], 1080) is None


async def test_probe_ignores_premium_and_placeholders(cdn, http):
    cdn.add("1080.mp4", SIZE)
    cdn.add("720.mp4", SIZE // 2)
    cdn.add("ultra.mp4", 1000)  # placeholder
    from app.rezka.models import Quality

    probed = await quality.probe(http, [
        Quality(label="1080p Ultra", height=1080, premium=True, urls=[cdn.url("ultra.mp4")]),
        Quality(label="1080p", height=1080, premium=False, urls=[cdn.url("missing.mp4"), cdn.url("1080.mp4")]),
        Quality(label="720p", height=720, premium=False, urls=[cdn.url("720.mp4")]),
    ], "ua")
    assert [(p.label, p.size) for p in probed] == [("1080p", SIZE), ("720p", SIZE // 2)]
    assert probed[0].urls[0] == cdn.url("1080.mp4")  # working mirror first


# ── movie engine ──


async def test_movie_download_with_failover_and_director_flag(settings, cdn, http):
    body = cdn.add("m1080.mp4", SIZE)
    cdn.add("m720.mp4", SIZE // 2)
    cdn.broken.add("dead.mp4")
    client = FakeClient(cdn)
    client.set_stream((981, "80-dir", None, None), {
        "720p": [cdn.url("m720.mp4")],
        "1080p": [cdn.url("dead.mp4"), cdn.url("m1080.mp4")],
    })
    job = movie_job(translator_key="80-dir")
    assert await run_engine(settings, http, client, job) == JobStatus.SUCCESS
    target = Path(settings.media_dir) / "Матрица (1999).mp4"
    assert target.read_bytes() == body
    assert not part_path(target).exists()
    assert job.quality == "1080p" and job.target == "Матрица (1999).mp4"


async def test_movie_resumes_from_part_file(settings, cdn, http):
    body = cdn.add("m.mp4", SIZE)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    target = Path(settings.media_dir) / "Матрица (1999).mp4"
    part_path(target).write_bytes(body[:100_000])
    passport_path(target).write_text(json.dumps({"label": "1080p", "size": SIZE}))

    assert await run_engine(settings, http, client, movie_job()) == JobStatus.SUCCESS
    assert target.read_bytes() == body
    assert ("m.mp4", "bytes=100000-") in cdn.hits
    assert not passport_path(target).exists()


async def test_resume_sticks_to_the_encode_of_the_part_file(settings, cdn, http):
    # the first run got 720p; on resume the CDN also offers 1080p — must not mix encodes
    cdn.add("m1080.mp4", SIZE)
    body720 = cdn.add("m720.mp4", SIZE // 2)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m1080.mp4")], "720p": [cdn.url("m720.mp4")]})
    target = Path(settings.media_dir) / "Матрица (1999).mp4"
    part_path(target).write_bytes(body720[:50_000])
    passport_path(target).write_text(json.dumps({"label": "720p", "size": SIZE // 2}))

    job = movie_job()
    assert await run_engine(settings, http, client, job) == JobStatus.SUCCESS
    assert target.read_bytes() == body720 and job.quality == "720p"


async def test_part_without_passport_is_restarted(settings, cdn, http):
    body = cdn.add("m.mp4", SIZE)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    target = Path(settings.media_dir) / "Матрица (1999).mp4"
    part_path(target).write_bytes(b"garbage from an unknown encode")

    assert await run_engine(settings, http, client, movie_job()) == JobStatus.SUCCESS
    assert target.read_bytes() == body


async def test_mirror_ignoring_range_restarts_instead_of_corrupting(settings, cdn, http):
    body = cdn.add("m.mp4", SIZE)
    cdn.ignore_range.add("m.mp4")
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    target = Path(settings.media_dir) / "Матрица (1999).mp4"
    part_path(target).write_bytes(body[:100_000])
    passport_path(target).write_text(json.dumps({"label": "1080p", "size": SIZE}))

    assert await run_engine(settings, http, client, movie_job()) == JobStatus.SUCCESS
    assert target.read_bytes() == body  # the old engine appended the full body → corrupt file


async def test_dropped_connection_is_resumed(settings, cdn, http):
    body = cdn.add("m.mp4", SIZE)
    cdn.cut_after["m.mp4"] = 120_000
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})

    assert await run_engine(settings, http, client, movie_job()) == JobStatus.SUCCESS
    assert (Path(settings.media_dir) / "Матрица (1999).mp4").read_bytes() == body
    assert any(rng and rng.startswith("bytes=") and rng != "bytes=0-0" for _, rng in cdn.hits)


async def test_existing_movie_is_not_downloaded_again(settings, cdn, http):
    target = Path(settings.media_dir) / "Матрица (1999).mp4"
    target.write_bytes(b"x" * 10)
    client = FakeClient(cdn)
    assert await run_engine(settings, http, client, movie_job()) == JobStatus.SUCCESS
    assert client.stream_calls == []


async def test_only_premium_qualities_fail_clearly(settings, cdn, http):
    cdn.add("p.mp4", 1000)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p Ultra": [cdn.url("p.mp4")]}, premium={"1080p Ultra"})
    with pytest.raises(JobFailed, match="премиум"):
        await run_engine(settings, http, client, movie_job())


async def test_no_space_fails_before_download(settings, cdn, http):
    cdn.add("m.mp4", SIZE)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    settings.min_free_space = 10**18
    with pytest.raises(JobFailed, match="места"):
        await run_engine(settings, http, client, movie_job())


async def test_cancel_interrupts(settings, cdn, http):
    cdn.add("m.mp4", SIZE)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    control = Control()
    control.stop("pause")
    with pytest.raises(Interrupted):
        await run_engine(settings, http, client, movie_job(), control)


# ── series engine ──


async def test_series_selected_seasons_skip_existing_and_report_partial(settings, cdn, http):
    client = FakeClient(cdn)
    for season, episode in [(2, 1), (2, 2)]:
        cdn.add(f"s{season}e{episode}.mp4", SIZE // 3)
        client.set_stream((1733, "84", season, episode), {"720p": [cdn.url(f"s{season}e{episode}.mp4")]})
    cdn.broken.add("s2e2.mp4")
    root = Path(settings.media_dir) / "Друзья (1994)" / "Сезон 2"
    root.mkdir(parents=True)

    job = series_job(seasons=[2])
    assert await run_engine(settings, http, client, job) == JobStatus.PARTIAL
    assert job.total_episodes == 2 and job.done_episodes == 1
    assert job.failed == ["S02E02"] and "S02E02" in job.error
    assert (root / "S02E01.mp4").stat().st_size == SIZE // 3
    assert all(call[2] == 2 for call in client.stream_calls)  # season 1 untouched


async def test_series_reuses_legacy_folder(settings, cdn, http):
    client = FakeClient(cdn)
    client.episode_map = {1: [1]}
    legacy = Path(settings.media_dir) / "Друзья" / "Сезон 1"
    legacy.mkdir(parents=True)
    (legacy / "S01E01.mp4").write_bytes(b"x")
    job = series_job()
    assert await run_engine(settings, http, client, job) == JobStatus.SUCCESS
    assert job.target == "Друзья" and client.stream_calls == []


# ── manager ──


async def wait_for(predicate, timeout=5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


class RecordingNotifier:
    def __init__(self):
        self.finished: list[Job] = []

    def job_finished(self, job):
        self.finished.append(job)


async def make_manager(settings, client, notifier=None):
    manager = DownloadManager(settings, client, LibraryMeta(settings), notifier or RecordingNotifier())
    await manager.start()
    return manager


async def test_manager_completes_persists_and_records_library_meta(settings, cdn):
    cdn.add("m.mp4", SIZE)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    notifier = RecordingNotifier()
    manager = await make_manager(settings, client, notifier)
    job = await manager.create(MOVIE_URL, "56", [], 1080, owner_id=123)
    await wait_for(lambda: job.status == JobStatus.SUCCESS)
    await manager.close()

    saved = json.loads((Path(settings.data_dir) / "jobs.json").read_text())
    assert saved[0]["status"] == "success" and saved[0]["owner_id"] == 123
    meta = json.loads((Path(settings.data_dir) / "library.json").read_text())
    assert meta["Матрица (1999).mp4"]["url"] == MOVIE_URL
    assert [j.id for j in notifier.finished] == [job.id]


async def test_manager_rejects_duplicate_active_download(settings, cdn):
    cdn.add("m.mp4", SIZE)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    manager = await make_manager(settings, client)
    manager._semaphore = asyncio.Semaphore(0)  # keep the first job queued
    await manager.create(MOVIE_URL, "56", [], 1080, owner_id=1)
    with pytest.raises(DownloadConflict):
        await manager.create(MOVIE_URL, "80-dir", [], 1080, owner_id=1)
    await manager.close()


async def test_series_jobs_with_disjoint_seasons_may_coexist(settings, cdn):
    manager = await make_manager(settings, FakeClient(cdn))
    manager._semaphore = asyncio.Semaphore(0)
    await manager.create(SERIES_URL, "84", [1], 1080, owner_id=1)
    await manager.create(SERIES_URL, "84", [2], 1080, owner_id=1)
    with pytest.raises(DownloadConflict):
        await manager.create(SERIES_URL, "84", [], 1080, owner_id=1)
    await manager.close()


async def test_unfinished_jobs_resume_after_restart(settings, cdn):
    body = cdn.add("m.mp4", SIZE)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    queued = movie_job(id="persisted", status=JobStatus.RUNNING)
    (Path(settings.data_dir)).mkdir(parents=True, exist_ok=True)
    (Path(settings.data_dir) / "jobs.json").write_text(json.dumps([queued.to_dict()]))

    manager = await make_manager(settings, client)
    job = manager.get("persisted")
    await wait_for(lambda: job.status == JobStatus.SUCCESS)
    assert (Path(settings.media_dir) / "Матрица (1999).mp4").read_bytes() == body
    await manager.close()


async def test_pause_resume_and_cancel_cleanup(settings, cdn):
    cdn.add("m.mp4", SIZE)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    manager = await make_manager(settings, client)
    manager._semaphore = asyncio.Semaphore(0)
    job = await manager.create(MOVIE_URL, "56", [], 1080, owner_id=1)

    assert manager.pause(job.id)
    await wait_for(lambda: job.status == JobStatus.PAUSED)
    part = part_path(Path(settings.media_dir) / "Матрица (1999).mp4")
    part.write_bytes(b"partial")
    passport = passport_path(Path(settings.media_dir) / "Матрица (1999).mp4")
    passport.write_text("{}")

    assert manager.cancel(job.id)
    assert job.status == JobStatus.CANCELLED and not part.exists() and not passport.exists()
    assert manager.remove(job.id) and manager.get(job.id) is None
    await manager.close()


async def test_retry_reuses_the_same_job(settings, cdn):
    cdn.add("m.mp4", SIZE)
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {"1080p": [cdn.url("m.mp4")]})
    manager = await make_manager(settings, client)
    job = movie_job(id="failed", status=JobStatus.ERROR, error="boom")
    manager._jobs[job.id] = job
    assert manager.retry("failed") is job
    await wait_for(lambda: job.status == JobStatus.SUCCESS)
    assert job.error is None
    await manager.close()


def test_finish_message():
    job = series_job(status=JobStatus.PARTIAL, done_episodes=20, total_episodes=24, error="Не скачались: S01E05")
    text = finish_message(job)
    assert "Друзья (1994)" in text and "20 из 24" in text
    assert finish_message(movie_job(status=JobStatus.CANCELLED)) is None


# ── library enrichment ──


async def test_enricher_matches_exact_title_and_year(settings):
    from app.library.service import LibraryEnricher, list_items
    from app.rezka.models import SearchItem, SearchPage

    class Catalog:
        async def search(self, query, page=1):
            items = {
                "Матрица": [SearchItem(url=MOVIE_URL, title="Матрица", kind="movie", year="1999", poster="https://statichdrezka.ac/m.jpg"),
                            SearchItem(url="https://rezka.fi/films/x/1-matrica-2021.html", title="Матрица", kind="movie", year="2021")],
                "Друзья": [SearchItem(url=SERIES_URL, title="Друзья", kind="series", year="1994-2004"),
                           SearchItem(url="https://rezka.fi/films/x/2-druzya.html", title="Друзья", kind="movie", year="2015")],
                "Тетрис": [SearchItem(url="https://rezka.fi/films/x/3-tetris.html", title="Тетрис", kind="movie", year="2023"),
                           SearchItem(url="https://rezka.fi/films/x/4-tetris.html", title="Тетрис", kind="movie", year="1990")],
            }
            return SearchPage(items=items.get(query, []), page=1, has_next=False)

    media = Path(settings.media_dir)
    (media / "Матрица (1999).mp4").write_bytes(b"x")
    (media / "Тетрис.mp4").write_bytes(b"x")  # ambiguous without a year → left alone
    (media / "Друзья" / "Сезон 1").mkdir(parents=True)
    (media / "Друзья" / "Сезон 1" / "S01E01.mp4").write_bytes(b"x")

    meta = LibraryMeta(settings)
    enricher = LibraryEnricher(meta, Catalog())
    assert enricher.schedule(list_items(settings, meta)) is True
    await enricher._task

    by_entry = {item["entry"]: item for item in list_items(settings, meta)}
    assert by_entry["Матрица (1999).mp4"]["url"] == MOVIE_URL
    assert by_entry["Матрица (1999).mp4"]["poster"] == "https://statichdrezka.ac/m.jpg"
    assert by_entry["Друзья"]["url"] == SERIES_URL  # the movie of the same name is filtered by kind
    assert by_entry["Тетрис.mp4"]["url"] is None
    assert enricher.schedule(list_items(settings, meta)) is False  # every entry looked up once


async def test_gated_stream_fails_clearly_without_downloading(settings, cdn, http):
    cdn.add("intro.mp4", 2 * SIZE)  # even a "big enough" intro must not be saved as the movie
    client = FakeClient(cdn)
    client.set_stream((981, "56", None, None), {q: [cdn.url("intro.mp4")] for q in ("480p", "720p", "1080p")})
    with pytest.raises(JobFailed, match="премиум"):
        await run_engine(settings, http, client, movie_job())
    assert not any(Path(settings.media_dir).iterdir())
