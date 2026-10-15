"""Regression checks for the focus-only CSS override (src/mambo_explorer/focus.css).

Static checks on the stylesheet: safe content, stable selectors, coverage of every
measured control, and contrast of the ring against every background it was measured on in
Chrome (Streamlit 1.65.0, docs/accessibility.md). Rendered behavior is checked in the
browser; these tests keep the file from drifting.
"""

import re
from pathlib import Path

import pytest
from test_theme_contrast import _rgb, ratio

from mambo_explorer import focus_style

CSS = focus_style.focus_css()
RING = _rgb(focus_style.FOCUS_COLOR)
# Backgrounds the blue ring was measured against (outline-offset 2px sits on these).
BACKGROUNDS = {
    "light page": (255, 255, 255),
    "light sidebar / input": (240, 242, 246),
    "dark page": (14, 17, 23),
    "dark sidebar / input": (38, 39, 48),
    "dark element toolbar": (19, 23, 32),
}
CHIP = (37, 99, 235)  # multiselect chip fill (primary), behind the inset white ring


def _rules() -> list[tuple[str, str]]:
    body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    return [(s.strip(), d.strip()) for s, d in re.findall(r"([^{}]+)\{([^{}]*)\}", body)]


def test_stylesheet_is_safe_and_static():
    lowered = CSS.lower()
    for banned in ("<script", "javascript:", "expression(", "@import", "url(", "behavior:"):
        assert banned not in lowered, banned
    assert not re.search(r"outline\s*:\s*(none|0)\b", lowered)  # never removes a native outline
    assert "st-emotion-cache" not in CSS and not re.search(r"\.css-[a-z0-9]{4,}", CSS)
    assert not re.search(r"\.[A-Za-z][\w-]*", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)), (
        "class selectors are not allowed; use elements, roles, types, or data attributes"
    )


def test_every_rule_is_scoped_focus_only_and_changes_only_the_outline():
    rules = _rules()
    assert rules
    for selector, decls in rules:
        for part in re.split(r",(?![^()]*\))", selector):
            assert part.strip().startswith('[data-testid="stApp"]'), part
        assert ":focus-visible" in selector, selector
        props = {d.split(":")[0].strip() for d in decls.split(";") if d.strip()}
        assert props <= {"outline", "outline-offset"}, props


@pytest.mark.parametrize(
    "hook",
    [
        "button",
        "a[href]",
        "summary",
        '[role="slider"]',
        '[role="spinbutton"]',
        'input[type="date"]',
        'input:is([type="radio"], [type="checkbox"])',
        'input[type="range"]',
        'input[role="combobox"]',
        '[data-testid="stMultiSelectTagsContainer"]',
        '[data-baseweb="select"]',
    ],
)
def test_every_measured_control_type_is_covered(hook):
    selectors = " ".join(selector for selector, _ in _rules())  # comments stripped
    assert hook in selectors, hook


@pytest.mark.parametrize("name", sorted(BACKGROUNDS))
def test_ring_is_at_least_3_to_1_against_every_measured_background(name):
    assert ratio(RING, BACKGROUNDS[name]) >= 3.0
    assert "#3b82f6" in CSS.lower() and focus_style.FOCUS_COLOR.lower() == "#3b82f6"


def test_chip_ring_is_at_least_3_to_1_against_the_chip():
    assert "outline: 2px solid #ffffff" in CSS
    assert ratio((255, 255, 255), CHIP) >= 3.0


def test_app_injects_the_stylesheet_once_as_a_style_element(monkeypatch):
    captured = []
    monkeypatch.setattr(focus_style.st, "html", captured.append)
    focus_style.inject_focus_style()
    assert len(captured) == 1
    html = captured[0]
    assert html.startswith("<style>") and html.endswith("</style>") and "<script" not in html
    app = Path(focus_style.__file__).with_name("app.py").read_text("utf-8")
    assert app.count("inject_focus_style()") == 1
