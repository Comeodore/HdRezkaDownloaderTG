from pydantic import BaseModel


class SearchItem(BaseModel):
    id: str
    title: str
    url: str
    year: str | None = None
    poster: str | None = None
    kind: str


class Translator(BaseModel):
    id: int
    name: str


class SeasonInfo(BaseModel):
    number: int
    episodes: int


class TitleDetails(BaseModel):
    url: str
    name: str
    kind: str
    is_series: bool
    year: str | None = None
    rating: float | None = None
    rating_imdb: float | None = None
    rating_kp: float | None = None
    poster: str | None = None
    translators: list[Translator]
