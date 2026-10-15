"""Static accessibility checks that do not need a browser."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "mambo_explorer"
BACKGROUNDS = {"light": "#ffffff", "dark": "#0e1117"}  # Streamlit theme backgrounds


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_formula_known_values():
    assert round(contrast("#000000", "#ffffff"), 1) == 21.0
    assert round(contrast("#ffffff", "#ffffff"), 1) == 1.0


def test_chart_line_colors_meet_non_text_contrast_in_both_themes():
    colors = set()
    for path in SRC.rglob("*.py"):
        for call in re.findall(
            r"(?:line_chart|utc_label_chart)\((.*?)\)\n", path.read_text("utf-8"), re.DOTALL
        ):
            colors |= set(re.findall(r'"(#[0-9a-fA-F]{6})"', call))
    assert colors, "no chart colors found"
    for color in colors:
        for theme, background in BACKGROUNDS.items():
            assert contrast(color, background) >= 3.0, (color, theme)


def test_ercot_palette_meets_non_text_contrast_in_both_themes():
    from mambo_explorer.ercot_explore import PALETTE

    assert len(set(PALETTE)) == len(PALETTE)
    for color in PALETTE:
        for theme, background in BACKGROUNDS.items():
            assert contrast(color, background) >= 3.0, (color, theme)


def test_ercot_chart_has_text_alternative():
    source = (SRC / "ercot_explore.py").read_text("utf-8")
    assert "alt=(" in source and "table below" in source
