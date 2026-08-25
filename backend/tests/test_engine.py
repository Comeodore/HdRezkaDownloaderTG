from app.download.engine import select_seasons


def test_empty_selection_returns_all_sorted():
    assert select_seasons([3, 1, 2], []) == [1, 2, 3]


def test_filters_to_wanted():
    assert select_seasons([1, 2, 3, 4], [2, 4]) == [2, 4]


def test_ignores_unknown_wanted():
    assert select_seasons([1, 2], [2, 9]) == [2]


def test_string_keys_sorted_numerically():
    assert select_seasons(["10", "2", "1"], []) == ["1", "2", "10"]
