"""Market-mechanics lessons and Learn <-> Model Labs links via AppTest (headless, offline).

The network, offers, and every result are SYNTHETIC/modeled.
"""

import functools
import re

import pytest
from streamlit.testing.v1 import AppTest

from mambo_explorer import routes
from mambo_explorer.lessons import load_lessons
from mambo_explorer.modeling import cases as mc
from mambo_explorer.modeling.runs import RunStore
from mambo_explorer.progress import Progress

LEARN = "from mambo_explorer.pages import render_page\nrender_page('learn')\n"
LAB = "from mambo_explorer.pages import render_page\nrender_page('model-labs')\n"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    # app.py registers its pages in a module-level dict; a test that ran the full app must
    # not leak them into these single-page tests.
    monkeypatch.setattr(routes, "PAGES", {})
    return path


def _open(lesson_id: str) -> AppTest:
    at = AppTest.from_string(LEARN)
    at.session_state["lesson_choice"] = lesson_id
    at.run(timeout=30)
    assert not at.exception
    return at


def _run_models(at: AppTest, lesson_id: str) -> AppTest:
    at.button(key=f"lesson_run::{lesson_id}").click()
    at.run(timeout=120)
    assert not at.exception
    return at


def _table(at: AppTest, column: str):
    return next((tb.value for tb in at.table if column in tb.value.columns), None)


def _texts(at: AppTest) -> list[str]:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return parts


def _text(at: AppTest) -> str:
    return "\n".join(_texts(at))


def _answer(at: AppTest, exercise_index: int, option: str) -> AppTest:
    radios = [r for r in at.radio if r.label == "Your answer"]
    radios[exercise_index].set_value(option)
    [b for b in at.button if b.label == "Check answer"][exercise_index].click()
    return at.run(timeout=60)


def _correct_option(at: AppTest, exercise_index: int, generator: str) -> str:
    from mambo_explorer import model_exercises as mx

    records = at.session_state["model_runs"]
    exercise = mx.generate({"exercise_id": "x", "generator": generator}, records)
    return exercise.options[exercise.answer_index]


def test_model_lesson_runs_nothing_until_asked(data_dir):
    at = _open("location-prices")
    text = _text(at)
    assert "Press **Run this lesson's model cases**" in text
    assert "Models run only when you press the button" in text
    assert _table(at, "Cost rate ($/h)") is None
    assert all("Exercise unavailable" in i.value for i in at.info if "Exercise" in i.value)
    assert not (data_dir / "model-runs").exists()
    # Inputs and topology are shown before any run.
    assert _table(at, "Offers G1 / G2 ($/MWh)") is not None
    assert _table(at, "Reactance (pu, 100 MVA base)") is not None
    assert "not yet been reviewed by a person" in text or "Not yet reviewed by a person" in text


def test_location_prices_lesson_shows_verified_results_units_and_provenance(data_dir):
    at = _run_models(_open("location-prices"), "location-prices")
    steps = _table(at, "Cost rate ($/h)")
    row = steps[steps["Step"] == "Congested"].iloc[0]
    assert (row["G1 / G2 (MW)"], row["Cost rate ($/h)"], row["Cost, 1 h ($)"]) == (
        "90 / 60",
        "3,600",
        "3,600",
    )
    assert row["Binding line"] == "AC (−40 $/h per MW)"
    prices = _table(at, "A")
    congested = prices[prices["Step"] == "Congested"].iloc[0]
    assert (congested["A"], congested["B"], congested["C"]) == ("20", "30", "40")
    units = _table(at, "Used for")
    assert list(units["Unit"]) == [
        "MW",
        "MWh",
        "synthetic $/MWh",
        "synthetic $/h",
        "synthetic $",
        "synthetic $/h per MW",
    ]
    extra = _table(at, "G2 change (MW)")
    assert list(extra["G2 change (MW)"]) == ["0", "20"]
    text = _text(at)
    assert "commit `26be8c18b7ef`" in text and "Adapter checks v" in text
    assert "not** ISO prices" in text and "not the model any real system operator runs" in text
    # Saved to the local model-run store only, never to observation storage.
    lesson = next(le for le in load_lessons() if le.id == "location-prices")
    assert len(RunStore(data_dir).recent(50)) == len(lesson.meta["model_bindings"])
    assert {p.name for p in data_dir.iterdir()} <= {"learn", "model-runs"}
    assert all("Exercise unavailable" not in i.value for i in at.info)


def test_pf_vs_dispatch_lesson_contrasts_reported_and_enforced_limits(data_dir):
    at = _run_models(_open("pf-vs-dispatch"), "pf-vs-dispatch")
    flows = _table(at, "AC")
    by_run = {r["Run"]: r for r in flows.to_dict("records")}
    assert by_run["Rating (MW)"]["AC"] == "60"
    assert by_run["Power flow: cheapest if lines had no limits"]["AC"] == "75"
    assert by_run["Power flow: cheapest if lines had no limits"]["Status"] == (
        "solved, limits exceeded"
    )
    assert by_run["Congested"]["AC"] == "60" and by_run["Congested"]["Status"] == "optimal"
    costs = _table(at, "Dispatch set by")
    assert dict(zip(costs["Run"], costs["Cost rate ($/h)"], strict=True)) == {
        "Power flow: cheapest if lines had no limits": "3,000",
        "Power flow: a dispatch chosen by hand": "3,900",
        "Congested": "3,600",
    }
    checks = _table(at, "Limits exceeded")
    assert list(checks["Limits exceeded"]) == ["branch AC", "none", "enforced by the optimizer"]


def test_unverified_lesson_shows_withheld_states_with_precise_wording(data_dir):
    at = _run_models(_open("unverified-marginal"), "unverified-marginal")
    status = _table(at, "Prices")
    by_case = {r["Case"]: r for r in status.to_dict("records")}
    assert by_case["Breakpoint"]["Prices"] == "withheld"
    assert by_case["Equal offers"]["Dispatch"] == "not unique"
    assert by_case["Equal offers"]["Prices"] == "verified"
    assert by_case["Not enough capacity"]["Run"] == "infeasible"
    assert by_case["Not enough capacity"]["Dispatch"] == "—"
    tables = [t.value for t in at.table if "Average rate ($/MWh)" in t.value.columns]
    # One finite-change table per withheld run, in panel order.
    assert len(tables) == 5
    edge = tables[3][tables[3]["Bus"] == "C"].set_index("Change (MW)")
    assert edge.loc["+0.1", "Cost-rate change ($/h)"] == "infeasible"
    assert (
        edge.loc["−0.1", "Cost-rate change ($/h)"],
        edge.loc["−0.1", "Average rate ($/MWh)"],
    ) == (
        "−3",
        "30",
    )
    near = tables[1][tables[1]["Bus"] == "C"].set_index("Change (MW)")
    assert near.loc["+0.1", "Average rate ($/MWh)"] == "25"  # blend: (0.05·20 + 0.05·30)/0.1
    zero = tables[4][tables[4]["Bus"] == "C"].set_index("Change (MW)")
    assert zero.loc["−0.1", "Cost-rate change ($/h)"] == "infeasible"
    assert zero.loc["+0.1", "Average rate ($/MWh)"] == "20"
    text = _text(at)
    assert "A unique two-sided marginal price was not verified for this run." in text
    assert "not local derivatives" in text
    assert "one-sided rates" not in text.lower()


def test_answering_records_progress_with_result_refs(data_dir):
    at = _run_models(_open("location-prices"), "location-prices")
    option = _correct_option(at, 0, "binding_constraint")
    at = _answer(at, 0, option)
    assert any("Correct." in s.value for s in at.success)
    assert any("Computed from model run(s)" in c.value for c in at.caption)
    record = Progress(data_dir).exercise_record("location-prices", "binding-constraint")
    assert record["first_attempt_correct"] is True and len(record["result_refs"]) == 1
    assert RunStore(data_dir).load(record["result_refs"][0]).kind == "opf.dc"
    assert set(Progress(data_dir).load()["lessons"]) == {"location-prices"}


def test_stale_results_are_hidden_and_never_marked(data_dir, monkeypatch):
    at = _run_models(_open("location-prices"), "location-prices")
    at = _answer(at, 0, _correct_option(at, 0, "binding_constraint"))
    assert any("Correct." in s.value for s in at.success)
    # The scenario changes (as after an update) while the old results sit in the session.
    original = mc.LAB_CASES["congested"]
    monkeypatch.setitem(mc.LAB_CASES, "congested", ("Changed", {"rating_ac": 70.0}))
    at.run(timeout=60)
    assert any("no longer match" in w.value for w in at.warning)
    assert not any("Correct." in s.value for s in at.success)
    assert any("Exercise unavailable" in i.value for i in at.info)
    assert _table(at, "Cost rate ($/h)") is not None  # other steps are still current
    steps = _table(at, "Cost rate ($/h)")
    assert "Congested" not in list(steps["Step"])
    # Back to the original scenario: the old verdict does not come back by itself. The
    # learner answers again against the current results. (Restore only this entry:
    # monkeypatch.undo() would also drop MAMBO_DATA_DIR and write to the real data dir.)
    monkeypatch.setitem(mc.LAB_CASES, "congested", original)
    at.run(timeout=60)
    assert not any("no longer match" in w.value for w in at.warning)
    assert not any("Correct." in s.value for s in at.success)


def test_failed_runs_show_no_results_or_answers(data_dir, monkeypatch):
    def failing(_net):
        raise RuntimeError("synthetic solver failure (test)")

    original = mc.run_lesson_runs
    monkeypatch.setattr(
        mc, "run_lesson_runs", functools.partial(original, solvers={"opf": failing})
    )
    at = _run_models(_open("location-prices"), "location-prices")
    steps = _table(at, "Cost rate ($/h)")
    assert set(steps["G1 / G2 (MW)"]) == {"FAILED (no results)"}
    assert set(steps["Cost rate ($/h)"]) == {"—"}
    assert not [r for r in at.radio if r.label == "Your answer"]
    assert sum("Exercise unavailable" in i.value for i in at.info) == 5


def test_rendered_markdown_never_holds_an_unescaped_dollar(data_dir):
    unescaped = re.compile(r"(?<!\\)\$")
    for lesson_id in ("pf-vs-dispatch", "location-prices", "unverified-marginal"):
        at = _run_models(_open(lesson_id), lesson_id)
        at.toggle(key="technical_detail").set_value(True).run(timeout=60)
        assert [t for t in _texts(at) if unescaped.search(t)] == [], lesson_id
        for radio in (r for r in at.radio if r.label == "Your answer"):
            assert all(str(o).count("$") <= 1 for o in radio.options), lesson_id


def test_lesson_links_to_the_lab_case_and_the_lab_opens_it(data_dir):
    at = _open("location-prices")
    at.button(key="lablink::location-prices::relaxed").click().run(timeout=30)
    assert at.session_state[routes.HANDOFF_LAB_CASE] == "relaxed"
    # A single-page test has no registered page, so the lesson says where to go.
    assert any("Open **Model Labs**" in i.value for i in at.info)
    lab = AppTest.from_string(LAB)
    lab.session_state[routes.HANDOFF_LAB_CASE] = "relaxed"
    lab.run(timeout=30)
    assert lab.radio(key="lab_choice").value == "opf"
    assert lab.selectbox(key="opf_case").value == "relaxed"
    assert lab.slider(key="opf_rating_ac").value == 70.0
    assert routes.HANDOFF_LAB_CASE not in lab.session_state


def test_lab_ignores_an_unknown_handoff_case(data_dir):
    lab = AppTest.from_string(LAB)
    lab.session_state[routes.HANDOFF_LAB_CASE] = "../../etc"
    lab.run(timeout=30)
    assert not lab.exception and lab.radio(key="lab_choice").value == "pf"


def test_lab_links_back_to_lessons(data_dir):
    lab = AppTest.from_string(LAB).run(timeout=30)
    labels = [b.label for b in lab.button]
    assert "Open lesson: Power flow versus economic dispatch" in labels
    lab.session_state["lab_choice"] = "opf"
    lab.run(timeout=30)
    lab.button(key="lessonlink::opf::unverified-marginal").click().run(timeout=30)
    assert lab.session_state[routes.HANDOFF_LESSON] == "unverified-marginal"
    learn = AppTest.from_string(LEARN)
    learn.session_state[routes.HANDOFF_LESSON] = "unverified-marginal"
    learn.run(timeout=30)
    assert learn.session_state["lesson_choice"] == "unverified-marginal"
    bad = AppTest.from_string(LEARN)
    bad.session_state[routes.HANDOFF_LESSON] = "not-a-lesson"
    bad.run(timeout=30)
    assert not bad.exception and bad.session_state["lesson_choice"] == "power-vs-energy"


def test_full_app_registers_pages_for_cross_links(data_dir):
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "src/mambo_explorer/app.py"
    at = AppTest.from_file(str(app)).run(timeout=30)
    assert not at.exception
    assert {"learn", "model-labs"} <= set(routes.PAGES)
