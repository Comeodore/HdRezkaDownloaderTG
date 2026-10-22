from pathlib import Path

from app.config import get_settings
from app.download.paths import (
    episode_path,
    existing_movie,
    movie_path,
    sanitize_filename,
    series_dir,
    subtitle_path,
)


def test_sanitize_replaces_illegal_chars():
    assert sanitize_filename('a/b:c*d?"e') == "a_b_c_d__e"


def test_sanitize_strips_trailing_dots_for_smb():
    assert sanitize_filename("Mr. Robot...  ") == "Mr. Robot"
    assert sanitize_filename("...") == "Без названия"


def test_sanitize_truncates_long_names():
    result = sanitize_filename("x" * 200, max_length=20)
    assert len(result) == 20 and result.endswith("…")


def test_movie_path_includes_year():
    settings = get_settings()
    assert movie_path(settings, "Матрица", 1999) == Path(settings.media_dir) / "Матрица (1999).mp4"
    assert movie_path(settings, "Матрица", None) == Path(settings.media_dir) / "Матрица.mp4"


def test_existing_movie_finds_legacy_name(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "media_dir", str(tmp_path))
    assert existing_movie(settings, "Тетрис", 2023) is None
    (tmp_path / "Тетрис.mp4").write_bytes(b"x")
    assert existing_movie(settings, "Тетрис", 2023) == tmp_path / "Тетрис.mp4"


def test_series_dir_prefers_legacy_folder(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "media_dir", str(tmp_path))
    assert series_dir(settings, "Друзья", 1994) == tmp_path / "Друзья (1994)"
    (tmp_path / "Друзья").mkdir()
    assert series_dir(settings, "Друзья", 1994) == tmp_path / "Друзья"


def test_episode_and_subtitle_paths():
    root = Path("/m/Друзья (1994)")
    episode = episode_path(root, 2, 5)
    assert episode == root / "Сезон 2" / "S02E05.mp4"
    assert subtitle_path(episode, "ru") == root / "Сезон 2" / "S02E05.ru.vtt"
    assert subtitle_path(episode, "../../x") == root / "Сезон 2" / "S02E05.x.vtt"
