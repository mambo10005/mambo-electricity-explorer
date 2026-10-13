"""Explore price view, lesson 14, and System Health price view via AppTest (offline, SYNTHETIC)."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest
from price_fixtures import FakePrices, day_doc
from refresh_helpers import T0, Clock, patch_clock
from streamlit.testing.v1 import AppTest

from mambo_explorer import routes, system_health
from mambo_explorer.ercot import prices as px
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


def fill(data_dir, doc_id="501", published=None, **kw):
    docs = dict([day_doc(D9, doc_id, published, **kw)])
    c = ErcotClient(transport=FakePrices(docs), sleep=lambda s: None, max_requests=6)
    return px.collect(px.Selection(latest=1), c, px.store(data_dir))


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return "\n".join(parts)


def _explore():
    at = AppTest.from_string(EXPLORE)
    at.session_state["explore_source"] = "ercot-dam-spp"
    return at.run(timeout=30)


def _price_table(at):
    return next(t.value for t in at.table if "Price ($/MWh)" in t.value.columns)


def test_explore_empty_state(data_dir):
    at = _explore()
    assert not at.exception
    text = _texts(at)
    assert "No ERCOT day-ahead prices have been collected" in text
    assert "collect --source ercot-dam-spp" in text and "Not a retail tariff" in text
    assert len(at.get("vega_lite_chart")) == 0


def test_explore_chart_tooltip_and_table_use_the_same_source_labels(data_dir):
    fill(data_dir, overrides={("05:00", "N"): ""})
    at = _explore()
    assert not at.exception
    (chart,) = at.get("vega_lite_chart")
    spec = json.loads(chart.proto.spec)
    line = spec["layer"][1]["encoding"]
    assert line["x"]["type"] == "ordinal" and line["x"]["sort"] == {"field": "order"}
    assert line["x"]["field"] == "label" and "temporal" not in json.dumps(spec)
    assert [t["field"] for t in line["tooltip"]] == ["label", "price", "revision"]
    import pyarrow as pa

    # st.vega_lite_chart ships its rows in proto.data (Arrow), not in named datasets.
    data = pa.ipc.open_stream(chart.proto.data.data).read_all().to_pylist()
    table = _price_table(at)
    chart_rows = {r["label"]: r["price"] for r in data}
    assert "05:00 N" not in chart_rows  # missing price is not drawn as zero
    assert chart_rows["03:00 N"] == -2.5
    row = table[(table["HourEnding"] == "03:00") & (table["DSTFlag"] == "N")]
    assert list(row["Price ($/MWh)"]) == ["-2.50"]
    missing = table[table["HourEnding"] == "05:00"]
    assert list(missing["Price ($/MWh)"]) == ["(missing)"]
    text = _texts(at)
    assert "24 hourly rows for HB_NORTH" in text and "1 missing; 2 negative" in text
    assert (
        "Finality:** Not determined" in text and "document 501 at 2026-03-08T12:46:27-05:00" in text
    )
    unescaped = re.compile(r"(?<!\\)\$")
    assert [
        t
        for t in [m.value for m in at.markdown] + [c.value for c in at.caption]
        if unescaped.search(t)
    ] == []


def test_explore_revision_provenance_lists_every_version(data_dir):
    fill(data_dir)
    fill(data_dir, "601", "2026-03-08T15:00:00-05:00", overrides={("10:00", "N"): "99.99"})
    at = _explore()
    trail = next(
        t.value for t in at.table if "Revision" in t.value.columns and "Document" in t.value.columns
    )
    ten = trail[trail["HourEnding"] == "10:00"]
    assert list(ten["Revision"]) == [1, 2] and list(ten["Price"]) == ["45.00", "99.99"]
    assert list(ten["Document"]) == ["501", "601"]


def _lesson():
    at = AppTest.from_string(LEARN)
    at.session_state["lesson_choice"] = "day-ahead-price"
    return at.run(timeout=30)


def test_lesson_14_without_data(data_dir):
    at = _lesson()
    assert not at.exception
    assert sum("Exercise unavailable" in i.value for i in at.info) == 5
    assert "Negative prices" in _texts(at)


def test_lesson_14_exercises_record_progress_and_a_revision_regenerates_them(data_dir):
    fill(data_dir)
    at = _lesson()
    radios = [r for r in at.radio if r.label == "Your answer"]
    assert len(radios) == 5
    top = next(r for r in radios if any(o.startswith("23:00 N: 64.50") for o in r.options))
    top.set_value(next(o for o in top.options if o.startswith("23:00 N: 64.50")))
    [b for b in at.button if b.label == "Check answer"][radios.index(top)].click()
    at.run(timeout=30)
    assert any("Correct." in s.value for s in at.success)
    first = Progress(data_dir).exercise_record("day-ahead-price", "highest-hour")
    assert first["first_attempt_correct"] and first["snapshot_id"].startswith("price-")
    fill(data_dir, "601", "2026-03-08T15:00:00-05:00", overrides={("10:00", "N"): "99.99"})
    at.run(timeout=30)
    assert any("regenerated" in w.value for w in at.warning)
    radios = [r for r in at.radio if r.label == "Your answer"]
    assert any(any(o.startswith("10:00 N: 99.99") for o in r.options) for r in radios)


def test_system_health_shows_the_price_dataset(data_dir):
    fill(data_dir)
    at = AppTest.from_string(HEALTH).run(timeout=30)
    assert not at.exception
    at.radio(key="health_view").set_value("ercot-dam-spp").run(timeout=30)
    items = [
        dict(zip(t.value["Item"], t.value["Value"], strict=True))
        for t in at.table
        if list(t.value.columns) == ["Item", "Value"] and "Freshness" in list(t.value["Item"])
    ]
    assert len(items) == 1
    assert items[0]["Latest observation label"].startswith(
        "DeliveryDate 03/09/2026, HourEnding 24:00"
    )
    assert items[0]["Publication timestamp"].startswith("2026-03-08T12:46:27-05:00")
    assert "Finality: Not determined" in _texts(at)
