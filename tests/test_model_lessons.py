"""Market-mechanics lessons: bindings, model-backed exercise answers, snapshots, invalidation.

Offline and credential-free. Every network, offer, and result here is SYNTHETIC/modeled.
Answers are computed by the verified services; this file asserts the hand-derived
benchmarks (docs/calculations.md, "DC OPF") against them.
"""

import re

import pytest

from mambo_explorer import model_exercises as mx
from mambo_explorer.exercises import Exercise, Unavailable
from mambo_explorer.lessons import LessonError, load_lessons, parse_lesson
from mambo_explorer.modeling import adapter
from mambo_explorer.modeling import cases as mc
from mambo_explorer.modeling import opf_network as on
from mambo_explorer.modeling.runs import RunStore
from mambo_explorer.progress import UNDERSTANDING, Progress

MODEL_LESSONS = ["pf-vs-dispatch", "location-prices", "unverified-marginal"]


@pytest.fixture(scope="module")
def records():
    return mc.run_lesson_runs(list(mc.LESSON_RUNS), {})


def _ex(name, records) -> Exercise:
    exercise = mx.generate({"exercise_id": name, "generator": name}, records)
    assert isinstance(exercise, Exercise), getattr(exercise, "reason", exercise)
    return exercise


def _answer(exercise: Exercise) -> str:
    return exercise.options[exercise.answer_index]


def _dispatch(record) -> dict:
    return {d["generator"]: d["dispatch_mw"] for d in record.dispatch}


# --- registry and benchmarks --------------------------------------------------------------


def test_every_lesson_run_is_current_and_passes_its_checks(records):
    assert set(records) == set(mc.LESSON_RUNS)
    for key, record in records.items():
        assert mc.is_current(key, records), key
        assert record.package["matches_pin"] and record.scenario_id == on.SCENARIO_ID
    expected = {k: "optimal" for k, s in mc.LESSON_RUNS.items() if s.kind == mc.OPF}
    expected.update(
        {
            "infeasible": "infeasible",
            "pf-no-limit-cheapest": "ok_with_violations",
            "pf-chosen": "ok",
        }
    )
    assert {k: r.status for k, r in records.items()} == expected


def test_congested_benchmark_through_the_verified_services(records):
    """Hand-derived benchmark C: 90/60 MW, 3,600 $/h, prices 20/30/40 $/MWh, AC dual −40."""
    r = records["congested"]
    assert _dispatch(r) == pytest.approx({"G1": 90.0, "G2": 60.0}, abs=1e-6)
    assert r.cost_rate_per_h == pytest.approx(3600.0, abs=1e-6)
    assert r.interval_cost == pytest.approx(3600.0, abs=1e-6) and r.interval_hours == 1.0
    assert r.price_status == "verified"
    prices = {p["bus"]: p["price_per_mwh"] for p in r.prices}
    assert prices == pytest.approx({"A": 20.0, "B": 30.0, "C": 40.0}, abs=1e-6)
    ac = next(b for b in r.branches if b["branch"] == "AC")
    assert ac["binding"] and ac["limit_sensitivity_per_mw"] == pytest.approx(-40.0, abs=1e-6)


def test_lesson_benchmarks_for_the_other_steps(records):
    """Hand derivations: AC = 75 − 0.25·g2 − ... with demand L at C: AC = L/2 − g2/4.

    - uncongested: 150/0, 3,000 $/h, all prices 20; +10 MW at C → 160/0 (G1 serves it)
    - congested +10 MW: AC = 80 − g2/4 ≤ 60 → g2 = 80, g1 = 80, 4,000 $/h (ΔG1 −10, ΔG2 +20)
    - AC rating 70: 70 = 75 − g2/4 → g2 = 20, g1 = 130, 3,200 $/h = 3,600 − 40 × 10
    """
    approx = lambda d: pytest.approx(d, abs=1e-6)  # noqa: E731
    assert _dispatch(records["uncongested"]) == approx({"G1": 150.0, "G2": 0.0})
    assert _dispatch(records["uncongested-plus10"]) == approx({"G1": 160.0, "G2": 0.0})
    assert _dispatch(records["congested-plus10"]) == approx({"G1": 80.0, "G2": 80.0})
    assert records["congested-plus10"].cost_rate_per_h == pytest.approx(4000.0, abs=1e-6)
    assert _dispatch(records["relaxed"]) == approx({"G1": 130.0, "G2": 20.0})
    assert records["relaxed"].cost_rate_per_h == pytest.approx(3200.0, abs=1e-6)


def test_power_flow_at_a_specified_dispatch_reports_but_does_not_enforce(records):
    over = records["pf-no-limit-cheapest"]
    assert over.kind == "pf.dispatch" and over.inputs["g2_mw"] == 0.0  # from the verified run
    flows = {b["branch"]: b["flow_from_to_mw"] for b in over.branches}
    assert flows["AC"] == pytest.approx(75.0, abs=1e-6)  # 150/2: rated 60, reported not limited
    failed = [c["name"] for c in over.checks if not c["passed"]]
    assert failed == ["branch AC within rating"]
    chosen = records["pf-chosen"]
    out = {g["generator"]: g["output_mw"] for g in chosen.generators}
    assert out == pytest.approx({"G1": 60.0, "G2": 90.0}, abs=1e-6)
    assert adapter.linear_cost_rate(mc.run_inputs("pf-chosen"), out) == pytest.approx(3900.0)


def test_power_flow_at_dispatch_rejects_invalid_g2_and_records_no_outputs():
    for bad in (-1.0, 301.0, float("nan"), True, "10"):
        record = adapter.run_dispatch_power_flow(mc.run_inputs("congested"), bad)
        assert record.status == "failed" and record.branches == [] and record.generators == []


def test_breakpoint_duals_lie_between_the_one_sided_rates():
    """Lesson 7 says the withheld dual is a legitimate number between the one-sided rates in
    these cases. Check it for both breakpoint cases, straight from the package."""
    from mambo_power.opf import solve_dc_opf

    for key in ("breakpoint", "ac-at-limit"):
        inputs = mc.run_inputs(key)
        result = solve_dc_opf(on.build_network(inputs))
        sens = {
            s["bus"]: s
            for s in adapter.price_sensitivities(inputs, result.objective_cost, solve_dc_opf)
        }
        for bus in result.buses:
            s = sens[bus.id]
            low, high = sorted((s["up_per_mwh"], s["down_per_mwh"]))
            assert low - 1e-6 <= bus.lmp <= high + 1e-6, (key, bus.id)


# --- lesson schema and bindings -----------------------------------------------------------


def test_model_lessons_bind_registered_runs_and_generators():
    lessons = {le.id: le for le in load_lessons()}
    for lesson_id in MODEL_LESSONS:
        meta = lessons[lesson_id].meta
        assert meta["model_bindings"] and meta["model_panels"]
        assert set(meta["model_bindings"]) <= set(mc.LESSON_RUNS)
        assert meta["dataset_bindings"] == [] and meta["sources"] == []
        for ex in meta["exercises"]:
            assert ex["kind"] == "model" and ex["generator"] in mx.GENERATORS
            assert set(mx.REQUIRES[ex["generator"]]) <= set(meta["model_bindings"])
        assert any("not yet reviewed by a person" in x.lower() for x in meta["limitations"])
    for lesson_id in ("power-vs-energy", "reading-demand"):
        assert lessons[lesson_id].meta["model_bindings"] == []
    used = {ex["generator"] for lid in MODEL_LESSONS for ex in lessons[lid].meta["exercises"]}
    assert used == set(mx.GENERATORS)


SAMPLE = """---
lesson_id: sample
title: Sample
order: 9
sequence_stage: fundamentals
prerequisites: []
objectives: [Learn a thing]
content_version: 1.0.0
effective_date: null
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources: []
dataset_bindings: []
calculation_ids: [dc_opf]
data_panels: []
model_bindings: [congested]
model_panels: [location_prices]
exercises:
  - exercise_id: e1
    kind: model
    generator: binding_constraint
    calculation_id: dc_opf
glossary_terms: [MW]
limitations: [Synthetic]
implementation_status: implemented
---

## Beginner

Text.

## Technical detail

More text.
"""


def test_valid_model_lesson_sample_parses():
    assert parse_lesson(SAMPLE).meta["model_bindings"] == ["congested"]


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("model_bindings: [congested]", "model_bindings: [made-up]", "model_bindings must"),
        ("model_panels: [location_prices]", "model_panels: [chart]", "unknown model_panels"),
        ("generator: binding_constraint", "generator: relaxation_cost", "model runs not bound"),
        ("generator: binding_constraint", "generator: demand_max", "unknown generator"),
        ("calculation_ids: [dc_opf]", "calculation_ids: [power_energy]", "not declared"),
        (
            "model_bindings: [congested]\nmodel_panels: [location_prices]",
            "model_bindings: []\nmodel_panels: [location_prices]",
            "model panels need",
        ),
        (
            "model_bindings: [congested]",
            "model_bindings: [congested, pf-no-limit-cheapest]",
            "needs its source run",
        ),
    ],
)
def test_invalid_model_bindings_are_rejected(old, new, message):
    assert old in SAMPLE
    with pytest.raises(LessonError, match=message):
        parse_lesson(SAMPLE.replace(old, new))


def test_model_lesson_text_does_not_hardcode_results():
    """Answers come from runs. The benchmark numbers must not appear in lesson prose."""
    lessons = {le.id: le for le in load_lessons()}
    for lesson_id in MODEL_LESSONS:
        lesson = lessons[lesson_id]
        text = lesson.beginner + lesson.technical
        assert not re.search(r"\b(3,?600|3,?900|3,?200|90 MW|60 MW|75 MW|40 \$)", text), lesson_id
        assert not re.search(r"\b(20|30|40) ?/ ?(30|40)\b", text), lesson_id


def test_model_lesson_wording_is_precise():
    lessons = {le.id: le for le in load_lessons()}
    text = {k: (lessons[k].beginner + lessons[k].technical) for k in MODEL_LESSONS}
    flat = {k: " ".join(v.split()) for k, v in text.items()}
    assert "not the model any real system operator runs" in flat["pf-vs-dispatch"]
    assert "Feasible does not mean cheapest" in flat["pf-vs-dispatch"]
    assert "a unique two-sided marginal price was not verified" in flat["unverified-marginal"]
    assert "concerns only the tested perturbations" in flat["unverified-marginal"]
    assert "not because it is meaningless" in flat["unverified-marginal"]
    assert "does not establish uniqueness" in flat["unverified-marginal"]
    assert "no loss component" in flat["location-prices"]
    for k in MODEL_LESSONS:
        assert "meaningless" not in flat[k].replace("not because it is meaningless", "")


# --- model-backed exercises ---------------------------------------------------------------


def test_every_exercise_is_available_with_answers_from_runs(records):
    for name in mx.GENERATORS:
        exercise = _ex(name, records)
        assert exercise.synthetic and exercise.snapshot_id.startswith("model-")
        assert len(set(exercise.options)) == len(exercise.options) == 4, name
        refs = tuple(records[k].run_id for k in mx.REQUIRES[name])
        assert exercise.result_refs == refs
        # Options are rendered as Markdown radio labels: never a pair of "$" (LaTeX).
        assert all(o.count("$") <= 1 and "\\" not in o for o in exercise.options), name


def test_benchmark_backed_answers(records):
    assert "Line AC would carry 75 MW, above its 60 MW rating" in _answer(
        _ex("pf_reports_violation", records)
    )
    assert "costs 300 synthetic $/h more" in _answer(_ex("feasible_not_cheapest", records))
    assert _answer(_ex("binding_constraint", records)) == "Line AC (A → C), at its 60 MW rating"
    assert _answer(_ex("next_increment", records)) == "G1 +10 MW and G2 0 MW"
    sens = _answer(_ex("positive_sensitivity", records))
    assert "adds about 40 synthetic $" in sens and "G1 by −1 MW and G2 by +2 MW" in sens
    assert (
        _answer(_ex("relaxation_cost", records)) == "It falls by 400 synthetic $/h (−40 × 10 MW)."
    )


def test_cost_rate_interval_cost_price_and_sensitivity_are_distinct(records):
    exercise = _ex("cost_units", records)
    assert _answer(exercise) == "3,600 synthetic $"
    assert set(exercise.options) == {
        "3,600 synthetic $",
        "3,600 synthetic $/h",
        "40 synthetic $/MWh",
        "−40 synthetic $/h per MW of rating",
    }
    assert "only because the interval is one hour" in exercise.explanation


def test_withheld_price_explanations(records):
    reason = _ex("withheld_reason", records)
    assert _answer(reason) == (
        "Over +0.1 MW the cost rate rises at an average of 30 per MWh; over −0.1 MW it falls "
        "at an average of 20 per MWh. They differ, so a unique two-sided marginal price was "
        "not verified for this run."
    )
    assert "not meaningless" in reason.explanation
    assert "averages over 0.1 MW, not local derivatives" in reason.explanation
    edge = _answer(_ex("infeasible_direction", records))
    assert edge == (
        "The +0.1 MW change is infeasible; the −0.1 MW change is feasible, with an average "
        "decremental rate of 30 per MWh."
    )


def test_nonunique_dispatch_wording(records):
    assert _answer(_ex("nonunique_vs_infeasible", records)) == (
        "Equal offers: optimal, but more than one dispatch is equally cheap. Not enough "
        "capacity: infeasible (no dispatch meets demand within the limits)."
    )
    exercise = _ex("uniqueness_vs_price", records)
    assert _answer(exercise) == (
        "The dispatch is not unique, and the tested two-sided price check passed."
    )
    assert "does not prove that the dispatch or the dual is unique" in exercise.explanation


def test_exercises_are_deterministic_for_the_same_results(records):
    a, b = _ex("binding_constraint", records), _ex("binding_constraint", records)
    assert (a.snapshot_id, a.options, a.answer_index) == (b.snapshot_id, b.options, b.answer_index)


# --- invalidation and failure -------------------------------------------------------------


def test_changing_a_case_invalidates_its_results_and_exercises(records, monkeypatch):
    monkeypatch.setitem(mc.LAB_CASES, "congested", ("Changed", {"rating_ac": 70.0}))
    assert not mc.is_current("congested", records)
    # The PF run that starts from the congested case is stale too.
    assert not mc.is_current("pf-chosen", records)
    current = {k: r for k, r in records.items() if mc.is_current(k, records)}
    result = mx.generate({"exercise_id": "x", "generator": "binding_constraint"}, current)
    assert isinstance(result, Unavailable) and "not current" in result.reason


def test_scenario_version_or_pin_change_invalidates(records, monkeypatch):
    original = on.SCENARIO_VERSION
    monkeypatch.setattr(on, "SCENARIO_VERSION", "9.9.9")
    assert not any(mc.is_current(k, records) for k in records)
    monkeypatch.setattr(on, "SCENARIO_VERSION", original)
    record = records["congested"]
    record_package = dict(record.package)
    try:
        record.package["matches_pin"] = False
        assert not mc.is_current("congested", records)
    finally:
        record.package.clear()
        record.package.update(record_package)
    assert mc.is_current("congested", records)


def test_a_source_change_invalidates_a_dependent_power_flow(records):
    changed = dict(records)
    changed["uncongested"] = records["congested"]  # a different verified dispatch
    assert not mc.is_current("pf-no-limit-cheapest", changed)


def test_snapshot_changes_with_inputs_status_or_versions(records, monkeypatch):
    keys = ("congested",)
    base, _ = mx.snapshot(keys, records)
    import copy

    other = copy.deepcopy(records["congested"])
    other.input_fingerprint = "0" * 16
    assert mx.snapshot(keys, {"congested": other})[0] != base
    other = copy.deepcopy(records["congested"])
    other.price_status = "withheld"
    assert mx.snapshot(keys, {"congested": other})[0] != base
    monkeypatch.setattr(adapter, "CHECKS_VERSION", "9.0.0")
    assert mx.snapshot(keys, records)[0] != base


def _failing(_net):
    raise RuntimeError("synthetic solver failure (test)")


def test_failed_runs_give_no_answers():
    failed = mc.run_lesson_runs(list(mc.LESSON_RUNS), {}, solvers={"opf": _failing})
    assert all(failed[k].status == "failed" for k, s in mc.LESSON_RUNS.items() if s.kind == mc.OPF)
    # A PF run whose verified source failed is not run at all.
    assert "pf-no-limit-cheapest" not in failed
    for name in mx.GENERATORS:
        result = mx.generate({"exercise_id": name, "generator": name}, failed)
        assert isinstance(result, Unavailable), name
        assert all(r.dispatch == [] and r.prices == [] for r in failed.values() if r.kind == mc.OPF)


def test_rerunning_skips_current_results(records):
    again = mc.run_lesson_runs(list(mc.LESSON_RUNS), records)
    assert all(again[k] is records[k] for k in records)


# --- progress -----------------------------------------------------------------------------


def test_progress_records_result_refs_and_stays_isolated(tmp_path, records):
    progress = Progress(tmp_path)
    for k in mx.REQUIRES["binding_constraint"]:
        RunStore(tmp_path).save(records[k])
    exercise = _ex("binding_constraint", records)
    progress.mark_viewed("location-prices")
    progress.record_answer(
        "location-prices", "binding-constraint", exercise.snapshot_id, True, exercise.result_refs
    )
    reloaded = Progress(tmp_path)  # persisted on disk
    rec = reloaded.exercise_record("location-prices", "binding-constraint")
    assert rec["first_attempt_correct"] and rec["result_refs"] == list(exercise.result_refs)
    assert RunStore(tmp_path).load(rec["result_refs"][0]).run_id == exercise.result_refs[0]
    assert reloaded.lesson_state("location-prices", ["binding-constraint"]) == UNDERSTANDING
    assert reloaded.lesson_state("unverified-marginal", ["withheld-reason"]) == "not started"
    assert set(reloaded.load()["lessons"]) == {"location-prices"}
    # A new snapshot (changed results) is a new question instance, with fresh attempts.
    rec2 = reloaded.record_answer("location-prices", "binding-constraint", "model-other", False)
    assert rec2["attempts"] == 1 and rec2["first_attempt_correct"] is False
    assert "result_refs" not in rec2
