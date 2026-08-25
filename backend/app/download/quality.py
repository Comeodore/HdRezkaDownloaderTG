from ..logging_conf import get_logger

logger = get_logger("quality")

QUALITY_PRIORITY = ("1080p", "720p", "480p", "360p", "240p")
PREMIUM_QUALITIES = frozenset({"2160p", "1440p", "1080p Ultra"})


def normalize_urls(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [url for url in raw if url]
    return [raw] if raw else []


def preview_qualities(videos: dict[str, object]) -> list[tuple[str, list[str]]]:
    """Qualities ordered cheapest-first for preview streaming.

    Premium tiers are skipped (broken placeholders on a free account); unknown
    labels go last so known-cheap ones are probed first.
    """
    rank = {quality: index for index, quality in enumerate(QUALITY_PRIORITY)}
    usable: list[tuple[str, list[str]]] = []
    for quality, raw in videos.items():
        if quality in PREMIUM_QUALITIES:
            continue
        urls = normalize_urls(raw)
        if urls:
            usable.append((quality, urls))
    usable.sort(key=lambda pair: -rank.get(pair[0], -1))
    return usable


def choose_quality(sizes: dict[str, int]) -> str | None:
    """Pick the best non-premium quality by measured byte size.

    Premium tiers (2160p / 1440p / 1080p Ultra) are skipped entirely — for a
    non-premium account they serve a broken multi-MB placeholder. Among the
    rest, the largest genuinely complete file wins (a broken mirror that
    reports a tiny size loses); ties break toward the higher label.
    """
    rank = {quality: index for index, quality in enumerate(QUALITY_PRIORITY)}
    valid = {
        quality: size
        for quality, size in sizes.items()
        if size > 0 and quality not in PREMIUM_QUALITIES
    }
    if not valid:
        return None
    return max(valid, key=lambda quality: (valid[quality], -rank.get(quality, 999)))
