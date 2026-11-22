from src.api.routes.tasks import (
    _normalize_font_color,
    _normalize_font_family,
    _normalize_font_size,
)


def test_normalize_font_size_bounds_values():
    assert _normalize_font_size(None) is None
    assert _normalize_font_size("") is None
    assert _normalize_font_size("4") == 12
    assert _normalize_font_size("120") == 72


def test_normalize_font_color_accepts_hex_values():
    assert _normalize_font_color(None) is None
    assert _normalize_font_color("  ") is None
    assert _normalize_font_color("#abcdef") == "#ABCDEF"
    assert _normalize_font_color("blue") == "#FFFFFF"


def test_normalize_font_family_passes_through_empty_values_as_none():
    assert _normalize_font_family(None) is None
    assert _normalize_font_family("  ") is None
    assert _normalize_font_family("Inter") == "Inter"
