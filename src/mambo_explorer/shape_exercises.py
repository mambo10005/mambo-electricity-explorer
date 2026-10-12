"""Time-shape exercises. Answers come from shape.evaluate() on the learner's CURRENT intervals;
the snapshot is the calculation id (every interval, B, K, scenario label and version, formula
version). Changing any input gives new questions. Options are kept distinct even when values
are zero or equal (fallback decoys), and hold at most one "$".
"""

from __future__ import annotations

from mambo_explorer import settlement as sm
from mambo_explorer import shape as sh
from mambo_explorer.exercises import Exercise, Unavailable, _order
from mambo_explorer.settlement_exercises import _m

CUR = sh.CURRENCY


def _ex(ex_id, r, question, correct, decoys, explanation, fallback=()):
    """Three distinct wrong options: the primary decoys first, then fallbacks if any coincide."""
    chosen: list[str] = []
    for d in (*decoys, *fallback):
        if d != correct and d not in chosen:
            chosen.append(d)
    options, answer = _order(r.snapshot_id, correct, chosen[:3])
    if len(options) < 3:
        return Unavailable(ex_id, "these inputs make the options coincide; change an input")
    return Exercise(
        ex_id, r.snapshot_id, question, options, answer, explanation, "time_shape", True
    )


def _setup(r: sh.Result) -> str:
    i = r.inputs
    return (
        f"Flat hedge B = {_m(i['hedge_mw'])} MW at K = {_m(i['fixed_price'])} over "
        f"{len(r.rows)} interval(s) totalling {_m(r.total_duration_h)} h."
    )


def interval_status(ex_id, r: sh.Result):
    x = max(r.rows, key=lambda y: abs(y.residual_mwh))
    gap = abs(x.residual_mwh)
    if x.status == "matched":
        correct = "Matched: hedge energy equals physical energy in every interval"
        decoys = [f"Underhedged by {_m(x.hedge_mwh)} MWh", f"Overhedged by {_m(x.hedge_mwh)} MWh"]
        question = f"{_setup(r)} In interval {x.interval_id}, how does the hedge compare with use?"
    else:
        other = "overhedged" if x.status == "underhedged" else "underhedged"
        correct = f"{x.status.capitalize()} by {_m(gap)} MWh"
        decoys = [f"{other.capitalize()} by {_m(gap)} MWh", "Matched: no mismatch"]
        question = (
            f"{_setup(r)} In interval {x.interval_id} the buyer uses {_m(x.energy_mwh)} MWh and "
            f"the hedge covers {_m(x.hedge_mwh)} MWh. How is that interval hedged?"
        )
    return _ex(
        ex_id,
        r,
        question,
        correct,
        decoys,
        f"Hedge energy h = B × d = {_m(r.inputs['hedge_mw'])} × {_m(x.duration_h)} = "
        f"{_m(x.hedge_mwh)} MWh. Mismatch q − h = {_m(x.residual_mwh)} MWh: positive is "
        "underhedged (more use than hedge), negative is overhedged.",
        fallback=[f"{x.status.capitalize()} by {_m(gap + 1)} MWh", "Not enough information"],
    )


def shape_component(ex_id, r: sh.Result):
    s = r.time_shape
    equal = abs(r.residual_mwh) < 1e-9
    lead = (
        "Total physical energy equals total hedge energy (R = 0)."
        if equal
        else f"The aggregate mismatch is R = {_m(r.residual_mwh)} MWh."
    )
    if abs(s) < 1e-9:
        correct = f"0 {CUR}: no mismatch meets a price different from p̄ here"
        decoys = [
            f"{_m(r.aggregate_mismatch)} {CUR}: R × p̄",
            f"{_m(r.net_cost)} {CUR}: the net cost",
            f"{_m(r.fixed_hedge_total)} {CUR}: B × D × K",
        ]
    else:
        correct = f"{_m(s)} {CUR}: interval mismatches meet different prices"
        decoys = [
            f"0 {CUR}: equal totals always mean no residual",
            f"{_m(-s)} {CUR}: interval mismatches meet different prices",
            f"{_m(r.aggregate_mismatch)} {CUR}: R × p̄",
        ]
    return _ex(
        ex_id,
        r,
        f"{_setup(r)} {lead} What is the time-shape component, Σ (q − h)(p − p̄)?",
        correct,
        decoys,
        f"Duration-weighted p̄ = {_m(r.average_price)}. Summing (q − h)(p − p̄) over intervals "
        f"gives {_m(s)}. Even when R = 0, energy over-hedged in one interval and under-hedged "
        "in another meets different prices, so the residual need not cancel. This split is an "
        "accounting decomposition, not a standard risk metric.",
        fallback=[f"{_m(s + 1000)} {CUR}", f"{_m(r.net_cost)} {CUR}: the net cost"],
    )


def mw_vs_mwh(ex_id, r: sh.Result):
    x = max(r.rows, key=lambda y: y.duration_h)
    b, d = r.inputs["hedge_mw"], x.duration_h
    return _ex(
        ex_id,
        r,
        f"The hedge is a constant {_m(b)} MW. Interval {x.interval_id} lasts {_m(d)} h. How much "
        "hedge energy does it cover?",
        f"{_m(b * d)} MWh (power × duration)",
        [
            f"{_m(b)} MWh (the MW figure read as energy)",
            f"{_m(b / d)} MWh (power ÷ duration)",
            f"{_m(b * d)} MW (an energy given as power)",
        ],
        f"Energy (MWh) = power (MW) × duration (h) = {_m(b)} × {_m(d)} = {_m(b * d)} MWh. MW is a "
        "rate; MWh is an amount. They share a number only when the interval lasts one hour.",
        fallback=[f"{_m(b * d + 1)} MWh", f"{_m(b + d)} MWh (power + duration)"],
    )


def profile_compare(ex_id, r: sh.Result):
    rev = sh.evaluate(sh.reversed_profile(_inputs(r)))
    diff = rev.net_cost - r.net_cost
    if abs(diff) < 1e-9:
        correct = "The same net cost: here the shape change does not change the cost"
    elif diff > 0:
        correct = f"Higher by {_m(diff)} {CUR}"
    else:
        correct = f"Lower by {_m(-diff)} {CUR}"
    return _ex(
        ex_id,
        r,
        f"{_setup(r)} Keep the same total energy ({_m(r.total_energy_mwh)} MWh) and prices, but "
        "use the interval energies in reverse order. How does the net cost change?",
        correct,
        [
            "The same net cost, because total energy is unchanged",
            f"{'Lower' if diff > 0 else 'Higher'} by {_m(abs(diff) or 1)} {CUR}",
        ],
        f"Recomputed: {_m(r.net_cost)} as entered, {_m(rev.net_cost)} reversed (time-shape "
        f"component {_m(r.time_shape)} vs {_m(rev.time_shape)}). Equal total energy does not "
        "mean equal exposure in each interval.",
        fallback=[f"Higher by {_m(abs(diff) + 1000)} {CUR}", "It cannot be compared"],
    )


def negative_receipt(ex_id, r: sh.Result):
    neg = [y for y in r.rows if y.hedge_receipt < 0]
    x = (
        min(neg, key=lambda y: y.hedge_receipt)
        if neg
        else max(r.rows, key=lambda y: y.hedge_receipt)
    )
    amt = abs(x.hedge_receipt)
    if x.hedge_receipt < 0:
        correct = f"The buyer pays {_m(amt)} {CUR} on the hedge in {x.interval_id}"
        decoys = [
            f"The buyer receives {_m(amt)} {CUR} in {x.interval_id}",
            "Electricity is returned",
        ]
    elif x.hedge_receipt > 0:
        correct = f"The buyer receives {_m(amt)} {CUR} on the hedge in {x.interval_id}"
        decoys = [f"The buyer pays {_m(amt)} {CUR} in {x.interval_id}", "Electricity is returned"]
    else:
        correct = f"No hedge cash flow in {x.interval_id}"
        decoys = [f"The buyer pays K × h in {x.interval_id}", "Electricity is returned"]
    return _ex(
        ex_id,
        r,
        f"{_setup(r)} In interval {x.interval_id} the spot price is {_m(x.price)}. The hedge "
        f"receipt there is h × (p − K) = {_m(x.hedge_receipt)}. What does it mean?",
        correct,
        decoys,
        f"h × (p − K) = {_m(x.hedge_mwh)} × ({_m(x.price)} − {_m(r.inputs['fixed_price'])}) = "
        f"{_m(x.hedge_receipt)}. When the spot price is below K the receipt is negative: the "
        "buyer pays. The hedge is a cash flow; no electricity moves.",
        fallback=[f"The buyer pays {_m(amt + 1)} {CUR} in {x.interval_id}"],
    )


def _inputs(r: sh.Result) -> sh.Inputs:
    i = r.inputs
    return sh.Inputs(
        intervals=tuple(sh.Interval(**iv) for iv in i["intervals"]),
        hedge_mw=i["hedge_mw"],
        fixed_price=i["fixed_price"],
        scenario=i["scenario"],
        scenario_version=i["scenario_version"],
    )


GENERATORS = {
    fn.__name__: fn
    for fn in (interval_status, shape_component, mw_vs_mwh, profile_compare, negative_receipt)
}


def generate(spec: dict, result: sh.Result | None):
    if result is None:
        return Unavailable(spec["exercise_id"], "the calculator has no valid result")
    try:
        return GENERATORS[spec["generator"]](spec["exercise_id"], result)
    except sm.SettlementError as exc:
        return Unavailable(spec["exercise_id"], f"not available for these inputs ({exc})")
