from pydantic import BaseModel


class SearchItem(BaseModel):
    url: str
    title: str
    kind: str
    year: str | None = None
    country: str | None = None
    genre: str | None = None
    status: str | None = None
    poster: str | None = None


class SearchPage(BaseModel):
    items: list[SearchItem]
    page: int
    has_next: bool


class Translator(BaseModel):
    """One selectable voice-over.

    HDRezka can list the same ``translator_id`` twice (e.g. "Гоблин" and
    "Гоблин (реж. версия)") — they differ only by the director/camrip/ads flags,
    which must be sent along with the stream request. ``key`` is the stable
    identity the API exchanges with the frontend.
    """

    key: str
    id: int
    name: str
    premium: bool = False
    director: bool = False
    camrip: bool = False
    ads: bool = False


class Part(BaseModel):
    """Another entry of the same franchise, as listed on the title page."""

    url: str
    title: str
    year: int | None = None
    rating: float | None = None
    current: bool = False


class TitleDetails(BaseModel):
    id: int
    url: str
    name: str
    orig_name: str | None = None
    kind: str
    is_series: bool
    year: int | None = None
    rating: float | None = None
    rating_imdb: float | None = None
    rating_kp: float | None = None
    duration: int | None = None
    country: str | None = None
    genres: list[str] = []
    age: str | None = None
    description: str | None = None
    status: str | None = None
    poster: str | None = None
    poster_hq: str | None = None
    translators: list[Translator]
    default_translator: str | None = None
    parts: list[Part] = []
    favs: str | None = None

    def translator(self, key: str) -> Translator | None:
        return next((t for t in self.translators if t.key == key), None)


class Quality(BaseModel):
    label: str
    height: int
    premium: bool
    urls: list[str]


class Subtitle(BaseModel):
    lang: str
    title: str
    url: str


class Stream(BaseModel):
    qualities: list[Quality]
    subtitles: list[Subtitle] = []
    # HDRezka serves its intro clip instead of the video (premium-only for this account)
    gated: bool = False
