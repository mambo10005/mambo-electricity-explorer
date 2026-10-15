"""Basis-exposure exercises. Answers come from basis.evaluate() on the learner's CURRENT
calculator inputs; the snapshot is the calculation id (every input, each price's provenance,
the formula version). Changing any input gives new questions. Options hold at most one "$".
"""

from __future__ import annotations

from mambo_explorer import basis as bx
from mambo_explorer import settlement as sm
from mambo_explorer.exercises import Exercise, Unavailable, _order
from mambo_explorer.settlement_exercises import _m

CUR = bx.CURRENCY


def _ex(ex_id, r, question, correct, decoys, explanation):
    options, answer = _order(r.snapshot_id, correct, decoys)
    if len(options) < 3:
        return Unavailable(ex_id, "these inputs make the options coincide; change an input")
    return Exercise(
        ex_id, r.snapshot_id, question, options, answer, explanation, "basis_exposure", True
    )


def _given(r: bx.Result) -> str:
    i = r.inputs
    return (
        f"Physical {_m(i['physical_mwh'])} MWh at P_L = {_m(i['delivery_price'])}; hedge "
        f"{_m(i['hedge_mwh'])} MWh paying K = {_m(i['fixed_price'])} and receiving P_H = "
        f"{_m(i['reference_price'])} (synthetic dollars per MWh)."
    )


def net_cost(ex_id, r: bx.Result):
    i = r.inputs
    return _ex(
        ex_id,
        r,
        f"{_given(r)} What is the net buyer cost?",
        f"{_m(r.net_cost)} {CUR}",
        [
            f"{_m(r.physical_cost + r.hedge_receipt)} {CUR}",
            f"{_m(i['physical_mwh'] * i['fixed_price'])} {CUR}",
            f"{_m(r.physical_cost)} {CUR}",
        ],
        f"Physical cost Q × P_L = {_m(r.physical_cost)}. Hedge receipt H × (P_H − K) = "
        f"{_m(r.hedge_receipt)}. Net = {_m(r.physical_cost)} − ({_m(r.hedge_receipt)}) = "
        f"{_m(r.net_cost)}. Adding the receipt instead of subtracting it, or assuming the hedge "
        "fixes the whole cost at Q × K, gives a different number.",
    )


def hedge_cash_flow(ex_id, r: bx.Result):
    receipt = r.hedge_receipt
    if receipt > 0:
        correct = f"The buyer receives {_m(receipt)} {CUR}"
        decoys = [f"The buyer pays {_m(receipt)} {CUR}", "Nothing: a hedge only moves electricity"]
    elif receipt < 0:
        correct = f"The buyer pays {_m(-receipt)} {CUR}"
        decoys = [
            f"The buyer receives {_m(-receipt)} {CUR}",
            "Nothing: a hedge only moves electricity",
        ]
    else:
        correct = "No hedge cash flow"
        decoys = ["The buyer receives the fixed price K", "Nothing: a hedge only moves electricity"]
    decoys.append(
        f"The buyer receives {_m(r.inputs['hedge_mwh'] * r.inputs['reference_price'])} {CUR}"
    )
    return _ex(
        ex_id,
        r,
        f"{_given(r)} What happens on the hedge?",
        correct,
        decoys,
        f"Hedge receipt = H × (P_H − K) = {_m(r.inputs['hedge_mwh'])} × "
        f"({_m(r.inputs['reference_price'])} − {_m(r.inputs['fixed_price'])}) = {_m(receipt)}. "
        "When the reference price is below K the receipt is negative: the buyer pays. The hedge "
        "is a financial cash flow and delivers no electricity.",
    )


def basis_component(ex_id, r: bx.Result):
    i = r.inputs
    return _ex(
        ex_id,
        r,
        f"{_given(r)} How large is the location-basis component of the net cost?",
        f"{_m(r.basis_component)} {CUR}: Q × (P_L − P_H)",
        [
            f"{_m(-r.basis_component)} {CUR}: Q × (P_H − P_L)",
            f"{_m(i['hedge_mwh'] * r.basis)} {CUR}: H × basis",
            f"{_m(r.basis)} {CUR}: the basis itself",
        ],
        f"Basis = P_L − P_H = {_m(r.basis)} per MWh. The hedge pays on P_H, but the energy is "
        f"bought at P_L, so all Q MWh carry the basis: Q × basis = {_m(r.basis_component)}. A "
        "positive basis raises the buyer's net cost; a negative basis lowers it.",
    )


def mismatch_component(ex_id, r: bx.Result):
    i = r.inputs
    gap = i["physical_mwh"] - i["hedge_mwh"]
    return _ex(
        ex_id,
        r,
        f"{_given(r)} What is the quantity-mismatch component, (Q − H) × (P_H − K)?",
        f"{_m(r.mismatch_component)} {CUR}",
        [
            f"{_m(-r.mismatch_component)} {CUR}",
            f"{_m(gap * i['delivery_price'])} {CUR}",
            f"{_m(i['physical_mwh'] * (i['reference_price'] - i['fixed_price']))} {CUR}",
            f"{_m(i['reference_price'] - i['fixed_price'])} {CUR}",
        ],
        f"Q − H = {_m(gap)} MWh and P_H − K = "
        f"{_m(i['reference_price'] - i['fixed_price'])}, so the "
        f"component is {_m(r.mismatch_component)}. It is zero when the hedge quantity matches the "
        f"physical energy. Here the position is: {r.position}.",
    )


def hedge_effect(ex_id, r: bx.Result):
    i = r.inputs
    unhedged = i["physical_mwh"] * i["delivery_price"]
    change = r.net_cost - unhedged
    if change > 0:
        correct = f"The hedge raised the cost by {_m(change)} {CUR}"
    elif change < 0:
        correct = f"The hedge lowered the cost by {_m(-change)} {CUR}"
    else:
        correct = "The hedge did not change the cost"
    return _ex(
        ex_id,
        r,
        f"{_given(r)} Compared with no hedge (cost Q × P_L), what did the hedge do in this "
        "scenario?",
        correct,
        [
            "A hedge always lowers the cost",
            "The hedge removed all price risk",
            f"The hedge {'lowered' if change > 0 else 'raised'} the cost by "
            f"{_m(abs(change) or 1)} {CUR}",
        ],
        f"Without the hedge the cost is {_m(unhedged)}; with it, {_m(r.net_cost)}. The difference "
        f"is −(hedge receipt) = {_m(change)}. When P_H ends below K the hedge costs money; it "
        "trades price risk for a fixed price on H MWh. It does not guarantee savings and leaves "
        "basis and quantity-mismatch exposure.",
    )


GENERATORS = {
    fn.__name__: fn
    for fn in (net_cost, hedge_cash_flow, basis_component, mismatch_component, hedge_effect)
}


def generate(spec: dict, result: bx.Result | None):
    if result is None:
        return Unavailable(spec["exercise_id"], "the calculator has no valid result")
    try:
        return GENERATORS[spec["generator"]](spec["exercise_id"], result)
    except sm.SettlementError as exc:
        return Unavailable(spec["exercise_id"], f"not available for these inputs ({exc})")
