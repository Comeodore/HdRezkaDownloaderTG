import base64
import json
from pathlib import Path

import pytest

from app.rezka import parse

FIXTURES = Path(__file__).parent / "fixtures"
MOVIE_URL = "https://rezka.fi/films/fiction/981-matrica-1999-latest.html"
SERIES_URL = "https://rezka.fi/series/comedy/1733-druzya-1994-latest.html"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


# ── search ──


def test_search_page_items_and_pagination():
    items, has_next = parse.parse_search(fixture("search.html"))
    assert len(items) == 8
    assert has_next is True
    by_kind = {item.kind for item in items}
    assert {"cartoon", "series", "movie"} <= by_kind

    friends = next(item for item in items if item.url == SERIES_URL)
    assert friends.title == "Друзья"
    assert friends.year == "1994-2004"
    assert friends.country == "США"
    assert friends.genre == "Комедии"
    assert friends.status == "Завершен (все серии)"
    assert friends.poster and friends.poster.startswith("https://")


def test_search_year_comes_from_card_not_url():
    # URLs like …-1994-latest.html broke the old URL-based year regex
    items, _ = parse.parse_search(fixture("search.html"))
    assert all(item.year for item in items)


def test_search_last_page_has_no_next():
    items, has_next = parse.parse_search(fixture("search_last.html"))
    assert items and has_next is False


def test_search_empty():
    assert parse.parse_search(fixture("search_empty.html")) == ([], False)


def test_search_login_wall_detected():
    with pytest.raises(parse.LoginRequired):
        parse.parse_search(fixture("login_wall.html"))


# ── title ──


def test_movie_title():
    title = parse.parse_title(fixture("movie.html"), MOVIE_URL)
    assert title.id == 981
    assert title.name == "Матрица"
    assert title.orig_name == "The Matrix"
    assert title.is_series is False
    assert title.kind == "movie"
    assert title.year == 1999
    assert title.rating == 9.37
    assert title.rating_imdb == 8.7
    assert title.rating_kp == 8.5
    assert title.duration == 136
    assert title.country == "США, Австралия"
    assert "Фантастика" in title.genres and "Зарубежные" not in title.genres
    assert title.age == "16+"
    assert title.description and title.description.startswith("Томас Андерсон")
    assert title.poster and title.poster_hq and title.poster != title.poster_hq
    assert title.default_translator == "56"
    assert title.favs == "fixture-favs"


def test_director_cut_is_a_separate_translator():
    title = parse.parse_title(fixture("movie.html"), MOVIE_URL)
    goblins = [t for t in title.translators if t.id == 80]
    assert [(t.key, t.director) for t in goblins] == [("80", False), ("80-dir", True)]
    assert goblins[1].name == "Гоблин (реж. версия)"
    assert len({t.key for t in title.translators}) == len(title.translators) == 23


def test_translator_language_suffix():
    title = parse.parse_title(fixture("movie.html"), MOVIE_URL)
    names = {t.name for t in title.translators}
    assert "Украинский дубляж" in names  # flag title already in the name
    assert "Грузинский двухголосый" in names


def test_premium_translator_flag():
    html = fixture("movie.html").replace(
        'class="b-translator__item" data-ads="0" data-camrip="0" data-cdn_quality="" data-director="0" '
        'data-id="981" data-translator_id="337"',
        'class="b-translator__item b-prem_translator" data-ads="0" data-camrip="0" data-cdn_quality="" '
        'data-director="0" data-id="981" data-translator_id="337"',
    )
    title = parse.parse_title(html, MOVIE_URL)
    assert title.translator("337").premium is True
    assert title.translator("56").premium is False


def test_series_title():
    title = parse.parse_title(fixture("series.html"), SERIES_URL)
    assert title.id == 1733
    assert title.is_series is True
    assert title.kind == "series"
    assert title.year == 1994
    assert title.status == "Завершен (все серии)"
    assert title.duration == 22
    assert [t.key for t in title.translators] == ["84", "87", "565", "389", "238"]
    assert title.translator("389").name == "Украинский (1+1)"
    assert title.default_translator == "84"


def test_single_voice_title_falls_back_to_player_init():
    html = fixture("movie.html")
    start = html.index('<ul class="b-translators__list"')
    end = html.index("</ul>", start) + len("</ul>")
    title = parse.parse_title(html[:start] + html[end:], MOVIE_URL)
    assert [t.key for t in title.translators] == ["56"]
    assert title.default_translator == "56"


def test_title_login_wall():
    with pytest.raises(parse.LoginRequired):
        parse.parse_title(fixture("login_wall.html"), MOVIE_URL)


def test_title_garbage_is_parse_error():
    with pytest.raises(parse.ParseError):
        parse.parse_title("<html><title>Oops</title><body>nothing</body></html>", MOVIE_URL)


def test_title_path_validation():
    assert parse.TITLE_PATH_RE.match("/films/fiction/981-matrica-1999-latest.html")
    assert parse.TITLE_PATH_RE.match("/animation/adventures/57085-naruto-ova-8-2011.html")
    assert not parse.TITLE_PATH_RE.match("/ajax/login/")
    assert not parse.TITLE_PATH_RE.match("/films/../../etc/passwd")


# ── episodes ──


def test_episodes():
    payload = json.loads(fixture("episodes.json"))
    episodes = parse.parse_episodes(payload["episodes"])
    assert list(episodes) == [1, 2, 3]
    assert episodes[1] == [1, 2, 3, 4, 5]
    assert episodes[3][0] == 1 and len(episodes[3]) == 25


# ── streams ──


def _obfuscate(decoded: str) -> str:
    """Re-create HDRezka's obfuscation: base64 with junk segments spliced in."""
    clean = base64.b64encode(decoded.encode()).decode()
    junk = [base64.b64encode(j.encode()).decode() for j in ("@#", "!^$", "$$!")]
    cut = len(clean) // 3
    return "#h" + clean[:cut] + "//_//" + junk[0] + clean[cut : 2 * cut] + "//_//" + junk[1] + clean[2 * cut :] + junk[2]


DECODED = (
    "[360p]https://cdn.example/a/360.mp4:hls:manifest.m3u8 or https://cdn2.example/a/360.mp4,"
    "[720p]https://cdn.example/a/720.mp4:hls:manifest.m3u8 or https://cdn2.example/a/720.mp4,"
    "[1080p]https://cdn.example/a/1080.mp4:hls:manifest.m3u8 or https://cdn2.example/a/1080.mp4,"
    '[<span class="pjs-prem-quality">1080p Ultra<img src="https://static.hdrezka.ac/prem-icon.svg" alt=""></span>]'
    "https://cdn.example/a/ultra.mp4"
)


def test_decode_stream_round_trip():
    assert parse.decode_stream(_obfuscate(DECODED)) == DECODED


def test_parse_qualities_marks_premium_and_keeps_mp4_mirrors():
    qualities = {q.label: q for q in parse.parse_qualities(DECODED)}
    assert list(qualities) == ["360p", "720p", "1080p", "1080p Ultra"]
    assert qualities["360p"].urls == ["https://cdn2.example/a/360.mp4"]
    assert qualities["1080p"].height == 1080 and not qualities["1080p"].premium
    assert qualities["1080p Ultra"].premium is True


def test_quality_height_named_labels():
    assert parse.quality_height("2K") == 1440
    assert parse.quality_height("4K") == 2160
    assert parse.quality_height("480p") == 480
    assert parse.quality_height("weird") == 0


def test_parse_stream_with_subtitles():
    stream = parse.parse_stream(
        {
            "url": _obfuscate(DECODED),
            "subtitle": "[Русский]https://s.example/ru.vtt,[English]https://s.example/en.vtt",
            "subtitle_lns": {"off": "", "Русский": "ru", "English": "en"},
        }
    )
    assert len(stream.qualities) == 4
    assert [(s.lang, s.url) for s in stream.subtitles] == [
        ("ru", "https://s.example/ru.vtt"),
        ("en", "https://s.example/en.vtt"),
    ]


def test_parse_stream_without_subtitles():
    stream = parse.parse_stream({"url": _obfuscate(DECODED), "subtitle": False, "subtitle_lns": False})
    assert stream.subtitles == []


# ── franchise parts, gated streams, anti-bot walls ──


def test_franchise_parts_in_order_with_current_marked():
    title = parse.parse_title(fixture("movie.html"), MOVIE_URL)
    assert [(p.title, p.year) for p in title.parts[:3]] == [
        ("Матрица", 1999),
        ("Аниматрица", 2003),
        ("Матрица: Перезагрузка", 2003),
    ]
    assert [p.current for p in title.parts].count(True) == 1 and title.parts[0].url == MOVIE_URL
    assert title.parts[0].rating == 8.5


def test_no_parts_block_means_no_parts():
    assert parse.parse_title(fixture("series.html"), SERIES_URL).parts == []


def test_labels_sharing_the_premium_file_are_premium_too():
    decoded = (
        "[720p]https://cdn/a/720.mp4,[1080p]https://cdn/a/1080.mp4,"
        '[<span class="pjs-prem-quality">1080p Ultra</span>]https://cdn/a/zrkms.mp4,'
        "[2K]https://cdn/a/zrkms.mp4,[4K]https://cdn/a/zrkms.mp4"
    )
    qualities = {q.label: q.premium for q in parse.parse_qualities(decoded)}
    assert qualities == {"720p": False, "1080p": False, "1080p Ultra": True, "2K": True, "4K": True}
    assert parse.is_gated(parse.parse_qualities(decoded)) is False


def test_intro_clip_in_every_quality_is_gated():
    # HdRezkaApi #37: a non-premium account gets the same intro file for all qualities
    decoded = ",".join(
        f"[{label}]https://cdn/x/2r9ld.mp4:hls:manifest.m3u8 or https://mirror/x/2r9ld.mp4"
        for label in ("360p", "480p", "720p", "1080p")
    )
    assert parse.parse_stream({"url": _obfuscate(decoded)}).gated is True


def test_premium_content_flag_marks_stream_gated():
    assert parse.parse_stream({"url": _obfuscate(DECODED), "premium_content": 1}).gated is True
    assert parse.parse_stream({"url": _obfuscate(DECODED), "premium_content": 0}).gated is False


def test_anubis_bot_check_is_detected():
    page = (
        '<!doctype html><html lang="ru"><head><title>Проверяем, что вы не бот!</title>'
        '<link rel="stylesheet" href="/.within.website/x/xess/xess.min.css?cachebuster=v1.27"></head></html>'
    )
    with pytest.raises(parse.CaptchaRequired):
        parse.parse_title(page, MOVIE_URL)
