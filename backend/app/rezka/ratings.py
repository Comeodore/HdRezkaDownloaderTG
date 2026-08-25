import re

_VALUE_RE = re.compile(r"\d+(?:[.,]\d+)?")


def external_rating(soup: object, service: str) -> float | None:
    """Extract an external rating (service: "imdb" | "kp") from a title page.

    HDRezka renders them as
    ``<span class="b-post__info_rates imdb">IMDb: <span class="bold">7.8</span> (…)</span>``.
    """
    node = soup.select_one(f"span.b-post__info_rates.{service} span.bold")
    if node is None:
        return None
    match = _VALUE_RE.search(node.get_text())
    if not match:
        return None
    try:
        value = float(match.group().replace(",", "."))
    except ValueError:
        return None
    return value if 0 < value <= 10 else None
