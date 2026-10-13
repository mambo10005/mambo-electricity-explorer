"""Timestamp display (Stage 17, ADR 0015): the same source observation shows the same UTC label
on the axis, in the tooltip, and in the table whatever the browser's time zone would be.

These are display tests. They say nothing about whether a label marks the start or the end of
an hour (unverified for the EIA API field) or about ERCOT's time zone (not stated).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from eia_fixtures import FAKE_KEY, FakeEIA, synthetic_rows
from generation_fixtures import FakeGeneration
from streamlit.testing.v1 import AppTest

from mambo_explorer import calculations as calc
from mambo_explorer import generation, routes, timeview
from mambo_explorer.collect import collect, plan_collection
from mambo_explorer.eia import dataset as ds
from mambo_explorer.eia.client import EIAClient
from mambo_explorer.storage import Store

LA, SEOUL = ZoneInfo("America/Los_Angeles"), ZoneInfo("Asia/Seoul")
# Labels whose browser-local rendering would differ from the UTC label:
FIXTURES = {
    "utc-midnight": "2026-03-08T00",  # 2026-03-07 16:00 in LA, 09:00 next day in Seoul
    "la-date-boundary": "2026-03-08T08",  # exactly 00:00 PST on 2026-03-08
    "seoul-date-boundary": "2026-03-07T15",  # exactly 00:00 KST on 2026-03-08
    "dst-transition": "2026-03-08T10",  # 03:00 PDT: the hour after the US spring-forward
}


def _local(label: str, zone) -> str:
    return ds.parse_period(label).astimezone(zone).strftime("%Y-%m-%dT%H")


def test_fixtures_sit_on_the_boundaries_they_claim():
    assert _local(FIXTURES["la-date-boundary"], LA) == "2026-03-08T00"
    assert _local(FIXTURES["seoul-date-boundary"], SEOUL) == "2026-03-08T00"
    assert _local(FIXTURES["utc-midnight"], LA) == "2026-03-07T16"
    assert (
        ds.parse_period(FIXTURES["dst-transition"]).astimezone(LA).utcoffset().total_seconds()
        == -7 * 3600
    )
    assert ds.parse_period("2026-03-08T09").astimezone(LA).utcoffset().total_seconds() == -8 * 3600
    # Every fixture would be displayed with a different date or hour in at least one zone.
    for label in FIXTURES.values():
        assert {_local(label, LA), _local(label, SEOUL)} != {label}


# --- serialized chart configuration -------------------------------------------------------


def _chart_spec(rows, **kw):
    script = (
        "from mambo_explorer.timeview import utc_label_chart\n"
        f"utc_label_chart({rows!r}, **{kw!r})\n"
    )
    at = AppTest.from_string(script).run(timeout=30)
    assert not at.exception
    element = at.get("vega_lite_chart")[0]
    return json.loads(element.proto.spec), element


def test_axis_is_a_utc_scale_and_tooltip_carries_the_verbatim_label():
    rows = [{"period": p, "v": i} for i, p in enumerate(FIXTURES.values())]
    spec, _ = _chart_spec(rows, value_field="v", value_title="V (MWh)", colors=["#1f77b4"])
    x = spec["encoding"]["x"]
    assert x["type"] == "temporal" and x["scale"] == {"type": "utc"}
    assert x["axis"]["title"] == timeview.AXIS_TITLE and x["axis"]["format"] == timeview.AXIS_FORMAT
    tooltip = spec["encoding"]["tooltip"]
    assert tooltip[0] == {"field": "period", "title": timeview.AXIS_TITLE, "type": "nominal"}
    assert tooltip[1]["field"] == "v" and tooltip[1]["type"] == "quantitative"
    assert "timeUnit" not in x  # no re-binning of labels


def test_series_chart_keeps_colors_and_domain():
    rows = [
        {"period": "2026-03-08T00", "Series": "A", "v": 1},
        {"period": "2026-03-08T00", "Series": "B", "v": 2},
    ]
    spec, _ = _chart_spec(
        rows,
        value_field="v",
        value_title="V",
        series_field="Series",
        series_domain=["A", "B"],
        colors=["#1f77b4", "#d95f02"],
        mark="bar",
        stack=True,
    )
    assert spec["encoding"]["color"]["scale"] == {
        "domain": ["A", "B"],
        "range": ["#1f77b4", "#d95f02"],
    }
    assert spec["encoding"]["y"]["stack"] == "zero" and spec["mark"]["type"] == "bar"
    assert [t["field"] for t in spec["encoding"]["tooltip"]] == ["Series", "period", "v"]


def test_instants_are_aware_utc_never_naive():
    frame = timeview.label_frame([{"period": p} for p in FIXTURES.values()])
    for label, instant in zip(frame["period"], frame["instant"], strict=True):
        assert instant.tzinfo is not None and instant.utcoffset().total_seconds() == 0
        assert instant.strftime("%Y-%m-%dT%H") == label


def test_empty_rows_draw_nothing():
    at = AppTest.from_string(
        "from mambo_explorer.timeview import utc_label_chart\n"
        "assert utc_label_chart([], value_field='v', value_title='V') is None\n"
    ).run(timeout=30)
    assert not at.exception and len(at.get("vega_lite_chart")) == 0


def test_format_utc_marks_utc_and_converts_offsets():
    assert timeview.format_utc("2026-03-08T00:30:00+00:00") == "2026-03-08 00:30 UTC"
    assert timeview.format_utc(datetime(2026, 3, 7, 16, 30, tzinfo=LA)) == "2026-03-08 00:30 UTC"
    assert (
        timeview.format_utc("2026-03-08T00:30:00") == "2026-03-08 00:30 UTC"
    )  # store stamps are UTC
    assert timeview.format_utc(None) == "unknown"
    assert (
        timeview.format_utc("2026-03-08T00:30:05+09:00", seconds=True) == "2026-03-07 15:30:05 UTC"
    )


# --- the corrected views, end to end --------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    plan = plan_collection(days=2, lookback_days=0, today=datetime(2026, 3, 9, tzinfo=UTC).date())
    rows = synthetic_rows(
        plan.fetch_start_day, plan.fetch_days, overrides={("D", "2026-03-08T08"): "41234"}
    )
    collect(
        plan,
        EIAClient(FAKE_KEY, transport=FakeEIA(rows), sleep=lambda s: None, max_requests=12),
        Store(path),
    )
    gplan = generation.plan_generation(
        days=2, lookback_days=0, today=datetime(2026, 3, 9, tzinfo=UTC).date()
    )
    generation.collect(
        gplan,
        EIAClient(FAKE_KEY, transport=FakeGeneration(), sleep=lambda s: None, max_requests=12),
        generation.store(path),
    )
    return path


def _dataset_rows(element) -> list[dict]:
    """Rows of the chart's dataset as the frontend receives them (Arrow), as plain dicts."""
    import pyarrow as pa

    tables = [pa.ipc.open_stream(d.data.data).read_all() for d in element.proto.datasets]
    return [r for t in tables for r in t.to_pylist()]


def test_lesson_2_chart_tooltip_and_table_show_the_same_utc_label(data_dir):
    at = AppTest.from_string("from mambo_explorer.pages import render_page\nrender_page('learn')\n")
    at.session_state["lesson_choice"] = "reading-demand"
    at.run(timeout=30)
    assert not at.exception
    charts = at.get("vega_lite_chart")
    assert len(charts) == 1  # lesson 2 draws exactly one chart: the demand series
    chart = charts[0]
    spec = json.loads(chart.proto.spec)
    assert spec["encoding"]["x"]["scale"] == {"type": "utc"}
    rows = _dataset_rows(chart)
    row = next(r for r in rows if r["period"] == FIXTURES["la-date-boundary"])
    assert row["Actual demand (MWh)"] == 41234.0
    instant = row["instant"]
    assert instant.astimezone(UTC).strftime("%Y-%m-%dT%H") == FIXTURES["la-date-boundary"]
    assert (
        instant.astimezone(LA).strftime("%Y-%m-%dT%H") != FIXTURES["la-date-boundary"]
    )  # would mislead
    table = next(
        t.value
        for t in at.table
        if "Label (UTC)" in t.value.columns and "Revision" in t.value.columns
    )
    matching = table[table["Label (UTC)"] == FIXTURES["la-date-boundary"]]
    assert list(matching["Value"]) == ["41234"]


def test_explore_demand_and_generation_charts_use_utc_scale_and_label_tooltips(data_dir):
    at = AppTest.from_string(
        "from mambo_explorer.pages import render_page\nrender_page('explore')\n"
    ).run(timeout=30)
    assert not at.exception
    spec = json.loads(next(iter(at.get("vega_lite_chart"))).proto.spec)
    assert spec["encoding"]["x"]["scale"] == {"type": "utc"}
    assert spec["encoding"]["tooltip"][1]["field"] == "period"
    at.session_state["explore_source"] = "eia-generation"
    at.run(timeout=30)
    spec = json.loads(next(iter(at.get("vega_lite_chart"))).proto.spec)
    assert spec["encoding"]["x"]["scale"] == {"type": "utc"} and spec["mark"]["type"] == "bar"
    assert [t["field"] for t in spec["encoding"]["tooltip"]][:2] == ["Category", "period"]


def test_observation_selection_is_unchanged_by_display(data_dir):
    store = Store(data_dir)
    sel = calc.Selection("ERCO", "2026-03-07T00", "2026-03-08T23")
    obs = calc.load_observations(store, sel)
    assert len(obs) == 96 and calc.snapshot_id(obs, sel) == calc.snapshot_id(obs, sel)
    assert {o.period for o in obs if o.metric == "D"} == set(
        calc.labels_between(sel.start_period, sel.end_period)
    )


def test_no_streamlit_builtin_chart_is_fed_datetimes():
    """Every time-axis chart goes through utc_label_chart; built-in charts cannot pin UTC."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "mambo_explorer"
    offenders = []
    for path in src.rglob("*.py"):
        text = path.read_text("utf-8")
        if path.name == "timeview.py":
            continue
        for call in re.findall(
            r"st\.(?:line_chart|bar_chart|area_chart)\((.*?)\)\n", text, re.DOTALL
        ):
            if "parse_period" in call or "datetime" in call or "strptime" in call:
                offenders.append(path.name)
    assert offenders == []
