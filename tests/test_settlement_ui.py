"""Finance page and settlement lesson via AppTest (headless, offline). Inputs are SYNTHETIC."""

import re

import pytest
from guards import assert_no_unauthorized_data
from streamlit.testing.v1 import AppTest

from mambo_explorer import routes
from mambo_explorer.modeling import cases as mc
from mambo_explorer.progress import Progress

FINANCE = "from mambo_explorer.pages import render_page\nrender_page('finance')\n"
LEARN = "from mambo_explorer.pages import render_page\nrender_page('learn')\n"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    return path


def _table(at, column):
    return next((t.value for t in at.table if column in t.value.columns), None)


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return parts


def _amounts(at):
    t = _table(at, "Energy (MWh)")  # the settlement table (the basis tables have no such column)
    return None if t is None else dict(zip(t["Component"], t["Amount ($)"], strict=True))


def test_finance_page_shows_components_total_and_role_readings(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    assert not at.exception
    assert _amounts(at) == {"Day-ahead": "4,000.00", "Deviation": "1,100.00", "Total": "5,100.00"}
    roles = _table(at, "Reading of the total")
    assert list(roles["Role"]) == ["Buyer", "Seller"]
    text = "\n".join(_texts(at))
    assert "not implemented" in text and "Neither is a market settlement engine, an invoice" in text
    status = _table(at, "Feature")
    assert dict(zip(status["ID"], status["Status"], strict=True)) == {
        "FIN-01": "planned",
        "FIN-02": "planned",
        "FIN-03": "done",
        "FIN-04": "done",
    }
    assert_no_unauthorized_data(at, "finance")
    assert not data_dir.exists() or not any(data_dir.rglob("*.parquet"))


def test_changing_inputs_recomputes_and_invalid_inputs_show_no_numbers(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    at.number_input(key="finance_q_rt").set_value(80.0).run(timeout=30)
    assert _amounts(at)["Total"] == "2,900.00"
    at.number_input(key="finance_p_rt").set_value(-20.0).run(timeout=30)
    assert _amounts(at)["Deviation"] == "400.00"  # (80 − 100) × (−20)
    at.radio(key="finance_mode").set_value("average power (MW) × duration").run(timeout=30)
    assert _amounts(at) is None  # no duration yet: no stale numbers
    assert any("duration in hours is required" in e.value for e in at.error)
    at.number_input(key="finance_hours").set_value(2.0).run(timeout=30)
    # 100 MW and 120 MW for 2 h: 200 and 240 MWh; 200·40 + 40·(−20) = 7,200
    assert _amounts(at)["Total"] == "7,200.00"


def test_import_offers_only_verified_runs_and_labels_the_price_modeled(data_dir):
    records = mc.run_lesson_runs(["congested", "breakpoint"], {})
    at = AppTest.from_string(FINANCE)
    at.session_state["model_runs"] = records
    at.run(timeout=30)
    options = at.selectbox(key="finance_imp_run").options
    assert len(options) == 1 and records["congested"].run_id[-8:] in options[0]
    at.radio(key="finance_imp_bus").set_value("C")
    at.radio(key="finance_imp_stage").set_value("real-time price")
    at.button(key="finance_imp_go").click().run(timeout=30)
    at.run(timeout=30)
    assert at.number_input(key="finance_p_rt").value == pytest.approx(40.0)
    text = "\n".join(_texts(at))
    assert "Real-time price: modeled (run" in text and records["congested"].run_id in text
    assert "price verified by the per-run check" in text and "not an ISO price" in text
    # Editing the price by hand drops the modeled label: it is synthetic again.
    at.number_input(key="finance_p_rt").set_value(41.0).run(timeout=30)
    assert "Real-time price: synthetic" in "\n".join(_texts(at))


def test_no_verified_runs_means_no_import_but_manual_inputs_still_work(data_dir):
    records = mc.run_lesson_runs(["breakpoint"], {})
    at = AppTest.from_string(FINANCE)
    at.session_state["model_runs"] = records
    at.run(timeout=30)
    assert not [s for s in at.selectbox if s.key == "finance_imp_run"]
    assert any("No verified economic-dispatch runs" in i.value for i in at.info)
    assert _amounts(at)["Total"] == "5,100.00"


def _open_lesson():
    at = AppTest.from_string(LEARN)
    at.session_state["lesson_choice"] = "energy-settlement"
    return at.run(timeout=30)


def test_lesson_exercises_record_progress_and_reset_when_inputs_change(data_dir):
    at = _open_lesson()
    assert not at.exception
    radios = [r for r in at.radio if r.label == "Your answer"]
    assert len(radios) == 5
    total = next(r for r in radios if "5,100 synthetic $" in r.options)
    total.set_value("5,100 synthetic $")
    index = radios.index(total)
    [b for b in at.button if b.label == "Check answer"][index].click()
    at.run(timeout=30)
    assert any("Correct." in s.value for s in at.success)
    record = Progress(data_dir).exercise_record("energy-settlement", "total-amount")
    assert record["first_attempt_correct"] is True and record["snapshot_id"].startswith("settle-")
    # New inputs: a new question; the old verdict is not shown against new numbers.
    at.number_input(key="learn_energy-settlement_q_rt").set_value(80.0).run(timeout=30)
    assert not any("Correct." in s.value for s in at.success)
    assert any("2,900 synthetic $" in r.options for r in at.radio if r.label == "Your answer")


def test_invalid_lesson_inputs_make_every_exercise_unavailable(data_dir):
    at = _open_lesson()
    at.radio(key="learn_energy-settlement_mode").set_value("average power (MW) × duration")
    at.run(timeout=30)
    assert _amounts(at) is None
    assert sum("Exercise unavailable" in i.value for i in at.info) == 5
    assert not [r for r in at.radio if r.label == "Your answer"]


def test_rendered_markdown_has_no_unescaped_dollar(data_dir):
    unescaped = re.compile(r"(?<!\\)\$")
    for script in (FINANCE, None):
        at = AppTest.from_string(script).run(timeout=30) if script else _open_lesson()
        at.toggle(key="technical_detail").set_value(True).run(
            timeout=30
        ) if script is None else None
        assert [t for t in _texts(at) if unescaped.search(t)] == []
        labels = [n.label for n in at.number_input]
        assert all(lb.count("$") <= 1 and "\\" not in lb for lb in labels)


def test_finance_links_to_the_lesson(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    at.button(key="finance_lesson").click().run(timeout=30)
    assert at.session_state[routes.HANDOFF_LESSON] == "energy-settlement"
