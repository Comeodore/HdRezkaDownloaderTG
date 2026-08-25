from app.routers.preview import parse_videos


def test_parse_videos_multiple_qualities_and_mirrors():
    decoded = (
        "[360p]https://cdn/a360.mp4 or https://cdn/b360.mp4,"
        "[720p]https://cdn/a720.mp4,"
        "[1080p <img src='premium.png'>]https://cdn/u1080.mp4"
    )
    videos = parse_videos(decoded)
    assert videos["360p"] == ["https://cdn/a360.mp4", "https://cdn/b360.mp4"]
    assert videos["720p"] == ["https://cdn/a720.mp4"]
    assert videos["1080p"] == ["https://cdn/u1080.mp4"]


def test_parse_videos_skips_non_mp4_and_garbage():
    decoded = "[480p]https://cdn/a.m3u8 or https://cdn/a.mp4,no-brackets-chunk"
    assert parse_videos(decoded) == {"480p": ["https://cdn/a.mp4"]}


def test_parse_videos_empty():
    assert parse_videos("") == {}
