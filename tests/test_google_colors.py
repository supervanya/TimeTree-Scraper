import pytest

from timetree_sync.destinations.google_colors import closest_google_color_id


def test_closest_google_color() -> None:
    palette = {"1": "#7986CB", "2": "#33B679", "11": "#D60000"}

    assert closest_google_color_id("#35b77a", palette) == "2"


def test_empty_google_palette_is_rejected() -> None:
    with pytest.raises(ValueError, match="palette is empty"):
        closest_google_color_id("#ffffff", {})
