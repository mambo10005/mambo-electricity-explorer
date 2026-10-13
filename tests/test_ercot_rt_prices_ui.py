"""Explore real-time price view, lesson 15, System Health view via AppTest (offline, SYNTHETIC)."""

from __future__ import annotations

import json
import re
from datetime import date

import pyarrow as pa
import pytest
from refresh_helpers import T0, Clock, patch_clock
from rt_price_fixtures import FakeRt, day_docs, interval_doc
from streamlit.testing.v1 import AppTest

from mambo_explorer import routes, system_health
from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.client import ErcotClient
from mambo_explorer.progress import Progress

EXPLORE = "from mambo_explorer.pages import render_page\nrender_page('explore')\n"
LEARN = "from mambo_explorer.pages import render_page\nrender_page('learn')\n"
HEALTH = "from mambo_explorer.pages import render_page\nrender_page('system-health')\n"
D9 = date(2026, 3, 9)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    patch_clock(monkeypatch, Clock())
    monkeypatch.setattr(system_health, "NOW", lambda: T0)
    return path


def fill(data_dir, docs, include_stored=False):
    c = ErcotClient(transport=FakeRt(docs), sleep=lambda s: None, max_requests=16)
    return rt.collect(rt.Selection(12, include_stored), c, rt.store(data_dir))


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return "\n".join(parts)


def _explore():
    at = AppTest.from_string(EXPLORE)
    at.session_state["explore_source"] = "ercot-rt-spp"
    return at.run(timeout=30)


def _item_table(at):
    return next(
        dict(zip(t.value["Item"], t.value["Value"], strict=True))
        for t in at.table
        if list(t.value.columns) == ["Item", "Value"]
        and "Interval (as published)" in list(t.value["Item"])
    )


def test_explore_empty_state(data_dir):
    at = _explore()
    assert not at.exception
    assert "No ERCOT real-time prices have been collected" in _texts(at)
    assert "Not a SCED LMP" in _texts(at) and len(at.get("vega_lite_chart")) == 0


def test_chart_tooltip_viewer_and_table_identify_the_same_interval(data_dir):
    docs = day_docs(D9, hours=(3, 4))
    docs.update(dict([interval_doc(D9, 5, 1, "7900", price="")]))
    fill(data_dir, docs)
    at = _explore()
    assert not at.exception
    (chart,) = at.get("vega_lite_chart")
    spec = json.loads(chart.proto.spec)
    enc = spec["layer"][1]["encoding"]
    assert enc["x"]["type"] == "ordinal" and "temporal" not in json.dumps(spec)
    assert [t["field"] for t in enc["tooltip"]] == ["label", "price", "revision"]
    data = pa.ipc.open_stream(chart.proto.data.data).read_all().to_pylist()
    points = {d["label"]: d["price"] for d in data}
    assert points["H04 I2 N"] == -5.0 and "H05 I1 N" not in points  # missing never drawn
    at.selectbox(key="explore_rt_interval").set_value(5).run(timeout=30)  # 6th stored interval
    viewer = _item_table(at)
    assert viewer["Interval (as published)"] == "H04 I2 N"
    assert (
        viewer["Price ($/MWh)"] == "-5.00"
        and viewer["DeliveryDate / DeliveryHour / DeliveryInterval / DSTFlag"]
        == "03/09/2026 / 4 / 2 / N"
    )
    table = next(
        t.value
        for t in at.table
        if "Interval (as published)" in t.value.columns
        and "Published by ERCOT" in t.value.columns
        and "Flags" in t.value.columns
    )
    row = table[table["Interval (as published)"] == "H04 I2 N"]
    assert list(row["Price ($/MWh)"]) == ["-5.00"]
    assert list(table[table["Interval (as published)"] == "H05 I1 N"]["Price ($/MWh)"]) == [
        "(missing)"
    ]
    text = _texts(at)
    assert "9 15-minute intervals stored" in text and "1 missing prices; 4 negative" in text
    assert "Hours with fewer than four stored intervals: 5" in text
    unescaped = re.compile(r"(?<!\\)\$")
    assert [
        t
        for t in [m.value for m in at.markdown] + [c.value for c in at.caption]
        if unescaped.search(t)
    ] == []


def test_revision_provenance(data_dir):
    fill(data_dir, dict([interval_doc(D9, 6, 2, "8101")]))
    fill(
        data_dir,
        dict(
            [interval_doc(D9, 6, 2, "8102", published="2026-03-09T09:00:00-05:00", price="88.88")]
        ),
    )
    at = _explore()
    trail = next(
        t.value for t in at.table if "Document" in t.value.columns and "Revision" in t.value.columns
    )
    assert list(trail["Revision"]) == [1, 2] and list(trail["Price"]) == ["28.00", "88.88"]


def _lesson():
    at = AppTest.from_string(LEARN)
    at.session_state["lesson_choice"] = "real-time-price"
    return at.run(timeout=30)


def test_lesson_15_without_data(data_dir):
    at = _lesson()
    assert not at.exception
    assert sum("Exercise unavailable" in i.value for i in at.info) == 5
    assert "The interval labels" in _texts(at)


def test_lesson_15_progress_and_a_new_interval_regenerates_questions(data_dir):
    fill(data_dir, day_docs(D9, hours=(3, 4)))
    at = _lesson()
    radios = [r for r in at.radio if r.label == "Your answer"]
    assert len(radios) == 5
    top = next(r for r in radios if any(o.startswith("H03 I4 N: 24.75") for o in r.options))
    top.set_value(next(o for o in top.options if o.startswith("H03 I4 N: 24.75")))
    [b for b in at.button if b.label == "Check answer"][radios.index(top)].click()
    at.run(timeout=30)
    assert any("Correct." in s.value for s in at.success)
    record = Progress(data_dir).exercise_record("real-time-price", "highest-interval")
    assert record["first_attempt_correct"] and record["snapshot_id"].startswith("rtprice-")
    fill(data_dir, dict([interval_doc(D9, 5, 1, "7999", price="99.00")]))
    at.run(timeout=30)
    assert any("regenerated" in w.value for w in at.warning)
    radios = [r for r in at.radio if r.label == "Your answer"]
    assert any(any(o.startswith("H05 I1 N: 99.00") for o in r.options) for r in radios)


def test_system_health_shows_the_real_time_dataset(data_dir):
    fill(data_dir, day_docs(D9))
    at = AppTest.from_string(HEALTH).run(timeout=30)
    at.radio(key="health_view").set_value("ercot-rt-spp").run(timeout=30)
    items = [
        dict(zip(t.value["Item"], t.value["Value"], strict=True))
        for t in at.table
        if list(t.value.columns) == ["Item", "Value"] and "Freshness" in list(t.value["Item"])
    ]
    assert len(items) == 1
    assert items[0]["Latest observation label"].startswith(
        "DeliveryDate 03/09/2026, DeliveryHour 2, DeliveryInterval 4"
    )
    assert "not compared with 96" in _texts(at)
