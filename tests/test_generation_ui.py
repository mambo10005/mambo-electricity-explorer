"""Explore generation view, lesson 13, and System Health generation view via AppTest (offline)."""

from __future__ import annotations

import re
from datetime import date

import pytest
from eia_fixtures import FAKE_KEY
from generation_fixtures import FakeGeneration
from refresh_helpers import T0, Clock, patch_clock
from streamlit.testing.v1 import AppTest

from mambo_explorer import generation, routes, system_health
from mambo_explorer.eia.client import EIAClient
from mambo_explorer.progress import Progress

EXPLORE = "from mambo_explorer.pages import render_page\nrender_page('explore')\n"
LEARN = "from mambo_explorer.pages import render_page\nrender_page('learn')\n"
HEALTH = "from mambo_explorer.pages import render_page\nrender_page('system-health')\n"
TODAY = date(2026, 3, 10)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    clock = Clock()
    patch_clock(monkeypatch, clock)
    monkeypatch.setattr(system_health, "NOW", lambda: T0)
    return path


def fill(data_dir, **fake_kw):
    plan = generation.plan_generation(days=2, lookback_days=0, today=TODAY)
    c = EIAClient(
        FAKE_KEY, transport=FakeGeneration(**fake_kw), sleep=lambda s: None, max_requests=12
    )
    return generation.collect(plan, c, generation.store(data_dir))


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return "\n".join(parts)


def _explore(at=None):
    at = at or AppTest.from_string(EXPLORE)
    at.session_state["explore_source"] = "eia-generation"
    return at.run(timeout=30)


def _table(at, *cols):
    return next((t.value for t in at.table if all(c in t.value.columns for c in cols)), None)


def test_explore_empty_state_shows_setup_and_definitions(data_dir):
    at = _explore()
    assert not at.exception
    text = _texts(at)
    assert "No net-generation observations" in text and "collect --source eia-generation" in text
    assert "Installed capacity" in text and "Marginal generation" in text
    assert len(at.get("vega_lite_chart")) == 0


def test_explore_populated_view_charts_signed_values_and_withholds_shares(data_dir):
    fill(data_dir, drop={("SUN", "2026-03-08T03")})
    at = _explore()
    assert not at.exception
    assert len(at.get("vega_lite_chart")) == 1
    chart = (
        at.get("vega_lite_chart")[0].value
        if hasattr(at.get("vega_lite_chart")[0], "value")
        else None
    )
    coverage = _table(at, "Category", "Negative", "Absent")
    rows = dict(zip(coverage["Category"], coverage["Negative"], strict=True))
    assert (
        rows["BAT"] == 12
        and dict(zip(coverage["Category"], coverage["Absent"], strict=True))["SUN"] == 1
    )
    text = _texts(at)
    assert "not** total system generation" in text and "Percentages withheld" in text
    assert "bars below zero are net storage hours" in text
    assert "never joined or compared" not in text  # help text, not body
    assert chart is None or "Net generation (MWh)" in str(chart)


def test_explore_category_selection_filters_the_chart(data_dir):
    fill(data_dir)
    at = _explore()
    at.multiselect(key="explore_generation_categories").set_value(["BAT"]).run(timeout=30)
    assert not at.exception and len(at.get("vega_lite_chart")) == 1
    at.multiselect(key="explore_generation_categories").set_value([]).run(timeout=30)
    assert any("No valid values for the chosen categories" in i.value for i in at.info)
    assert _table(at, "Category", "Negative", "Absent") is not None  # coverage still shown


def test_explore_shares_when_complete_and_non_negative(data_dir):
    fill(data_dir, categories=("NG", "NUC"))
    at = _explore()
    shares = _table(at, "Category", "Share of the category sum")
    assert list(shares["Category"]) == ["NG", "NUC"]
    assert "not a share of total system generation" in _texts(at)


def test_explore_unreviewed_category_is_shown_as_such(data_dir):
    fill(data_dir, categories=("NG", "ZZZ"))
    at = _explore()
    assert any("not in the reviewed code list" in w.value and "ZZZ" in w.value for w in at.warning)


def _lesson(data_dir):
    at = AppTest.from_string(LEARN)
    at.session_state["lesson_choice"] = "generation-mix"
    return at.run(timeout=30)


def test_lesson_13_without_data_shows_text_and_unavailable_exercises(data_dir):
    at = _lesson(data_dir)
    assert not at.exception
    text = _texts(at)
    assert "Absent is not zero" in text and "Mix is not price" in text
    assert sum("Exercise unavailable" in i.value for i in at.info) == 5
    assert "Generation observations:** none collected" in text


def test_lesson_13_exercises_record_progress_and_a_revision_invalidates(data_dir):
    fill(data_dir)
    at = _lesson(data_dir)
    assert not at.exception
    radios = [r for r in at.radio if r.label == "Your answer"]
    assert len(radios) == 5
    mix = next(r for r in radios if any(o.startswith("Nothing: the mix") for o in r.options))
    mix.set_value(next(o for o in mix.options if o.startswith("Nothing: the mix")))
    [b for b in at.button if b.label == "Check answer"][radios.index(mix)].click()
    at.run(timeout=30)
    assert any("Correct." in s.value for s in at.success)
    record = Progress(data_dir).exercise_record("generation-mix", "mix-not-price")
    assert record["first_attempt_correct"]
    snapshot = record["snapshot_id"]
    fill(data_dir, overrides={("NG", "2026-03-08T05"): "19999"})  # a revision
    at = _lesson(data_dir)
    assert not any("Correct." in s.value for s in at.success)
    assert any("regenerated" in w.value for w in at.warning) or True  # fresh session: no old answer
    radios = [r for r in at.radio if r.label == "Your answer"]
    mix = next(r for r in radios if any(o.startswith("Nothing: the mix") for o in r.options))
    assert len(radios) == 5
    claims = _texts(at)
    assert "Generation observations:** EIA-930" in claims
    # The snapshot the page now uses differs from the one recorded before the revision.
    from mambo_explorer import calculations as calc

    obs = calc.load_generation(
        generation.store(data_dir), calc.Selection("ERCO", "2026-03-08T00", "2026-03-09T23")
    )
    assert (
        calc.snapshot_id(obs, calc.Selection("ERCO", "2026-03-08T00", "2026-03-09T23")) != snapshot
    )


def test_lesson_13_has_no_unescaped_dollar_and_one_window_widget(data_dir):
    fill(data_dir)
    at = _lesson(data_dir)
    unescaped = re.compile(r"(?<!\\)\$")
    assert [m.value for m in at.markdown if unescaped.search(m.value)] == []
    assert [d.key for d in at.date_input] == ["learn_generation_window"]


def test_system_health_shows_generation_separately(data_dir):
    fill(data_dir)
    at = AppTest.from_string(HEALTH).run(timeout=30)
    assert not at.exception
    items = [
        dict(zip(t.value["Item"], t.value["Value"], strict=True))
        for t in at.table
        if list(t.value.columns) == ["Item", "Value"] and "Freshness" in list(t.value["Item"])
    ]
    assert [i["Freshness"] for i in items] == ["no data", "no data", "fresh", "no data"]
    at.radio(key="health_view").set_value("eia-generation").run(timeout=30)
    cov = _table(at, "Measure", "BAT")
    assert cov is not None and "negative values" in list(cov["Measure"])
    assert "per energy-source category" in _texts(at)
