"""Pure parsers for HDRezka pages and ajax payloads — no I/O, unit-tested on real markup."""
import base64
import itertools
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from .models import Part, Quality, SearchItem, Stream, Subtitle, TitleDetails, Translator

KIND_BY_CATEGORY = {"films": "movie", "series": "series", "cartoons": "cartoon", "animation": "anime"}
TITLE_PATH_RE = re.compile(r"^/(films|series|cartoons|animation)/[\w-]+/\d+-[\w.-]+\.html$")

_TAG_RE = re.compile(r"<[^>]*>")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_YEAR_RE = re.compile(r"\d{4}")
_HEIGHT_RE = re.compile(r"(\d{3,4})p")
_NAMED_HEIGHTS = {"2k": 1440, "4k": 2160}
_INIT_RE = re.compile(r"sof\.tv\.initCDN(Movies|Series)Events\(\s*(\d+)\s*,\s*(\d+)\s*,\s*([^,]+),\s*([^,]+),\s*([^,]+),")
_TRASH_CODES = sorted(
    (
        base64.b64encode("".join(combo).encode()).decode()
        for size in (2, 3)
        for combo in itertools.product("@#!^$", repeat=size)
    ),
    key=len,
    reverse=True,
)


class LoginRequired(Exception):
    """The page is the HDRezka sign-in wall — the session cookies are missing or stale."""


class CaptchaRequired(Exception):
    """HDRezka served its anti-bot verification page."""


class ParseError(Exception):
    pass


def category(url: str) -> str:
    return urlparse(url).path.lstrip("/").split("/", 1)[0]


def kind_of(url: str) -> str:
    return KIND_BY_CATEGORY.get(category(url), "movie")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _text(node: Tag | None) -> str | None:
    if node is None:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


_CAPTCHA_MARKERS = (
    "<title>Verify</title>",
    'id="challenge-form"',
    'class="g-recaptcha"',
    'class="cf-turnstile"',
    "/.within.website/",  # Anubis proof-of-work wall (seen on rezka.ag mirrors)
    "Проверяем, что вы не бот",
)
_LOGIN_MARKERS = ('id="loginForm"', 'name="login_name"', "<title>Вход на HDrezka", "<title>Sign In</title>")


def detect_wall(html: str) -> None:
    """Raise if HDRezka served its sign-in or anti-bot page instead of content."""
    if any(marker in html for marker in _CAPTCHA_MARKERS):
        raise CaptchaRequired()
    if any(marker in html for marker in _LOGIN_MARKERS):
        raise LoginRequired()


# ── search ──────────────────────────────────────────────────────────────────


def parse_search(html: str) -> tuple[list[SearchItem], bool]:
    soup = _soup(html)
    items: list[SearchItem] = []
    for node in soup.select(".b-content__inline_item"):
        link = node.select_one(".b-content__inline_item-link a")
        url = node.get("data-url") or (link.get("href") if link else None)
        if not url or link is None:
            continue
        info = _text(node.select_one(".b-content__inline_item-link div")) or ""
        parts = [part.strip() for part in info.split(",")]
        cover = node.select_one(".b-content__inline_item-cover img")
        items.append(
            SearchItem(
                url=url,
                title=link.get_text(strip=True).split(" / ")[0] or "Без названия",
                kind=kind_of(url),
                year=parts[0].replace(" ", "") if parts and _YEAR_RE.match(parts[0]) else None,
                country=parts[1] if len(parts) > 1 and parts[1] else None,
                genre=parts[2] if len(parts) > 2 and parts[2] else None,
                status=_text(node.select_one(".b-content__inline_item-cover .info")),
                poster=cover.get("src") if cover else None,
            )
        )
    if not items:
        detect_wall(html)
    has_next = soup.select_one("a > .b-navigation__next") is not None
    return items, has_next


# ── title page ──────────────────────────────────────────────────────────────


def _list_text(node: Tag | None) -> str | None:
    """``<a>США</a> , <a>Австралия</a>`` → ``США, Австралия``."""
    if node is None:
        return None
    links = [a.get_text(strip=True) for a in node.select("a")]
    return ", ".join(link for link in links if link) or _text(node)


def _info_rows(soup: BeautifulSoup) -> dict[str, Tag]:
    rows: dict[str, Tag] = {}
    for tr in soup.select(".b-post__info tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) == 2:
            label = cells[0].get_text(strip=True).rstrip(":").strip()
            rows[label] = cells[1]
    return rows


def _external_rating(soup: BeautifulSoup, service: str) -> float | None:
    node = soup.select_one(f".b-post__info_rates.{service} .bold")
    match = _NUMBER_RE.search(node.get_text()) if node else None
    if not match:
        return None
    value = float(match.group().replace(",", "."))
    return value if 0 < value <= 10 else None


def _flag(node: Tag, name: str) -> bool:
    return str(node.get(f"data-{name}", "0")).strip().lower() in ("1", "true")


def translator_key(translator_id: int, director: bool = False, camrip: bool = False, ads: bool = False) -> str:
    return f"{translator_id}{'-dir' if director else ''}{'-cam' if camrip else ''}{'-ads' if ads else ''}"


def _translators(soup: BeautifulSoup, html: str, rows: dict[str, Tag]) -> tuple[list[Translator], str | None]:
    translators: list[Translator] = []
    active: str | None = None
    for node in soup.select("#translators-list > [data-translator_id]"):
        translator_id = int(node["data-translator_id"])
        director, camrip, ads = _flag(node, "director"), _flag(node, "camrip"), _flag(node, "ads")
        key = translator_key(translator_id, director, camrip, ads)
        if any(t.key == key for t in translators):
            continue
        name = (node.get("title") or node.get_text(" ", strip=True)).strip()
        flag = node.find("img")
        lang = flag.get("title") if flag else None
        if lang and lang not in name:
            name = f"{name} ({lang})"
        translators.append(
            Translator(
                key=key,
                id=translator_id,
                name=name,
                premium="b-prem_translator" in (node.get("class") or []),
                director=director,
                camrip=camrip,
                ads=ads,
            )
        )
        if "active" in (node.get("class") or []):
            active = key

    init = _INIT_RE.search(html)
    if not translators and init:
        # Single-voice titles have no list — the player init call carries the id.
        kind, translator_id = init.group(1), int(init.group(3))
        flags = [arg.strip() == "1" for arg in init.group(4, 5, 6)] if kind == "Movies" else [False, False, False]
        camrip, ads, director = flags
        name = _text(rows.get("В переводе")) or "Оригинал"
        key = translator_key(translator_id, director, camrip, ads)
        translators.append(
            Translator(key=key, id=translator_id, name=name, director=director, camrip=camrip, ads=ads)
        )
        active = key
    return translators, active or (translators[0].key if translators else None)


def _parts(soup: BeautifulSoup, url: str) -> list[Part]:
    """Franchise entries in chronological order; the page itself is marked ``current``."""
    numbered: list[tuple[int, Part]] = []
    for node in soup.select(".b-post__partcontent_item"):
        current = "current" in (node.get("class") or [])
        link = node.select_one(".title a")
        target = url if current else node.get("data-url") or (link.get("href") if link else None)
        title = _text(node.select_one(".title"))
        if not target or not title or not TITLE_PATH_RE.match(urlparse(target).path):
            continue
        year = _YEAR_RE.search(_text(node.select_one(".year")) or "")
        rating = _NUMBER_RE.search(_text(node.select_one(".rating")) or "")
        number = re.search(r"\d+", _text(node.select_one(".num")) or "")
        numbered.append((
            int(number.group()) if number else 0,
            Part(
                url=target,
                title=title,
                year=int(year.group()) if year else None,
                rating=float(rating.group().replace(",", ".")) if rating else None,
                current=current,
            ),
        ))
    numbered.sort(key=lambda pair: pair[0])
    return [part for _, part in numbered] if len(numbered) > 1 else []


def parse_title(html: str, url: str) -> TitleDetails:
    soup = _soup(html)
    heading = soup.select_one(".b-post__title")
    if heading is None:
        detect_wall(html)
        raise ParseError("Страница тайтла не распознана")

    rows = _info_rows(soup)
    post_id = soup.select_one("#post_id")
    og_type = soup.find("meta", property="og:type")
    is_series = bool(og_type and og_type.get("content") == "video.tv_series")
    year_link = soup.select_one('.b-post__info a[href*="/year/"]')
    year_match = _YEAR_RE.search(year_link.get("href", "")) if year_link else None
    rating_node = soup.select_one(".b-post__rating .num")
    rating_match = _NUMBER_RE.search(rating_node.get_text()) if rating_node else None
    duration_match = re.search(r"\d+", _text(rows.get("Время")) or "")
    cover = soup.select_one(".b-sidecover")
    cover_img = cover.find("img") if cover else None
    cover_link = cover.find("a") if cover else None
    favs = soup.select_one("#ctrl_favs")
    genres = [a.get_text(strip=True) for a in rows["Жанр"].select("a")] if "Жанр" in rows else []
    translators, default = _translators(soup, html, rows)

    if post_id is not None and post_id.get("value", "").isdigit():
        title_id = int(post_id["value"])
    else:
        match = re.search(r"/(\d+)-", urlparse(url).path)
        if not match:
            raise ParseError("Не найден id тайтла")
        title_id = int(match.group(1))

    return TitleDetails(
        id=title_id,
        url=url,
        name=heading.get_text(" ", strip=True).split(" / ")[0],
        orig_name=_text(soup.select_one(".b-post__origtitle")),
        kind=kind_of(url),
        is_series=is_series,
        year=int(year_match.group()) if year_match else None,
        rating=float(rating_match.group().replace(",", ".")) if rating_match else None,
        rating_imdb=_external_rating(soup, "imdb"),
        rating_kp=_external_rating(soup, "kp"),
        duration=int(duration_match.group()) if duration_match else None,
        country=_list_text(rows.get("Страна")),
        genres=[genre for genre in genres if genre.lower() != "зарубежные"],
        age=(_text(rows.get("Возраст")) or "").split(" ")[0] or None,
        description=_text(soup.select_one(".b-post__description_text")),
        status=_text(soup.select_one(".b-post__infolast")),
        poster=cover_img.get("src") if cover_img else None,
        poster_hq=cover_link.get("href") if cover_link else None,
        translators=translators,
        default_translator=default,
        parts=_parts(soup, url),
        favs=favs.get("value") if favs else None,
    )


# ── series episodes ─────────────────────────────────────────────────────────


def parse_episodes(episodes_html: str) -> dict[int, list[int]]:
    seasons: dict[int, set[int]] = {}
    for node in _soup(episodes_html).select(".b-simple_episode__item[data-season_id][data-episode_id]"):
        seasons.setdefault(int(node["data-season_id"]), set()).add(int(node["data-episode_id"]))
    return {season: sorted(seasons[season]) for season in sorted(seasons)}


# ── streams ─────────────────────────────────────────────────────────────────


def decode_stream(encoded: str) -> str:
    """Undo HDRezka's stream obfuscation: base64 sprinkled with base64-encoded junk."""
    data = "".join(encoded.replace("#h", "").split("//_//"))
    for code in _TRASH_CODES:
        data = data.replace(code, "")
    try:
        return base64.b64decode(data + "=" * (-len(data) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return data


def quality_height(label: str) -> int:
    match = _HEIGHT_RE.search(label)
    if match:
        return int(match.group(1))
    return _NAMED_HEIGHTS.get(label.strip().lower(), 0)


def parse_qualities(decoded: str) -> list[Quality]:
    """``[360p]a.mp4:hls:manifest.m3u8 or b.mp4,[1080p Ultra<img…>]…`` → qualities.

    Premium tiers carry a ``pjs-prem-quality`` marker in the raw label; for a
    regular account they resolve to a ~8 MB placeholder clip.
    """
    qualities: dict[str, Quality] = {}
    for chunk in re.split(r",(?=\[)", decoded):
        match = re.match(r"\[(.*?)\](.*)", chunk, re.S)
        if not match:
            continue
        raw_label, tail = match.groups()
        label = _TAG_RE.sub("", raw_label).strip()
        urls = [link.strip() for link in tail.split(" or ") if link.strip().endswith(".mp4")]
        if not label or not urls:
            continue
        premium = "prem" in raw_label.lower()
        if label in qualities:
            qualities[label].urls.extend(url for url in urls if url not in qualities[label].urls)
        else:
            qualities[label] = Quality(label=label, height=quality_height(label), premium=premium, urls=urls)
    # labels pointing at the same file as a premium tier are that placeholder too (e.g. "2K", "4K")
    premium_files = {_file_of(url) for q in qualities.values() if q.premium for url in q.urls}
    for quality in qualities.values():
        if not quality.premium and any(_file_of(url) in premium_files for url in quality.urls):
            quality.premium = True
    return list(qualities.values())


def _file_of(url: str) -> str:
    return urlparse(url).path.rsplit("/", 1)[-1]


def is_gated(qualities: list[Quality]) -> bool:
    """Every regular quality is the same file — HDRezka's intro clip instead of the video.

    Happens for a logged-in non-premium account on premium-only releases
    (HdRezkaApi issues #37/#38).
    """
    regular = [q for q in qualities if not q.premium]
    files = {_file_of(url) for q in regular for url in q.urls}
    return len(regular) > 1 and len(files) == 1


def parse_subtitles(raw: object, languages: object) -> list[Subtitle]:
    if not isinstance(raw, str) or not raw:
        return []
    codes = languages if isinstance(languages, dict) else {}
    subtitles: list[Subtitle] = []
    for chunk in re.split(r",(?=\[)", raw):
        match = re.match(r"\[(.*?)\](\S+)", chunk.strip())
        if match:
            title, url = match.groups()
            subtitles.append(Subtitle(lang=str(codes.get(title) or title).lower(), title=title, url=url))
    return subtitles


def parse_stream(payload: dict) -> Stream:
    encoded = payload.get("url")
    if not encoded:
        raise ParseError("Пустой ответ плеера")
    qualities = parse_qualities(decode_stream(encoded))
    return Stream(
        qualities=qualities,
        subtitles=parse_subtitles(payload.get("subtitle"), payload.get("subtitle_lns")),
        gated=bool(payload.get("premium_content")) or is_gated(qualities),
    )
