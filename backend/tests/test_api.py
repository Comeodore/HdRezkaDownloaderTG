import pytest
from fastapi.testclient import TestClient

from app.deps import get_gateway, get_manager
from app.download.progress import Job, ProgressHub
from app.main import app
from app.rezka.models import SearchItem, SeasonInfo, TitleDetails, Translator
from tests.conftest import forge_init_data


class FakeGateway:
    async def search(self, query: str) -> list[SearchItem]:
        return [
            SearchItem(
                id="abc",
                title="Матрица",
                url="https://rezka.fi/films/x-1999.html",
                year="1999",
                poster=None,
                kind="movie",
            )
        ]

    async def details(self, url: str) -> TitleDetails:
        return TitleDetails(
            url=url,
            name="Матрица",
            kind="movie",
            is_series=False,
            year="1999",
            rating=8.5,
            poster=None,
            translators=[Translator(id=1, name="Оригинал")],
        )

    async def seasons(self, url: str, translator_id: int) -> list[SeasonInfo]:
        return [SeasonInfo(number=1, episodes=7), SeasonInfo(number=2, episodes=13)]


class FakeManager:
    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.hub = ProgressHub()

    async def create(self, url: str, translator_id: int, poster=None, seasons=None) -> Job:
        job = Job(
            id="job1",
            url=url,
            translator_id=translator_id,
            translator_name="Оригинал",
            name="Матрица",
            kind="movie",
            is_series=False,
            seasons=sorted(set(seasons or [])),
        )
        self.jobs.append(job)
        return job

    def list_jobs(self) -> list[Job]:
        return self.jobs

    async def cancel(self, job_id: str) -> bool:
        return any(job.id == job_id for job in self.jobs)

    async def retry(self, job_id: str) -> Job | None:
        return next((job for job in self.jobs if job.id == job_id), None)


@pytest.fixture
def client():
    manager = FakeManager()
    app.dependency_overrides[get_gateway] = lambda: FakeGateway()
    app.dependency_overrides[get_manager] = lambda: manager
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth():
    return {"X-Telegram-Init-Data": forge_init_data(123)}


def test_requires_auth(client):
    assert client.get("/api/search?q=x").status_code == 401


def test_forbidden_for_unlisted_user(client):
    assert client.get("/api/search?q=x", headers={"X-Telegram-Init-Data": forge_init_data(999)}).status_code == 403


def test_search(client):
    response = client.get("/api/search?q=matrix", headers=auth())
    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["title"] == "Матрица"
    assert results[0]["kind"] == "movie"


def test_title(client):
    response = client.get("/api/title", params={"url": "https://rezka.fi/films/x-1999.html"}, headers=auth())
    body = response.json()
    assert response.status_code == 200
    assert body["is_series"] is False
    assert body["translators"][0]["name"] == "Оригинал"


def test_session_issues_token(client):
    response = client.get("/api/session", headers=auth())
    assert response.status_code == 200
    assert response.json()["token"]
    assert response.json()["user"]["id"] == 123


def test_create_and_list_and_cancel(client):
    created = client.post(
        "/api/downloads",
        json={"url": "https://rezka.fi/films/x-1999.html", "translator_id": 1},
        headers=auth(),
    )
    assert created.status_code == 200
    job_id = created.json()["job"]["id"]

    listed = client.get("/api/downloads", headers=auth())
    assert listed.json()["jobs"][0]["id"] == job_id

    cancelled = client.delete(f"/api/downloads/{job_id}", headers=auth())
    assert cancelled.status_code == 200

    assert client.delete("/api/downloads/missing", headers=auth()).status_code == 404


def test_seasons(client):
    response = client.get(
        "/api/seasons",
        params={"url": "https://rezka.fi/series/x-2008.html", "translator_id": 56},
        headers=auth(),
    )
    assert response.status_code == 200
    seasons = response.json()["seasons"]
    assert seasons == [{"number": 1, "episodes": 7}, {"number": 2, "episodes": 13}]


def test_create_with_seasons(client):
    created = client.post(
        "/api/downloads",
        json={"url": "https://rezka.fi/series/x.html", "translator_id": 1, "seasons": [2, 1, 2]},
        headers=auth(),
    )
    assert created.status_code == 200
    assert created.json()["job"]["seasons"] == [1, 2]


def test_library_empty(client):
    response = client.get("/api/library", headers=auth())
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_title_includes_external_ratings_fields(client):
    response = client.get("/api/title", params={"url": "https://rezka.fi/films/x-1999.html"}, headers=auth())
    body = response.json()
    assert "rating_imdb" in body
    assert "rating_kp" in body


def test_preview_stream_requires_token(client):
    response = client.get("/api/preview/stream", params={"url": "https://rezka.fi/films/x.html", "translator_id": 1})
    assert response.status_code == 401
