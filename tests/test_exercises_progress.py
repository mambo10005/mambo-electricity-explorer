import json
import subprocess
from pathlib import Path

import pytest

from mambo_explorer import calculations as calc
from mambo_explorer import exercises as ex
from mambo_explorer.calculations import Observation, Selection
from mambo_explorer.progress import (
    EXERCISE_COMPLETED,
    NOT_STARTED,
    UNDERSTANDING,
    VIEWED,
    Progress,
)

REPO = Path(__file__).resolve().parents[1]
SEL = Selection("ERCO", "2026-10-01T00", "2026-10-01T05")


def _obs(d_values, df_values):
    """SYNTHETIC observations for exercise tests."""
    rows = []
    for metric, values in (("D", d_values), ("DF", df_values)):
        for h, v in enumerate(values):
            if v is not None:
                rows.append(
                    Observation(
                        "ERCO",
                        metric,
                        f"2026-10-01T{h:02d}",
                        float(v),
                        str(v),
                        "megawatthours",
                        "",
                        1,
                        "r1",
                    )
                )
    return rows


OBS = _obs([100, 200, 300, 250, 150, 120], [110, 190, None, 240, 170, None])


@pytest.mark.parametrize("name", ["demand_max", "error_sign", "mae_value", "forecast_absent_count"])
def test_data_exercises_are_deterministic_and_answer_from_calculations(name):
    first = ex.GENERATORS[name]("x", OBS, SEL)
    again = ex.GENERATORS[name]("x", list(reversed(OBS)), SEL)
    assert first == again
    assert first.snapshot_id == calc.snapshot_id(OBS, SEL)
    assert len(set(first.options)) == len(first.options) >= 3
    answer = first.options[first.answer_index]
    if name == "demand_max":
        assert answer.startswith("300 MWh at 2026-10-01T02")
    elif name == "mae_value":
        assert answer == f"{ex._fmt(calc.forecast_error(OBS, SEL).values['mae'])} MWh"
    elif name == "forecast_absent_count":
        assert answer == "2 of 6 hourly labels"
    else:
        assert ("ABOVE" in answer) == (answer.startswith("+"))


def test_error_sign_answer_matches_actual_minus_forecast():
    e = ex.error_sign("x", OBS, SEL)
    period = e.question.split("At label ")[1].split(",")[0]
    pair = next(
        p for p in calc.forecast_error(OBS, SEL).values["pair_errors"] if p["period"] == period
    )
    answer = e.options[e.answer_index]
    assert answer.startswith("+" if pair["error"] > 0 else "−")


def test_new_snapshot_regenerates_exercise():
    revised = [
        o
        if o.period != "2026-10-01T02" or o.metric != "D"
        else Observation("ERCO", "D", o.period, 999.0, "999", o.unit, "", 2, "r2")
        for o in OBS
    ]
    before = ex.demand_max("x", OBS, SEL)
    after = ex.demand_max("x", revised, SEL)
    assert before.snapshot_id != after.snapshot_id
    assert "999" in after.options[after.answer_index]
    narrower = ex.demand_max("x", OBS, Selection("ERCO", "2026-10-01T00", "2026-10-01T01"))
    assert "200 MWh" in narrower.options[narrower.answer_index]


def test_data_exercises_are_unavailable_without_data():
    spec = {"exercise_id": "x", "kind": "data", "generator": "demand_max"}
    assert isinstance(ex.generate(spec, None, None), ex.Unavailable)
    assert isinstance(ex.demand_max("x", [], SEL), ex.Unavailable)
    assert isinstance(ex.error_sign("x", _obs([1, 2], []), SEL), ex.Unavailable)


def test_concept_exercises_are_labeled_synthetic_when_numeric():
    for name in ("power_energy_synthetic", "one_hour_equivalence"):
        e = ex.GENERATORS[name]("x")
        assert e.synthetic and e.question.startswith("SYNTHETIC EXAMPLE")
    assert (
        "1,000 MWh"
        == ex.power_energy_synthetic("x").options[ex.power_energy_synthetic("x").answer_index]
    )


# --- progress -----------------------------------------------------------------------------


def test_progress_states_are_distinct_and_not_granted_by_viewing(tmp_path):
    p = Progress(tmp_path / "data")
    ids = ["a", "b"]
    assert p.lesson_state("L", ids) == NOT_STARTED
    p.mark_viewed("L")
    assert p.lesson_state("L", ids) == VIEWED
    p.record_answer("L", "a", "s1", correct=True)
    assert p.lesson_state("L", ids) == EXERCISE_COMPLETED
    p.record_answer("L", "b", "s1", correct=True)
    assert p.lesson_state("L", ids) == UNDERSTANDING


def test_wrong_first_attempt_does_not_demonstrate_understanding(tmp_path):
    p = Progress(tmp_path / "data")
    p.mark_viewed("L")
    p.record_answer("L", "a", "s1", correct=False)
    record = p.record_answer("L", "a", "s1", correct=True)
    assert record["attempts"] == 2 and record["first_attempt_correct"] is False
    assert p.lesson_state("L", ["a"]) == EXERCISE_COMPLETED
    # A new data snapshot is a new question instance with a fresh first attempt.
    fresh = p.record_answer("L", "a", "s2", correct=True)
    assert fresh["attempts"] == 1 and p.lesson_state("L", ["a"]) == UNDERSTANDING


def test_bookmarks_and_local_storage_location(tmp_path):
    p = Progress(tmp_path / "data")
    p.set_bookmark("L", True)
    assert p.bookmarked("L") and not p.bookmarked("other")
    assert p.path == tmp_path / "data" / "learn" / "progress.json"
    assert json.loads(p.path.read_text("utf-8"))["version"] == 1


def test_default_progress_path_is_gitignored():
    assert (
        subprocess.run(
            ["git", "check-ignore", "-q", "data/learn/progress.json"], cwd=REPO
        ).returncode
        == 0
    )


def test_unknown_progress_version_is_rejected(tmp_path):
    p = Progress(tmp_path)
    p.path.parent.mkdir(parents=True)
    p.path.write_text('{"version": 99, "lessons": {}}', "utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        p.load()
