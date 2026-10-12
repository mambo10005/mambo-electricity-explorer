"""Settlement exercises. Every answer comes from settlement.settle() on the learner's CURRENT
calculator inputs; the exercise snapshot is the calculation id, which covers every input,
each price's provenance, and the formula version. Changing any input gives a new question.
Options hold at most one "$" (radio options are rendered as Markdown).
"""

from __future__ import annotations

from dataclasses import replace

from mambo_explorer import settlement as sm
from mambo_explorer.exercises import Exercise, Unavailable, _order

CUR = sm.CURRENCY


def _m(x: float) -> str:
    x = round(x, 2) + 0.0
    text = f"{x:,.2f}".replace("-", "−")
    return text[:-3] if text.endswith(".00") else text


def _inputs(result: sm.Result) -> sm.Inputs:
    i = result.inputs
    return sm.Inputs(
        scheduled_energy_mwh=i["scheduled_energy_mwh"],
        actual_energy_mwh=i["actual_energy_mwh"],
        day_ahead_price=i["day_ahead_price"],
        real_time_price=i["real_time_price"],
        day_ahead_source=sm.PriceSource(**i["day_ahead_source"]),
        real_time_source=sm.PriceSource(**i["real_time_source"]),
    )


def _ex(ex_id, r, question, correct, decoys, explanation):
    options, answer = _order(r.snapshot_id, correct, decoys)
    if len(options) < 3:
        return Unavailable(ex_id, "these inputs make the options coincide; change an input")
    return Exercise(
        ex_id, r.snapshot_id, question, options, answer, explanation, "energy_settlement", True
    )


def _given(r: sm.Result) -> str:
    i = r.inputs
    return (
        f"Scheduled {_m(i['scheduled_energy_mwh'])} MWh at a day-ahead price of "
        f"{_m(i['day_ahead_price'])}; actual {_m(i['actual_energy_mwh'])} MWh with a real-time "
        f"price of {_m(i['real_time_price'])} (synthetic dollars per MWh)."
    )


def total_amount(ex_id, r: sm.Result):
    i = r.inputs
    flipped = r.day_ahead_component - r.deviation_component
    return _ex(
        ex_id,
        r,
        f"{_given(r)} What is the signed energy-settlement amount?",
        f"{_m(r.total)} {CUR}",
        [
            f"{_m(i['actual_energy_mwh'] * i['real_time_price'])} {CUR}",
            f"{_m(r.day_ahead_component)} {CUR}",
            f"{_m(flipped)} {CUR}",
        ],
        f"Day-ahead component {_m(i['scheduled_energy_mwh'])} × {_m(i['day_ahead_price'])} = "
        f"{_m(r.day_ahead_component)}. Deviation ({_m(r.deviation_mwh)} MWh) × "
        f"{_m(i['real_time_price'])} = {_m(r.deviation_component)}. Total "
        f"{_m(r.total)} synthetic dollars. Pricing all actual energy at the real-time price, "
        "or ignoring the deviation, gives a different number unless the two prices are equal "
        "or the deviation is zero.",
    )


def deviation_component(ex_id, r: sm.Result):
    i = r.inputs
    return _ex(
        ex_id,
        r,
        f"{_given(r)} What is the deviation component?",
        f"{_m(r.deviation_component)} {CUR}: ({_m(r.deviation_mwh)} MWh) × the real-time price",
        [
            f"{_m(r.deviation_mwh * i['day_ahead_price'])} {CUR}: "
            "the deviation × the day-ahead price",
            f"{_m(abs(r.deviation_mwh) * i['real_time_price'])} {CUR}: the deviation's size, "
            "sign ignored",
            f"{_m(i['actual_energy_mwh'] * i['real_time_price'])} {CUR}: all actual energy × the "
            "real-time price",
        ],
        f"Deviation = actual − scheduled = {_m(i['actual_energy_mwh'])} − "
        f"{_m(i['scheduled_energy_mwh'])} = {_m(r.deviation_mwh)} MWh. Only the deviation is "
        f"settled at the real-time price: {_m(r.deviation_mwh)} × {_m(i['real_time_price'])} = "
        f"{_m(r.deviation_component)}. Its sign matters: less energy than scheduled gives a "
        "negative deviation.",
    )


def role_reading(ex_id, r: sm.Result):
    readings = {
        "buyer": r.buyer_reading(),
        "seller": r.seller_reading(),
    }
    correct = f"Buyer: {readings['buyer']}"
    decoys = [
        f"Buyer: {readings['seller']}",
        "Buyer: the sign is irrelevant; only the size matters",
    ]
    opposite = (
        "The buyer pays this amount."
        if r.total < 0
        else ("Negative: under these teaching assumptions it is a credit to the buyer.")
    )
    decoys.append(f"Buyer: {opposite}")
    return _ex(
        ex_id,
        r,
        f"The total is {_m(r.total)} synthetic dollars. Using this app's sign convention, what "
        "does it mean for a buyer?",
        correct,
        decoys,
        "One signed amount, read by role: a buyer pays it and a seller receives it. A negative "
        "amount is a credit to a buyer under these teaching assumptions. (This is the app's "
        "teaching convention; actual invoices use their own sign conventions.)",
    )


def volume_exposure(ex_id, r: sm.Result):
    more = sm.settle(replace(_inputs(r), actual_energy_mwh=r.inputs["actual_energy_mwh"] + 1.0))
    change = more.total - r.total
    i = r.inputs
    return _ex(
        ex_id,
        r,
        f"{_given(r)} If actual energy were 1 MWh higher (everything else unchanged), how would "
        "the total change?",
        f"By {_m(change)} {CUR}: the real-time price",
        [
            f"By {_m(i['day_ahead_price'])} {CUR}: the day-ahead price",
            f"By {_m(i['real_time_price'] - i['day_ahead_price'])} {CUR}: the price difference",
            "It would not change: the schedule is fixed",
        ],
        f"Recomputed with {_m(i['actual_energy_mwh'] + 1)} MWh: the total changes by "
        f"{_m(change)}, the real-time price. Energy above or below the schedule is exposed to "
        "the real-time price (volume exposure); the scheduled part is already priced day-ahead.",
    )


def price_exposure(ex_id, r: sm.Result):
    up = sm.settle(replace(_inputs(r), real_time_price=r.inputs["real_time_price"] + 1.0))
    change = up.total - r.total
    i = r.inputs
    return _ex(
        ex_id,
        r,
        f"{_given(r)} If the real-time price were 1 higher (everything else unchanged), how "
        "would the total change?",
        f"By {_m(change)} {CUR}: one per MWh of deviation",
        [
            f"By {_m(i['actual_energy_mwh'])} {CUR}: one per MWh of actual energy",
            f"By {_m(i['scheduled_energy_mwh'])} {CUR}: one per MWh scheduled",
            f"By {_m(abs(r.deviation_mwh) + 1)} {CUR}",
        ],
        f"Recomputed with a real-time price of {_m(i['real_time_price'] + 1)}: the total changes "
        f"by {_m(change)}, which is the deviation in MWh ({_m(r.deviation_mwh)}). Only the "
        "deviation is exposed to the real-time price (price exposure); with no deviation, a "
        "real-time price change does not change this teaching total.",
    )


GENERATORS = {
    fn.__name__: fn
    for fn in (total_amount, deviation_component, role_reading, volume_exposure, price_exposure)
}


def generate(spec: dict, result: sm.Result | None):
    if result is None:
        return Unavailable(spec["exercise_id"], "the calculator has no valid result")
    try:
        return GENERATORS[spec["generator"]](spec["exercise_id"], result)
    except sm.SettlementError as exc:  # e.g. +1 would leave the allowed input range
        return Unavailable(spec["exercise_id"], f"not available for these inputs ({exc})")
