"""Streamlit AppTest renders. These run the scripts headlessly; they are not browser tests."""

from pathlib import Path

import pytest
from guards import assert_no_data_elements, assert_no_unauthorized_data, section_is_implemented
from streamlit.testing.v1 import AppTest

from mambo_explorer.catalog import features
from mambo_explorer.navigation import SECTIONS
from mambo_explorer.pages import NOT_IMPLEMENTED

APP = Path(__file__).resolve().parents[1] / "src/mambo_explorer/app.py"


def test_app_entrypoint_runs_and_shows_home():
    at = AppTest.from_file(str(APP)).run(timeout=30)
    assert not at.exception
    assert at.title[0].value == "mambo electricity explorer"
    headers = [h.value for h in at.header]
    assert headers == ["Learning sequence", "Implementation status", "Data labels"]
    assert_no_data_elements(at)


def test_home_status_table_lists_every_feature():
    at = AppTest.from_file(str(APP)).run(timeout=30)
    table = at.table[0].value
    assert list(table["ID"]) == [f["id"] for f in features()]
    assert list(table["Status"]) == [f["status"] for f in features()]


def test_home_lists_all_data_labels():
    at = AppTest.from_file(str(APP)).run(timeout=30)
    text = " ".join(m.value for m in at.markdown)
    for label in ("Observed", "Derived", "Modeled", "Synthetic"):
        assert f"**{label}**" in text


@pytest.mark.parametrize("key", [s.key for s in SECTIONS])
def test_section_page_renders_without_unauthorized_data(key):
    script = f"from mambo_explorer.pages import render_section\nrender_section({key!r})\n"
    at = AppTest.from_string(script).run(timeout=30)
    assert not at.exception
    if not section_is_implemented(key):
        assert any(NOT_IMPLEMENTED in w.value for w in at.warning)
    assert_no_unauthorized_data(at, key)
