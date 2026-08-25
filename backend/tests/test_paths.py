from pathlib import Path

from app.config import get_settings
from app.download.paths import episode_path, movie_path, sanitize_filename, series_dir


def test_sanitize_replaces_illegal_chars():
    assert sanitize_filename('a/b:c*d?"e') == "a_b_c_d__e"


def test_sanitize_truncates_long_names():
    result = sanitize_filename("x" * 200, max_length=20)
    assert len(result) == 20
    assert result.endswith("...")


def test_movie_path():
    settings = get_settings()
    assert movie_path(settings, "Матрица") == Path(settings.media_dir) / "Матрица.mp4"


def test_series_and_episode_path():
    settings = get_settings()
    root = series_dir(settings, "Друзья")
    assert root == Path(settings.media_dir) / "Друзья"
    assert episode_path(root, 2, 5) == root / "Сезон 2" / "S02E05.mp4"
