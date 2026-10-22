import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.download.manager import DownloadManager
from app.library.service import LibraryEnricher, LibraryMeta
from app.main import app, create_app
from app.routers import media
from app.streams import StreamResolver
from tests.conftest import forge_init_data
from aiohttp.test_utils import TestServer

from tests.fakes import MOVIE_URL, SERIES_URL, Cdn, FakeClient, cdn_app


class NullNotifier:
    def job_finished(self, job):
        pass


@pytest.fixture
def client():
    settings = get_settings()
    fake = FakeClient()
    with TestClient(app) as test_client:
        state = app.state
        test_client.portal.call(state.manager.close)
        test_client.portal.call(state.resolver.close)
        test_client.portal.call(state.client.close)
        state.client = fake
        state.resolver = StreamResolver(settings, fake)
        test_client.portal.call(state.resolver.start)
        state.meta = LibraryMeta(settings)
        state.enricher = LibraryEnricher(state.meta, fake)
        state.manager = DownloadManager(settings, fake, state.meta, NullNotifier())
        test_client.portal.call(state.manager.start)
        test_client.fake = fake
        yield test_client
        test_client.portal.call(state.manager.close)
        test_client.portal.call(state.resolver.close)
        for job in list(state.manager.list_jobs()):
            state.manager._jobs.pop(job.id, None)


def auth(user_id: int = 123) -> dict:
    return {"X-Telegram-Init-Data": forge_init_data(user_id)}


def test_requires_auth(client):
    assert client.get("/api/search?q=x").status_code == 401


def test_forbidden_for_unlisted_user(client):
    assert client.get("/api/search?q=x", headers=auth(999)).status_code == 403


def test_health_is_public(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True and "active_downloads" in body


def test_search_returns_signed_poster_urls_and_paging(client):
    body = client.get("/api/search", params={"q": "matrix", "page": 1}, headers=auth()).json()
    assert body["has_next"] is True and body["page"] == 1
    poster = body["items"][0]["poster"]
    assert poster.startswith("/api/img/") and poster.endswith(".jpg")


def test_title_exposes_translator_keys_and_local_state(client):
    body = client.get("/api/title", params={"url": MOVIE_URL}, headers=auth()).json()
    assert [t["key"] for t in body["translators"]] == ["56", "80-dir"]
    assert body["local"] == {"exists": False, "episodes": {}}
    assert "favs" not in body


def test_title_rejects_non_rezka_urls(client):
    client.app.state.client = __import__("app.rezka.client", fromlist=["RezkaClient"]).RezkaClient(get_settings())
    response = client.get("/api/title", params={"url": "https://evil.example/ajax/login/"}, headers=auth())
    assert response.status_code == 400


def test_episodes_with_local_counts(client):
    root = Path(get_settings().media_dir) / "Друзья (1994)" / "Сезон 1"
    root.mkdir(parents=True, exist_ok=True)
    (root / "S01E01.mp4").write_bytes(b"x")
    body = client.get("/api/episodes", params={"url": SERIES_URL, "translator": "84"}, headers=auth()).json()
    assert body["seasons"] == [
        {"number": 1, "episodes": 2, "local": 1},
        {"number": 2, "episodes": 2, "local": 0},
    ]


def test_create_download_validation_and_conflict(client):
    bad = client.post("/api/downloads", json={"url": MOVIE_URL, "translator": "999"}, headers=auth())
    assert bad.status_code == 400
    bad_quality = client.post("/api/downloads", json={"url": MOVIE_URL, "translator": "56", "max_height": 2160},
                              headers=auth())
    assert bad_quality.status_code == 422

    client.app.state.manager._semaphore = asyncio.Semaphore(0)  # keep jobs queued
    first = client.post("/api/downloads", json={"url": MOVIE_URL, "translator": "56"}, headers=auth())
    assert first.status_code == 200
    job = first.json()["job"]
    assert "owner_id" not in job and job["poster"].startswith("/api/img/")

    second = client.post("/api/downloads", json={"url": MOVIE_URL, "translator": "80-dir"}, headers=auth())
    assert second.status_code == 409 and second.json()["job_id"] == job["id"]

    listed = client.get("/api/downloads", headers=auth()).json()["jobs"]
    assert listed[0]["id"] == job["id"]
    assert client.post("/api/downloads/missing/cancel", headers=auth()).status_code == 404


def test_library_lists_disk_usage_and_deletes(client):
    media_dir = Path(get_settings().media_dir)
    (media_dir / "Тетрис.mp4").write_bytes(b"x" * 10)
    (media_dir / "Тетрис.ru.vtt").write_text("WEBVTT")
    body = client.get("/api/library", headers=auth()).json()
    assert body["disk"]["total"] > 0
    item = next(i for i in body["items"] if i["name"] == "Тетрис")
    assert item["kind"] == "movie" and item["size"] == 10 and item["downloading"] is False

    assert client.delete(f"/api/library/{item['id']}", headers=auth()).status_code == 200
    assert not (media_dir / "Тетрис.mp4").exists() and not (media_dir / "Тетрис.ru.vtt").exists()
    assert client.delete(f"/api/library/{item['id']}", headers=auth()).status_code == 404


def test_image_proxy_requires_valid_signature(client):
    remote = "https://statichdrezka.ac/i/poster.jpg"
    path = media.image_url(remote, get_settings())
    forged = path.replace("/api/img/", "/api/img/AAAA")
    assert client.get(forged).status_code == 403

    media._cache.set(remote, (b"\xff\xd8jpeg", "image/jpeg"))
    response = client.get(path)
    assert response.status_code == 200 and response.content == b"\xff\xd8jpeg"
    assert "immutable" in response.headers["cache-control"]


def test_image_url_only_for_rezka_hosts():
    settings = get_settings()
    assert media.image_url("https://static.hdrezka.ac/x.jpg", settings)
    assert media.image_url("https://evil.example/x.jpg", settings) is None
    assert media.image_url(None, settings) is None


def test_preview_requires_token(client):
    response = client.get("/api/preview", params={"url": MOVIE_URL, "translator": "56"})
    assert response.status_code == 401


def test_static_files_cannot_escape_frontend_dir(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>app</html>")
    (static / "robots.txt").write_text("ok")
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    monkeypatch.setattr(get_settings(), "frontend_dir", str(static))
    spa = TestClient(create_app())

    assert spa.get("/robots.txt").text == "ok"
    assert spa.get("/some/route").text == "<html>app</html>"
    for attack in ("/..%2Fsecret.txt", "/%2E%2E/secret.txt", "/..%2F..%2F..%2Fetc%2Fhostname"):
        response = spa.get(attack)
        assert "TOP SECRET" not in response.text
        assert response.text == "<html>app</html>"
    assert spa.head("/").status_code == 200


def test_image_proxy_returns_the_whole_body(client, monkeypatch):
    # regression: StreamReader.read(n) returned a partial buffer → half-drawn posters
    cdn = Cdn()
    body = cdn.add("poster.jpg", 900_000)
    server = TestServer(cdn_app(cdn))
    client.portal.call(server.start_server)
    try:
        monkeypatch.setattr(media, "is_allowed_image_host", lambda url: True)
        path = media.image_url(str(server.make_url("/poster.jpg")), get_settings())
        response = client.get(path)
        assert response.status_code == 200
        assert response.content == body
    finally:
        client.portal.call(server.close)


def test_qualities_reports_premium_only(client):
    fake = client.fake
    fake.set_stream((981, "56", None, None), {q: ["https://cdn/x/intro.mp4"] for q in ("720p", "1080p")})
    body = client.get("/api/qualities", params={"url": MOVIE_URL, "translator": "56"}, headers=auth()).json()
    assert body["items"] == [] and "премиум" in body["premium_only"]


def test_title_includes_parts(client):
    from app.rezka.models import Part

    fake = client.fake
    fake.titles[MOVIE_URL] = fake.titles[MOVIE_URL].model_copy(
        update={"parts": [Part(url=MOVIE_URL, title="Матрица", year=1999, current=True),
                          Part(url=SERIES_URL, title="Другое", year=2003)]}
    )
    body = client.get("/api/title", params={"url": MOVIE_URL}, headers=auth()).json()
    assert [p["title"] for p in body["parts"]] == ["Матрица", "Другое"]
