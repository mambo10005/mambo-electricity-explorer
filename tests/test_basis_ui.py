"""Basis calculator on the Finance page and lesson 9 via AppTest (offline). SYNTHETIC inputs."""

import re

import pytest
from streamlit.testing.v1 import AppTest

from mambo_explorer import routes
from mambo_explorer.modeling import cases as mc
from mambo_explorer.progress import Progress

FINANCE = "from mambo_explorer.pages import render_page\nrender_page('finance')\n"
LEARN = "from mambo_explorer.pages import render_page\nrender_page('learn')\n"
P = "finance_basis"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    return path


def _flows(at):
    t = next(
        (t.value for t in at.table if "Item" in t.value.columns and "Formula" in t.value.columns),
        None,
    )
    return None if t is None else dict(zip(t["Item"], t["Amount ($)"], strict=True))


def _parts(at):
    t = next(
        (
            t.value
            for t in at.table
            if "Component" in t.value.columns and "Formula" in t.value.columns
        ),
        None,
    )
    return None if t is None else dict(zip(t["Component"], t["Amount ($)"], strict=True))


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return parts


def test_finance_shows_cash_flows_decomposition_and_hedge_effect(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    assert not at.exception
    assert _flows(at) == {
        "Physical purchase cost": "6,000.00",
        "Hedge receipt": "800.00",
        "Net buyer cost": "5,200.00",
    }
    assert _parts(at) == {
        "Fixed price": "4,000.00",
        "Location basis": "1,000.00",
        "Quantity mismatch": "200.00",
        "Sum = net buyer cost": "5,200.00",
    }
    text = "\n".join(_texts(at))
    assert "Basis = P_L − P_H = **10.00" in text and "does not guarantee savings" in text


def test_hedge_can_raise_cost_and_invalid_inputs_show_nothing(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    at.number_input(key=f"{P}_p_l").set_value(30.0).run(timeout=30)
    at.number_input(key=f"{P}_p_h").set_value(30.0).run(timeout=30)
    assert _flows(at)["Hedge receipt"] == "−800.00"  # 80 × (30 − 40)
    text = "\n".join(_texts(at))
    assert "the hedge **raised** the buyer's cost by 800.00" in text.replace("\\$", "$")
    at.number_input(key=f"{P}_q").set_value(0.0).run(timeout=30)
    assert "financial position without physical consumption" in "\n".join(_texts(at))


def test_pair_import_offers_only_verified_runs_and_edits_drop_the_label(data_dir):
    records = mc.run_lesson_runs(["congested", "breakpoint"], {})
    at = AppTest.from_string(FINANCE)
    at.session_state["model_runs"] = records
    at.run(timeout=30)
    options = at.selectbox(key=f"{P}_imp_run").options
    assert len(options) == 1 and records["congested"].run_id[-8:] in options[0]
    at.radio(key=f"{P}_imp_l").set_value("C")
    at.radio(key=f"{P}_imp_h").set_value("A")
    at.button(key=f"{P}_imp_go").click().run(timeout=30)
    at.run(timeout=30)
    assert at.number_input(key=f"{P}_p_l").value == pytest.approx(40.0)
    assert at.number_input(key=f"{P}_p_h").value == pytest.approx(20.0)
    text = "\n".join(_texts(at))
    assert "P_L: modeled (run" in text and "P_H: modeled (run" in text and "K: synthetic" in text
    assert "not a market hub" in text
    at.number_input(key=f"{P}_p_h").set_value(25.0).run(timeout=30)
    text = "\n".join(_texts(at))
    assert "P_L: modeled (run" in text and "P_H: synthetic" in text


def test_same_bus_import_is_refused(data_dir):
    records = mc.run_lesson_runs(["congested"], {})
    at = AppTest.from_string(FINANCE)
    at.session_state["model_runs"] = records
    at.run(timeout=30)
    at.radio(key=f"{P}_imp_l").set_value("B")
    at.radio(key=f"{P}_imp_h").set_value("B")
    at.button(key=f"{P}_imp_go").click().run(timeout=30)
    assert any("different buses" in e.value for e in at.error)
    assert "P_L: synthetic" in "\n".join(_texts(at))


def _open_lesson():
    at = AppTest.from_string(LEARN)
    at.session_state["lesson_choice"] = "basis-exposure"
    return at.run(timeout=30)


def test_lesson_exercises_record_progress_and_reset_on_change(data_dir):
    at = _open_lesson()
    assert not at.exception
    radios = [r for r in at.radio if r.label == "Your answer"]
    assert len(radios) == 5
    net = next(r for r in radios if "5,200 synthetic $" in r.options)  # defaults: H = 80
    net.set_value("5,200 synthetic $")
    [b for b in at.button if b.label == "Check answer"][radios.index(net)].click()
    at.run(timeout=30)
    assert any("Correct." in s.value for s in at.success)
    record = Progress(data_dir).exercise_record("basis-exposure", "net-cost")
    assert record["first_attempt_correct"] and record["snapshot_id"].startswith("basis-")
    at.number_input(key="learn_basis-exposure_h").set_value(60.0).run(timeout=30)
    assert not any("Correct." in s.value for s in at.success)


def test_rendered_markdown_has_no_unescaped_dollar(data_dir):
    unescaped = re.compile(r"(?<!\\)\$")
    at = AppTest.from_string(FINANCE).run(timeout=30)
    assert [t for t in _texts(at) if unescaped.search(t)] == []
    lesson = _open_lesson()
    lesson.toggle(key="technical_detail").set_value(True).run(timeout=30)
    assert [t for t in _texts(lesson) if unescaped.search(t)] == []
    labels = [n.label for n in at.number_input] + [n.label for n in lesson.number_input]
    assert all(lb.count("$") <= 1 and "\\" not in lb for lb in labels)
