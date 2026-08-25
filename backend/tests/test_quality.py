from app.download.quality import choose_quality, normalize_urls, preview_qualities


def test_normalize_urls():
    assert normalize_urls(["a", "", "b"]) == ["a", "b"]
    assert normalize_urls("single") == ["single"]
    assert normalize_urls(None) == []


def test_picks_largest_real_size():
    assert choose_quality({"720p": 836_000_000, "480p": 458_000_000, "1080p": 2_100_000_000}) == "1080p"


def test_broken_high_label_loses_to_larger_lower():
    # 1080p mirror returned a broken 8 MB file; 720p is the real one
    assert choose_quality({"1080p": 8_554_559, "720p": 836_477_783}) == "720p"


def test_premium_tiers_excluded():
    sizes = {"1080p Ultra": 9_000_000_000, "2160p": 9_000_000_000, "720p": 836_000_000}
    assert choose_quality(sizes) == "720p"


def test_premium_only_returns_none():
    assert choose_quality({"1080p Ultra": 8_000_000, "2160p": 0}) is None


def test_all_zero_returns_none():
    assert choose_quality({"1080p": 0, "720p": 0}) is None


def test_tie_breaks_to_higher_label():
    assert choose_quality({"720p": 500, "480p": 500}) == "720p"


def test_preview_qualities_lowest_first_premium_skipped():
    videos = {"1080p": ["u1080"], "360p": ["u360a", "u360b"], "720p": "u720", "1080p Ultra": ["prem"]}
    ordered = preview_qualities(videos)
    assert [quality for quality, _ in ordered] == ["360p", "720p", "1080p"]
    assert ordered[0][1] == ["u360a", "u360b"]


def test_preview_qualities_unknown_label_goes_last():
    videos = {"strange": ["x"], "480p": ["u"]}
    assert [quality for quality, _ in preview_qualities(videos)] == ["480p", "strange"]


def test_preview_qualities_empty_when_only_premium():
    assert preview_qualities({"2160p": ["p"], "720p": []}) == []
