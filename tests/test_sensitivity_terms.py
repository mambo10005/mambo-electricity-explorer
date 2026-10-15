"""BL-5 regressions: finite-change terminology, direction-specific feasibility, staleness.

Offline; SYNTHETIC network and offers. Expected values are derived by hand here, never
copied from the app's output:

Network: G1 at A (offer 20), G2 at B (offer 30), demand D at C, h = 0.1 MW.
- near breakpoint: cap G1 = 150, D = 149.95, ratings 300. G1 has 0.05 MW of headroom.
    increase: first 0.05 MW at 20, next 0.05 MW at 30 → ΔC = 1 + 1.5 = +2.5 $/h,
              average = 2.5 / 0.1 = 25 $/MWh (a blend; the local slope is still 20)
    decrease: 0.1 MW less from G1 → ΔC = −2 $/h, average = 20 $/MWh
- capacity edge: caps 100 + 50 = D = 150. increase infeasible; decrease saves G2 (dearest
    running unit) → ΔC = −3 $/h, average 30.
- zero demand: D = 0, both units at 0 MW. decrease would need negative output → infeasible;
    increase from G1 → ΔC = +2 $/h, average 20.
- congested (AC 60): both directions feasible; averages equal the prices 20 / 30 / 40.
"""

import copy

import pytest
from mambo_power.opf import solve_dc_opf

from mambo_explorer import model_exercises as mx
from mambo_explorer.modeling import adapter, sensitivity
from mambo_explorer.modeling import cases as mc
from mambo_explorer.modeling import opf_network as on

H = 0.1


@pytest.fixture(scope="module")
def runs():
    keys = ("near-breakpoint", "capacity-edge", "zero-demand", "congested", "breakpoint")
    return {k: adapter.run_dc_opf(mc.run_inputs(k)) for k in keys}


def _rows(record, bus="C"):
    s = next(x for x in record.sensitivities if x["bus"] == bus)
    return {d["direction"]: d for d in sensitivity.directions(s, H)}


def test_breakpoint_closer_than_the_step_gives_a_blended_average(runs):
    r = runs["near-breakpoint"]
    assert r.status == "optimal" and r.price_status == "withheld" and r.prices == []
    rows = _rows(r)
    up, down = rows["increase"], rows["decrease"]
    assert up["feasible"] and down["feasible"]
    assert up["cost_change_per_h"] == pytest.approx(2.5, abs=1e-6)
    assert up["rate_per_mwh"] == pytest.approx(25.0, abs=1e-6)
    assert down["cost_change_per_h"] == pytest.approx(-2.0, abs=1e-6)
    assert down["rate_per_mwh"] == pytest.approx(20.0, abs=1e-6)
    # The 25 is not the local slope: a change inside the headroom still costs 20.
    inputs = mc.run_inputs("near-breakpoint")
    base = solve_dc_opf(on.build_network(inputs)).objective_cost
    small = solve_dc_opf(on.build_network(inputs, extra_load_mw={"C": 0.01})).objective_cost
    assert (small - base) / 0.01 == pytest.approx(20.0, abs=1e-4)


def test_blended_note_never_calls_an_average_a_local_rate(runs):
    note = runs["near-breakpoint"].price_note
    assert "average cost rates over a +0.1 MW and a −0.1 MW change of demand differ" in note
    assert "blends the rates on either side" in note
    assert "neither average is presented as a local (one-sided) marginal rate" in note
    assert "a unique two-sided marginal price was not verified for this run" in note
    for wrong in ("One-sided rates are shown", "Breakpoint at bus"):
        assert wrong not in note


def test_blended_rate_exercise_derives_the_blend(runs):
    records = {"near-breakpoint": runs["near-breakpoint"]}
    ex = mx.generate({"exercise_id": "x", "generator": "blended_rate"}, records)
    assert ex.options[ex.answer_index] == (
        "A blend: the first 0.05 MW comes from G1 at 20 and the remaining 0.05 MW from G2 at "
        "30. It is an average over the change, not a local marginal rate."
    )
    assert "(0.05 × 20 + 0.05 × 30) ÷ 0.1 = 25" in ex.explanation


def test_increase_only_infeasibility_names_only_that_direction(runs):
    r = runs["capacity-edge"]
    assert r.status == "optimal" and r.price_status == "withheld"
    rows = _rows(r)
    assert not rows["increase"]["feasible"] and rows["increase"]["rate_per_mwh"] is None
    assert rows["decrease"]["feasible"]
    assert rows["decrease"]["cost_change_per_h"] == pytest.approx(-3.0, abs=1e-6)
    assert rows["decrease"]["rate_per_mwh"] == pytest.approx(30.0, abs=1e-6)
    assert sensitivity.infeasible_sides(r.sensitivities) == {b: ["increase"] for b in "ABC"}
    note = r.price_note
    assert "a +0.1 MW change of demand is infeasible" in note
    assert "the −0.1 MW change is feasible" in note
    assert "The base run itself is optimal and verified." in note
    for wrong in ("more or less", "both a +0.1 MW", "−0.1 MW change of demand is infeasible"):
        assert wrong not in note


def test_decrease_only_infeasibility_names_only_that_direction(runs):
    r = runs["zero-demand"]
    assert r.status == "optimal" and r.price_status == "withheld"
    assert r.cost_rate_per_h == pytest.approx(0.0, abs=1e-9)
    rows = _rows(r)
    assert rows["increase"]["feasible"]
    assert rows["increase"]["cost_change_per_h"] == pytest.approx(2.0, abs=1e-6)
    assert rows["increase"]["rate_per_mwh"] == pytest.approx(20.0, abs=1e-6)
    assert not rows["decrease"]["feasible"] and rows["decrease"]["cost_change_per_h"] is None
    assert sensitivity.infeasible_sides(r.sensitivities) == {b: ["decrease"] for b in "ABC"}
    note = r.price_note
    assert "a −0.1 MW change of demand is infeasible" in note
    assert "the +0.1 MW change is feasible" in note
    assert "more or less" not in note and "+0.1 MW change of demand is infeasible" not in note


def test_both_directions_infeasible_is_worded_as_both():
    sens = [{"bus": "C", "up_per_mwh": None, "down_per_mwh": None}]
    assert "both a +0.1 MW and a −0.1 MW change of demand are infeasible" in (
        sensitivity.unservable_note(sens, H)
    )


def test_both_directions_feasible_signs_and_units(runs):
    r = runs["congested"]
    assert r.price_status == "verified" and r.price_note is None
    for bus, price in (("A", 20.0), ("B", 30.0), ("C", 40.0)):
        rows = _rows(r, bus)
        up, down = rows["increase"], rows["decrease"]
        assert up["change_mw"] == pytest.approx(H) and down["change_mw"] == pytest.approx(-H)
        # increase: C(D+h) − C(D) > 0; decrease: C(D−h) − C(D) < 0; both rates positive.
        assert up["cost_change_per_h"] == pytest.approx(price * H, abs=1e-6)
        assert down["cost_change_per_h"] == pytest.approx(-price * H, abs=1e-6)
        assert up["rate_per_mwh"] == pytest.approx(price, abs=1e-6)
        assert down["rate_per_mwh"] == pytest.approx(price, abs=1e-6)
    assert sensitivity.RATE_UNIT == "$/MWh" and sensitivity.CHANGE_UNIT == "$/h"
    assert sensitivity.INCREASE_FORMULA == "[C(D + h) − C(D)] / h"
    assert sensitivity.DECREASE_FORMULA == "[C(D) − C(D − h)] / h"


def test_records_saved_before_stage_9_rebuild_cost_changes_with_correct_signs():
    old = {"bus": "C", "up_per_mwh": 30.0, "down_per_mwh": 20.0}  # no cost-change fields
    rows = {d["direction"]: d for d in sensitivity.directions(old, H)}
    assert rows["increase"]["cost_change_per_h"] == pytest.approx(3.0)
    assert rows["decrease"]["cost_change_per_h"] == pytest.approx(-2.0)


def test_price_gate_decisions_are_unchanged():
    """The wording changed; the gate did not. Decisions match the Stage 7/8 expectations."""
    expected = {
        "congested": "verified",
        "uncongested": "verified",
        "relaxed": "verified",
        "equal": "verified",
        "breakpoint": "withheld",
        "ac-at-limit": "withheld",
        "capacity-edge": "withheld",
        "near-breakpoint": "withheld",
        "zero-demand": "withheld",
        "infeasible": "not available",
    }
    for key, status in expected.items():
        assert adapter.run_dc_opf(mc.run_inputs(key)).price_status == status, key


def test_an_infeasible_base_run_is_distinct_from_an_infeasible_perturbation(runs):
    base_infeasible = adapter.run_dc_opf(mc.run_inputs("infeasible"))
    assert base_infeasible.status == "infeasible"
    assert base_infeasible.sensitivities == [] and base_infeasible.price_note is None
    assert base_infeasible.dispatch == [] and base_infeasible.cost_rate_per_h is None
    edge = runs["capacity-edge"]
    assert edge.status == "optimal" and edge.dispatch and edge.cost_rate_per_h is not None


def test_a_failed_run_has_no_explanations_or_rates():
    def corrupt(net):
        result = solve_dc_opf(net)
        g = result.generators[0]
        return result.model_copy(
            update={
                "generators": [g.model_copy(update={"p_mw": g.p_mw + 5.0}), *result.generators[1:]]
            }
        )

    r = adapter.run_dc_opf(mc.run_inputs("near-breakpoint"), solver=corrupt)
    assert r.status == "failed"
    assert r.sensitivities == [] and r.price_note is None and r.prices == []


def test_records_from_older_checks_are_stale(runs):
    record = copy.deepcopy(runs["congested"])
    assert record.checks_version == adapter.CHECKS_VERSION
    assert mc.is_current("congested", {"congested": record})
    record.checks_version = "1.1.0"  # produced with the Stage 8 wording
    assert not mc.is_current("congested", {"congested": record})
    record.checks_version = None  # saved before versions were recorded
    assert not mc.is_current("congested", {"congested": record})


def test_changed_interpretation_changes_exercise_snapshots(runs, monkeypatch):
    records = {"breakpoint": runs["breakpoint"]}
    before = mx.snapshot(("breakpoint",), records)[0]
    monkeypatch.setattr(mx, "VERSION", "0.0.1")
    assert mx.snapshot(("breakpoint",), records)[0] != before


def test_no_page_source_keeps_the_old_wording():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src/mambo_explorer"
    text = "\n".join(p.read_text("utf-8") for p in root.rglob("*.py"))
    content = root / "content"
    text += "\n".join(
        p.read_text("utf-8") for p in [*content.rglob("*.md"), *content.rglob("*.yaml")]
    )
    for wrong in (
        "One-sided rates are shown",
        "slightly more or less demand cannot be met",
        "+0.1 MW demand ($/MWh)",
        "One-sided rates where prices were withheld",
        "both one-sided rates are shown",
    ):
        assert wrong not in text, wrong
