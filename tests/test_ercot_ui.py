"""ERCOT Explore view via AppTest (headless). All data is SYNTHETIC."""

from datetime import date

import pytest
from ercot_fixtures import FakeErcot, day_doc
from guards import assert_no_data_elements, assert_no_unauthorized_data
from streamlit.testing.v1 import AppTest

from mambo_explorer.ercot.client import ErcotClient
from mambo_explorer.ercot.collect import Selection, collect, store

EXPLORE = "from mambo_explorer.pages import render_page\nrender_page('explore')\n"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    return path


def _ingest(data_dir, docs):
    collect(
        Selection(latest=len(docs)),
        ErcotClient(transport=FakeErcot(docs), sleep=lambda s: None),
        store(data_dir),
    )


def _ercot(at: AppTest) -> AppTest:
    at.session_state["explore_source"] = "ercot"
    return at.run(timeout=30)


def _table(at: AppTest, column: str):
    return next(tb.value for tb in at.table if column in tb.value.columns)


def _text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [x.value for x in at.info] + [x.value for x in at.warning]
    return "\n".join(parts)


def test_default_source_is_eia_and_selector_offers_all_five(data_dir):
    at = AppTest.from_string(EXPLORE).run(timeout=30)
    assert not at.exception
    assert at.radio(key="explore_source").value == "eia"
    assert at.radio(key="explore_source").options == [
        "EIA-930 via EIA API (ERCO demand and day-ahead forecast)",
        "ERCOT direct: NP6-345-CD actual load by weather zone",
        "EIA-930 via EIA API (ERCO net generation by energy source)",
        "ERCOT direct: NP4-190-CD day-ahead settlement point price (HB_NORTH)",
        "ERCOT direct: NP6-905-CD real-time settlement point price (HB_NORTH)",
    ]


def test_ercot_empty_state_shows_instructions_not_a_chart(data_dir):
    at = _ercot(AppTest.from_string(EXPLORE))
    assert not at.exception
    assert_no_data_elements(at)
    text = _text(at)
    assert "No ERCOT observations have been collected" in text
    assert "mambo collect --source ercot --dry-run" in text
    assert "never joined" in text
    assert not (data_dir / "ercot-np6-345-cd").exists()  # rendering creates no store


def test_ercot_populated_shows_total_labels_units_and_provenance(data_dir):
    _ingest(
        data_dir,
        dict(
            [
                day_doc(
                    date(2026, 10, 10),
                    "103",
                    "2026-10-11T05:50:00-05:00",
                    overrides={("05:00", "N"): {"EAST": ""}},
                )
            ]
        ),
    )
    at = _ercot(AppTest.from_string(EXPLORE))
    assert not at.exception
    assert len(at.get("vega_lite_chart")) == 1
    assert_no_unauthorized_data(at, "explore")
    table = _table(at, "Zones − TOTAL (check)")
    assert list(table.columns)[:2] == ["HourEnding", "DSTFlag"]
    assert {"COAST", "TOTAL", "Zones − TOTAL (check)"} <= set(table.columns)
    assert list(table["HourEnding"])[:2] == ["01:00", "02:00"]
    text = _text(at)
    assert "not stated by" in text.lower()  # units are not assumed
    assert "2026-10-11T05:50:00-05:00 (= 2026-10-11 10:50 UTC)" in text
    assert "1 values missing" in text
    assert "never joined" in text


def test_ercot_dst_twin_rows_are_both_shown(data_dir):
    _ingest(
        data_dir,
        dict(
            [
                day_doc(
                    date(2026, 10, 10),
                    "301",
                    "2026-10-11T05:50:00-05:00",
                    dst={"02:00": ["N", "Y"]},
                )
            ]
        ),
    )
    at = _ercot(AppTest.from_string(EXPLORE))
    for table in (_table(at, "Zones − TOTAL (check)"), _table(at, "Value (as published)")):
        twins = table[table["HourEnding"] == "02:00"]
        assert list(twins["DSTFlag"]) == ["N", "Y"]  # preserved exactly, in both views
    assert any("25 hourly rows" in w.value for w in at.warning)


def test_eia_view_unaffected_by_ercot_data(data_dir):
    _ingest(data_dir, dict([day_doc(date(2026, 10, 10), "103", "2026-10-11T05:50:00-05:00")]))
    at = AppTest.from_string(EXPLORE).run(timeout=30)  # default source: EIA
    assert any("No observations have been collected yet" in i.value for i in at.info)
    assert_no_data_elements(at)


def test_narrow_viewer_lists_every_value_of_each_series(data_dir):
    _ingest(
        data_dir,
        dict(
            [
                day_doc(
                    date(2026, 10, 10),
                    "103",
                    "2026-10-11T05:50:00-05:00",
                    overrides={("05:00", "N"): {"EAST": ""}},
                )
            ]
        ),
    )
    at = _ercot(AppTest.from_string(EXPLORE))
    viewer = _table(at, "Value (as published)")
    assert list(viewer.columns) == ["#", "HourEnding", "DSTFlag", "Value (as published)", "Flags"]
    assert len(viewer) == 24 and list(viewer["#"]) == list(range(1, 25))  # complete, file order
    assert at.selectbox(key="ercot_viewer_series").value == "TOTAL"
    at.selectbox(key="ercot_viewer_series").set_value("EAST").run(timeout=30)
    east = _table(at, "Value (as published)")
    missing = east[east["HourEnding"] == "05:00"].iloc[0]
    assert (missing["Value (as published)"], missing["Flags"]) == ("(missing)", "missing")
    # every series is reachable through the selector, so all 24 x 9 values can be listed
    assert len(at.selectbox(key="ercot_viewer_series").options) == 9
