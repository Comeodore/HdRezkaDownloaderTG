from bs4 import BeautifulSoup

from app.rezka.ratings import external_rating

RATES_HTML = (
    '<td><span class="b-post__info_rates imdb"><a href="#">IMDb</a>: '
    '<span class="bold">7.8</span> <i>(275 782)</i></span>, '
    '<span class="b-post__info_rates kp"><a href="#">Кинопоиск</a>: '
    '<span class="bold">8,1</span> <i>(45 800)</i></span></td>'
)


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_parses_imdb_and_kp():
    page = soup(RATES_HTML)
    assert external_rating(page, "imdb") == 7.8
    assert external_rating(page, "kp") == 8.1


def test_missing_block_returns_none():
    page = soup("<div class='b-post__info'></div>")
    assert external_rating(page, "imdb") is None
    assert external_rating(page, "kp") is None


def test_non_numeric_value_returns_none():
    page = soup('<span class="b-post__info_rates imdb"><span class="bold">N/A</span></span>')
    assert external_rating(page, "imdb") is None


def test_out_of_range_value_rejected():
    page = soup('<span class="b-post__info_rates kp"><span class="bold">99.9</span></span>')
    assert external_rating(page, "kp") is None
