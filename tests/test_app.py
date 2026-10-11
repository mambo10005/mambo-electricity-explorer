"""Streamlit AppTest renders. These run the scripts headlessly; they are not browser tests."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from eia_fixtures import FAKE_KEY, FakeEIA, synthetic_rows
from guards import assert_no_data_elements, assert_no_unauthorized_data, section_is_implemented
from streamlit.testing.v1 import AppTest

from mambo_explorer.catalog import features
from mambo_explorer.collect import collect, plan_collection
from mambo_explorer.eia.client import EIAClient
from mambo_explorer.navigation import SECTIONS
from mambo_explorer.pages import NOT_IMPLEMENTED
from mambo_explorer.storage import Store

APP = Path(__file__).resolve().parents[1] / "src/mambo_explorer/app.py"
EXPLORE = "from mambo_explorer.pages import render_page\nrender_page('explore')\n"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    return path


def _ingest(data_dir, overrides=None):
    plan = plan_collection(days=2, lookback_days=0, today=date(2026, 10, 11))
    rows = synthetic_rows(plan.fetch_start_day, plan.fetch_days, overrides=overrides)
    client = EIAClient(FAKE_KEY, transport=FakeEIA(rows), sleep=lambda s: None)
    collect(plan, client, Store(data_dir))


def _text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [e.value for e in at.caption]
    parts += [w.value for w in at.warning] + [i.value for i in at.info] + [c.value for c in at.code]
    return "\n".join(parts)


def test_app_entrypoint_runs_and_shows_home(data_dir):
    at = AppTest.from_file(str(APP)).run(timeout=30)
    assert not at.exception
    assert at.title[0].value == "mambo electricity explorer"
    headers = [h.value for h in at.header]
    assert headers == ["Learning sequence", "Implementation status", "Data labels"]
    assert_no_data_elements(at)


def test_home_status_table_lists_every_feature(data_dir):
    at = AppTest.from_file(str(APP)).run(timeout=30)
    table = at.table[0].value
    assert list(table["ID"]) == [f["id"] for f in features()]
    assert list(table["Status"]) == [f["status"] for f in features()]


def test_home_lists_all_data_labels(data_dir):
    at = AppTest.from_file(str(APP)).run(timeout=30)
    text = " ".join(m.value for m in at.markdown)
    for label in ("Observed", "Derived", "Modeled", "Synthetic"):
        assert f"**{label}**" in text


@pytest.mark.parametrize("key", [s.key for s in SECTIONS])
def test_section_page_renders_without_unauthorized_data(key, data_dir):
    script = f"from mambo_explorer.pages import render_page\nrender_page({key!r})\n"
    at = AppTest.from_string(script).run(timeout=30)
    assert not at.exception
    if not section_is_implemented(key):
        assert any(NOT_IMPLEMENTED in w.value for w in at.warning)
    assert_no_unauthorized_data(at, key)


# --- Explore: the first real-data page -----------------------------------------------------


def test_explore_empty_state_shows_instructions_not_a_chart(data_dir):
    at = AppTest.from_string(EXPLORE).run(timeout=30)
    assert not at.exception
    assert_no_data_elements(at)  # stricter than the section guard: no chart without data
    text = _text(at)
    assert "No observations have been collected yet" in text
    assert "mambo collect --dry-run" in text
    assert "not reconstructed" in text
    assert not data_dir.exists()  # rendering never collects or creates the store


def test_explore_populated_state_charts_actual_vs_published_forecast(data_dir):
    _ingest(data_dir, {("D", "2026-10-10T03"): None})
    at = AppTest.from_string(EXPLORE).run(timeout=30)
    assert not at.exception
    assert len(at.get("vega_lite_chart")) == 1
    assert len(at.dataframe) == 1 and len(at.dataframe[0].value) == 96
    text = _text(at)
    assert "not by this application" in text
    assert "1 reported without a value" in text  # missing value indicated, not hidden
    assert "megawatthours" in text and "Publication time:** not provided" in text
    assert "Last successful collection" in text
    assert not any("stale" in w.value for w in at.warning)


def test_explore_warns_when_data_is_stale(data_dir):
    _ingest(data_dir)
    with sqlite3.connect(Store(data_dir).catalog) as con:
        con.execute("UPDATE runs SET finished_at='2026-01-01T00:00:00+00:00'")
    at = AppTest.from_string(EXPLORE).run(timeout=30)
    assert any("stale" in w.value for w in at.warning)


def test_explore_rejects_unsafe_data_dir(monkeypatch):
    monkeypatch.setenv("MAMBO_DATA_DIR", "src/not-allowed")
    at = AppTest.from_string(EXPLORE).run(timeout=30)
    assert any("Unsafe data directory" in e.value for e in at.error)
    assert_no_data_elements(at)
