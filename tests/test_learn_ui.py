"""Learn page via Streamlit AppTest (headless; not a browser test). Data is SYNTHETIC."""

from datetime import date

import pytest
from eia_fixtures import FAKE_KEY, FakeEIA, synthetic_rows
from guards import assert_no_data_elements, assert_no_unauthorized_data
from streamlit.testing.v1 import AppTest

from mambo_explorer import calculations as calc
from mambo_explorer import exercises as ex
from mambo_explorer.collect import collect, plan_collection
from mambo_explorer.eia.client import EIAClient
from mambo_explorer.progress import Progress
from mambo_explorer.storage import Store

LEARN = "from mambo_explorer.pages import render_page\nrender_page('learn')\n"
TODAY = date(2026, 10, 11)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    return path


def _ingest(data_dir, days=3, overrides=None):
    plan = plan_collection(days=days, lookback_days=0, today=TODAY)
    rows = synthetic_rows(plan.fetch_start_day, plan.fetch_days, overrides=overrides)
    rows = [r for r in rows if not (r["type"] == "DF" and r["period"].startswith("2026-10-09T0"))]
    collect(
        plan, EIAClient(FAKE_KEY, transport=FakeEIA(rows), sleep=lambda s: None), Store(data_dir)
    )


def _open(lesson_id: str) -> AppTest:
    # The lesson radio uses a format_func, which AppTest.set_value cannot invert, so
    # select through session state (the same state the radio reads).
    at = AppTest.from_string(LEARN)
    at.session_state["lesson_choice"] = lesson_id
    at.run(timeout=30)
    assert not at.exception
    assert at.session_state["lesson_choice"] == lesson_id
    return at


def _text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [x.value for x in at.info] + [x.value for x in at.warning]
    parts += (
        [x.value for x in at.success] + [x.value for x in at.error] + [c.value for c in at.code]
    )
    return "\n".join(parts)


def _table(at: AppTest, column: str):
    """The first table that has the given column (robust to table order)."""
    return next(tb.value for tb in at.table if column in tb.value.columns)


def _answer(at: AppTest, form_index: int, option: str) -> AppTest:
    radios = [r for r in at.radio if r.label == "Your answer"]
    radios[form_index].set_value(option)
    [b for b in at.button if b.label == "Check answer"][form_index].click()
    return at.run(timeout=30)


def test_lesson_list_shows_eight_lessons_in_order(data_dir):
    at = AppTest.from_string(LEARN).run(timeout=30)
    assert not at.exception
    assert at.radio(key="lesson_choice").options == [
        "1. Power versus energy (MW and MWh)",
        "2. Reading an actual demand series",
        "3. Comparing demand with a published forecast",
        "4. Understanding missing observations",
        "5. Power flow versus economic dispatch",
        "6. Why modeled prices differ by location",
        "7. When one marginal number is not verified",
        "8. From scheduled energy to settlement",
    ]
    status = _table(at, "Status")
    assert list(status["Status"]) == ["viewed"] + ["not started"] * 7
    assert "Not yet reviewed by a person" in _text(at)


@pytest.mark.parametrize(
    "lesson_id", ["power-vs-energy", "reading-demand", "demand-vs-forecast", "missing-observations"]
)
def test_every_lesson_readable_without_observations_and_no_charts(data_dir, lesson_id):
    at = _open(lesson_id)
    assert_no_data_elements(at)  # no observations -> no charts, synthetic or otherwise
    assert at.subheader and any(s.value == "Limitations" for s in at.subheader)
    if lesson_id != "power-vs-energy":
        assert "No observations have been collected" in _text(at)
        assert "mambo collect --dry-run" in _text(at)


def test_power_energy_lesson_is_synthetic_and_chart_free_even_with_data(data_dir):
    _ingest(data_dir)
    at = _open("power-vs-energy")
    assert_no_data_elements(at)
    assert "SYNTHETIC" in _text(at)
    assert "1,000 MWh" in str(_table(at, "Given").to_dict())


def test_demand_lesson_populated_chart_with_accessible_table(data_dir):
    _ingest(data_dir)
    at = _open("reading-demand")
    assert len(at.get("vega_lite_chart")) == 1
    assert_no_unauthorized_data(at, "learn")
    summary = _table(at, "Measure")
    assert "Highest value" in list(summary["Measure"])
    assert len(_table(at, "Revision")) == 72  # chart data table: one row per actual-demand hour
    assert "not** a set of readings from customers' meters" in _text(at)


def test_forecast_lesson_reports_pairs_and_exclusions(data_dir):
    _ingest(data_dir)
    at = _open("demand-vs-forecast")
    table = _table(at, "Measure")
    measures = dict(zip(table["Measure"], table["Value"], strict=True))
    assert measures["Excluded hours"] == "10"  # synthetic: DF removed for 2026-10-09T00..09
    assert measures["Matched valid pairs (hours)"] == str(72 - 10)
    assert "not necessarily the forecast as first issued" in _text(at)


def test_missing_lesson_lists_absent_runs_by_utc_label(data_dir):
    _ingest(data_dir)
    at = _open("missing-observations")
    assert_no_data_elements(at)
    runs = _table(at, "First absent label (UTC)")
    assert list(runs["First absent label (UTC)"]) == ["2026-10-09T00"]
    assert list(runs["Labels"]) == [10]


def test_exercise_interaction_records_progress_states(data_dir):
    _ingest(data_dir)
    at = _open("demand-vs-forecast")
    obs = calc.load_observations(
        Store(data_dir), calc.Selection("ERCO", "2026-10-08T00", "2026-10-10T23")
    )
    sel = calc.Selection("ERCO", "2026-10-08T00", "2026-10-10T23")
    sign, mae = ex.error_sign("error-sign", obs, sel), ex.mae_value("mae", obs, sel)
    wrong = next(o for i, o in enumerate(sign.options) if i != sign.answer_index)
    at = _answer(at, 0, wrong)
    assert any("Not quite" in e.value for e in at.error)
    assert "Worked explanation" in _text(at)
    progress = Progress(data_dir)
    assert (
        progress.lesson_state("demand-vs-forecast", ["error-sign", "mae"]) == "exercise completed"
    )
    at = _answer(at, 1, mae.options[mae.answer_index])
    assert any("Correct" in s.value for s in at.success)
    # First attempt on error-sign was wrong, so understanding is not demonstrated.
    assert (
        progress.lesson_state("demand-vs-forecast", ["error-sign", "mae"]) == "exercise completed"
    )


def test_window_change_regenerates_exercise(data_dir):
    _ingest(data_dir)
    at = _open("reading-demand")
    before = [r for r in at.radio if r.label == "Your answer"][0].options
    at.date_input(key="learn_window").set_value((date(2026, 10, 10), date(2026, 10, 10))).run(
        timeout=30
    )
    after = [r for r in at.radio if r.label == "Your answer"][0].options
    assert before != after
    assert "exercise was regenerated" in _text(at)


def test_technical_toggle_prerequisite_navigation_and_bookmark(data_dir):
    at = _open("reading-demand")
    assert not any(s.value == "Technical detail" for s in at.subheader)
    at.toggle(key="technical_detail").set_value(True).run(timeout=30)
    assert any(s.value == "Technical detail" for s in at.subheader)
    at.toggle(key="bookmark::reading-demand").set_value(True).run(timeout=30)
    assert Progress(data_dir).bookmarked("reading-demand")
    at.button(key="prereq::reading-demand::power-vs-energy").click().run(timeout=30)
    assert at.session_state["lesson_choice"] == "power-vs-energy"
    assert at.header[0].value == "Power versus energy (MW and MWh)"


def test_deep_link_opens_requested_lesson(data_dir):
    at = AppTest.from_string(LEARN)
    at.query_params["lesson"] = "missing-observations"
    at.run(timeout=30)
    assert at.header[0].value == "Understanding missing observations"


def test_status_table_updates_in_the_same_interaction_as_the_answer(data_dir):
    _ingest(data_dir)
    at = _open("demand-vs-forecast")
    options = [r for r in at.radio if r.label == "Your answer"][0].options
    at = _answer(at, 0, options[0])
    status = _table(at, "Status")
    row = status[status["Lesson"].str.startswith("3.")]
    assert list(row["Status"]) == ["exercise completed"]


def test_coverage_table_is_narrow_and_counts_each_series_separately(data_dir):
    _ingest(data_dir)
    at = _open("missing-observations")
    table = _table(at, "Day-ahead forecast")
    assert list(table.columns) == ["Measure", "Actual demand", "Day-ahead forecast"]
    absent = table[table["Measure"] == "Absent rows"]
    assert (int(absent["Actual demand"].iloc[0]), int(absent["Day-ahead forecast"].iloc[0])) == (
        0,
        10,
    )
