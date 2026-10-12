"""Automated contrast checks for the committed Streamlit theme (.streamlit/config.toml).

What is checked here is arithmetic on configured and *measured* colors; it is not a WCAG
conformance claim. Rendered colors were measured in Chrome against Streamlit 1.65.0
(docs/accessibility.md). Streamlit derives the hover/focus shade itself, so the measured
value is pinned to that version: a Streamlit upgrade fails this file until someone
re-measures the rendered colors.
"""

import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"
MEASURED_STREAMLIT = "1.65.0"
WHITE = (255, 255, 255)
PAGE = {"light": (255, 255, 255), "dark": (14, 17, 23)}  # rendered .stApp backgrounds
HOVER_FOCUS = (16, 67, 177)  # rendered primary-button background on :hover / :focus-visible
# Rendered secondary/form-submit buttons: (text, background). Measured in dark only; the
# light theme's hover/active overlays were not measured in Stage 9 (docs/accessibility.md).
SECONDARY = {"dark": ((250, 250, 250), (19, 23, 32))}


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _lum(rgb) -> float:
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _over(fg, alpha, bg):
    return tuple(alpha * x + (1 - alpha) * y for x, y in zip(fg, bg, strict=True))


def _theme() -> dict:
    return tomllib.loads(CONFIG.read_text("utf-8"))["theme"]


def test_ratio_formula_matches_known_values():
    assert ratio(WHITE, (0, 0, 0)) == pytest.approx(21.0)
    assert ratio(WHITE, _rgb("#FF4B4B")) == pytest.approx(3.30, abs=0.01)  # the old default


def test_both_themes_are_defined_so_users_can_still_switch():
    theme = _theme()
    assert set(theme) >= {"light", "dark"}
    assert "base" not in theme  # a fixed base would remove the light/dark choice


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_primary_button_text_meets_4_5_to_1_in_every_measured_state(mode):
    primary = _rgb(_theme()[mode]["primaryColor"])
    assert ratio(WHITE, primary) >= 4.5  # default and :active (white text on primary)
    assert ratio(WHITE, HOVER_FOCUS) >= 4.5  # :hover and :focus-visible


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_primary_is_distinguishable_from_the_page(mode):
    primary = _rgb(_theme()[mode]["primaryColor"])
    assert ratio(primary, PAGE[mode]) >= 3.0  # non-text UI component (button body)


@pytest.mark.parametrize("mode", sorted(SECONDARY))
def test_secondary_buttons_keep_text_contrast_in_every_state(mode):
    text, bg = SECONDARY[mode]
    overlay = (172, 177, 195)
    for alpha in (0.0, 0.15, 0.25):  # default, :hover/:focus-visible, :active overlays
        assert ratio(text, _over(overlay, alpha, bg)) >= 4.5


def test_measurements_are_for_the_installed_streamlit():
    assert version("streamlit") == MEASURED_STREAMLIT, (
        "Streamlit changed: re-measure rendered button colors (docs/accessibility.md)"
    )
