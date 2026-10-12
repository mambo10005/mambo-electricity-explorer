"""Time-shape calculator on the Finance page and lesson 10 via AppTest (offline, SYNTHETIC)."""

import re

import pytest
from streamlit.testing.v1 import AppTest

from mambo_explorer import routes
from mambo_explorer.progress import Progress

FINANCE = "from mambo_explorer.pages import render_page\nrender_page('finance')\n"
LEARN = "from mambo_explorer.pages import render_page\nrender_page('learn')\n"
P = "finance_shape"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    return path


def _table(at, *cols):
    return next((t.value for t in at.table if all(c in t.value.columns for c in cols)), None)


def _decomp2(at):
    for t in at.table:
        v = t.value
        if "Component" in v.columns and "Time-shape component" in list(v["Component"]):
            return dict(zip(v["Component"], v["Amount ($)"], strict=True))
    return None


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return parts


def _iv_input(at, field, idx=0):
    return next(n for n in at.number_input if n.key.startswith(f"{P}_iv_{field}_{idx}_"))


def test_default_scenario_shows_interval_flows_and_both_decompositions(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    assert not at.exception
    flows = _table(at, "q (MWh)", "Net ($)")
    assert list(flows["Interval"]) == ["t1", "t2"]
    assert list(flows["Net ($)"]) == ["3,000.00", "8,000.00"]  # 1,000+2,000; 12,000−4,000
    assert _decomp2(at) == {
        "Fixed hedge component": "8,000.00",
        "Aggregate energy mismatch": "0.00",
        "Time-shape component": "3,000.00",
        "Sum = net cost": "11,000.00",
    }
    compare = _table(at, "Profile", "Time-shape ($)")
    assert list(compare["Net ($)"]) == ["11,000.00", "5,000.00"]
    text = "\n".join(_texts(at))
    assert "not a universal industry risk metric" in text and "does not guarantee savings" in text
    assert "synthetic scenario `peaky` v1.0.0" in text


def test_switching_scenarios_and_editing_an_interval(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    at.selectbox(key=f"{P}_scenario").set_value("unequal-durations").run(timeout=30)
    assert _decomp2(at)["Time-shape component"] == "1,500.00"
    _iv_input(at, "q", 0).set_value(100.0).run(timeout=30)  # t1: 50 → 100 MWh
    # t1 is now matched (100 = 100·1): r = (0, 0); shape 0; net = 100·20 + 300·60 − 4,000
    assert _decomp2(at)["Time-shape component"] == "0.00"
    assert _decomp2(at)["Sum = net cost"] == "16,000.00"
    assert "edited from synthetic scenario `unequal-durations` v1.0.0" in "\n".join(_texts(at))


def test_invalid_duration_shows_an_error_and_no_numbers(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    _iv_input(at, "d", 0).set_value(0.0).run(timeout=30)
    assert any("greater than 0 hours" in e.value for e in at.error)
    assert _decomp2(at) is None and _table(at, "q (MWh)", "Net ($)") is None


def test_power_entry_uses_the_explicit_duration(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    at.selectbox(key=f"{P}_scenario").set_value("unequal-durations").run(timeout=30)
    at.radio(key=f"{P}_mode").set_value("average power (MW) × the interval's duration").run(
        timeout=30
    )
    at.selectbox(key=f"{P}_edit").set_value(1).run(timeout=30)  # t2 lasts 3 h
    _iv_input(at, "mw", 1).set_value(50.0).run(timeout=30)  # 50 MW × 3 h = 150 MWh
    flows = _table(at, "q (MWh)", "Net ($)")
    assert list(flows["q (MWh)"]) == ["50.00", "150.00"]


def test_add_remove_and_narrow_viewer(data_dir):
    at = AppTest.from_string(FINANCE).run(timeout=30)
    at.button(key=f"{P}_add").click().run(timeout=30)
    flows = _table(at, "q (MWh)", "Net ($)")
    assert list(flows["Interval"]) == ["t1", "t2", "t3"]
    at.selectbox(key=f"{P}_view").set_value(2).run(timeout=30)
    detail = _table(at, "Quantity", "Value")
    assert "Hedge energy h = B × d" in list(detail["Quantity"])
    at.button(key=f"{P}_remove").click().run(timeout=30)  # removes the selected (t3)
    assert list(_table(at, "q (MWh)", "Net ($)")["Interval"]) == ["t1", "t2"]
    assert not at.exception


def _open_lesson():
    at = AppTest.from_string(LEARN)
    at.session_state["lesson_choice"] = "shape-exposure"
    return at.run(timeout=30)


def test_lesson_exercises_record_progress_and_reset_on_change(data_dir):
    at = _open_lesson()
    assert not at.exception
    radios = [r for r in at.radio if r.label == "Your answer"]
    assert len(radios) == 5
    mw = next(r for r in radios if "100 MWh (power × duration)" in r.options)
    mw.set_value("100 MWh (power × duration)")
    [b for b in at.button if b.label == "Check answer"][radios.index(mw)].click()
    at.run(timeout=30)
    assert any("Correct." in s.value for s in at.success)
    record = Progress(data_dir).exercise_record("shape-exposure", "mw-vs-mwh")
    assert record["first_attempt_correct"] and record["snapshot_id"].startswith("shape-")
    at.number_input(key="learn_shape-exposure_b").set_value(50.0).run(timeout=30)
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
