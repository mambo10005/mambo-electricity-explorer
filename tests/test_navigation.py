import pytest

from mambo_explorer.navigation import SECTIONS, section_by_key

EXPECTED_TITLES = [
    "Learn",
    "Explore",
    "Replay",
    "Model Labs",
    "Finance",
    "Compliance",
    "Sources",
    "System Health",
]


def test_sections_match_required_navigation_in_order():
    assert [s.title for s in SECTIONS] == EXPECTED_TITLES


def test_section_keys_are_unique_url_safe_slugs():
    keys = [s.key for s in SECTIONS]
    assert len(set(keys)) == len(keys)
    for key in keys:
        assert key == key.lower()
        assert all(c.isalnum() or c == "-" for c in key)
        assert key != "home"


def test_every_section_has_summary_scope_and_material_icon():
    for s in SECTIONS:
        assert s.summary.strip()
        assert s.scope and all(item.strip() for item in s.scope)
        assert s.icon.startswith(":material/")


def test_section_by_key():
    assert section_by_key("model-labs").title == "Model Labs"
    with pytest.raises(KeyError):
        section_by_key("missing")
