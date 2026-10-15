"""Lesson 14 exercises. Answers come from the stored HB_NORTH day-ahead prices for the learner's
chosen DeliveryDate; the snapshot is price_view.snapshot_id, so a revision or another day gives
new questions and invalidates old answers. No current price, extreme, or row count is hardcoded.
"""

from __future__ import annotations

from mambo_explorer.ercot import prices as px
from mambo_explorer.exercises import Exercise, Unavailable, _order
from mambo_explorer.price_view import PriceHour, coverage, snapshot_id

CALCULATION_ID = "dam_price_reading"
NOT_A_BILL = (
    "A wholesale day-ahead price at one hub; a retail bill adds other charges and contract "
    "terms, and real-time prices can differ"
)
FINALITY = (
    "Not determined here: ERCOT says DAM prices are final at 1000 on the second Business Day "
    "after the Operating Day, and corrections are a separate report"
)


def _p(v: float) -> str:
    return f"{v:,.2f} {px.UNIT}"


def _ex(ex_id, sid, question, correct, decoys, explanation):
    chosen = [d for d in dict.fromkeys(decoys) if d and d != correct][:3]
    options, answer = _order(sid, correct, chosen)
    if len(options) < 3:
        return Unavailable(ex_id, "this day makes the options coincide; choose another day")
    return Exercise(ex_id, sid, question, options, answer, explanation, CALCULATION_ID)


def highest_hour(ex_id, day: str, hours: list[PriceHour]):
    valid = [h for h in hours if h.value is not None]
    if not valid:
        return Unavailable(ex_id, "no valid prices for this DeliveryDate")
    top = max(valid, key=lambda h: (h.value, h.row_order))
    low = min(valid, key=lambda h: (h.value, h.row_order))
    mean = sum(h.value for h in valid) / len(valid)
    sid = snapshot_id(day, hours)
    return _ex(
        ex_id,
        sid,
        f"On DeliveryDate {day} (ERCOT labels), which HourEnding had the highest day-ahead "
        f"price at {px.LOCATION}?",
        f"{top.label}: {_p(top.value)}",
        [
            f"{low.label}: {_p(low.value)}",
            f"Every hour: {_p(mean)} (the average)",
            f"{valid[0].label}: {_p(valid[0].value)}" if valid[0] is not top else "",
            f"{valid[-1].label}: {_p(valid[-1].value)}" if valid[-1] is not top else "",
            "It cannot be read without the real-time price",
        ],
        f"Among {len(valid)} valid hourly prices the largest is {_p(top.value)} at HourEnding "
        f"{top.label}. The labels are ERCOT's own; the price varies by hour because the DAM "
        "clears each hour separately. This says nothing about why that hour was highest.",
    )


def negative_count(ex_id, day: str, hours: list[PriceHour]):
    c = coverage(hours)
    sid = snapshot_id(day, hours)
    n = c["negative"]
    return _ex(
        ex_id,
        sid,
        f"How many hours on DeliveryDate {day} have a NEGATIVE day-ahead price at {px.LOCATION}, "
        "and how are they shown?",
        f"{n}, shown as published (below zero), never changed to zero",
        [
            f"{n}, but this app sets them to zero",
            f"{n + 1}, shown as published",
            "0: settlement point prices cannot be negative",
            f"{max(n - 1, 0) if n else 2}, shown as published",
        ],
        f"Counting the stored prices below zero gives {n}. Day-ahead settlement point prices can "
        "be negative; this app keeps the sign exactly as ERCOT published it.",
    )


def missing_not_zero(ex_id, day: str, hours: list[PriceHour]):
    c = coverage(hours)
    sid = snapshot_id(day, hours)
    return _ex(
        ex_id,
        sid,
        f"DeliveryDate {day} has {c['rows']} stored hourly rows, {c['missing']} of them missing a "
        "price. What does a missing price mean here?",
        "No price was published for that row; it is not zero and is never filled",
        [
            "The price was zero",
            "The price equals the previous hour's",
            "The price equals the day's average",
        ],
        "A blank price in the file is stored as missing. Filling it with zero or a neighbour "
        "would invent a value the source did not publish.",
    )


def not_a_bill(ex_id, day: str, hours: list[PriceHour]):
    if not hours:
        return Unavailable(ex_id, "no prices for this DeliveryDate")
    sid = snapshot_id(day, hours)
    return _ex(
        ex_id,
        sid,
        f"What is the {px.LOCATION} day-ahead price for HourEnding {hours[0].label} on {day}?",
        NOT_A_BILL,
        [
            "What a Texas household pays for electricity in that hour",
            "A guaranteed forecast of the real-time price",
            "The price of a forward contract for next month",
        ],
        "It is the Day-Ahead Market Settlement Point Price at one hub. Retail prices include "
        "delivery and other charges; real-time prices are set separately; forward prices are "
        "for later delivery periods.",
    )


def finality_unknown(ex_id, day: str, hours: list[PriceHour]):
    if not hours:
        return Unavailable(ex_id, "no prices for this DeliveryDate")
    sid = snapshot_id(day, hours)
    revised = coverage(hours)["revised"]
    return _ex(
        ex_id,
        sid,
        f"This computer downloaded the {day} prices successfully ({revised} hour(s) revised since "
        "first stored). Are they final?",
        FINALITY,
        [
            "Yes: a successful download means the price is final",
            "Yes: day-ahead prices never change after posting",
            "No: they always change in real time",
        ],
        "Finality is a rule about time and business days, plus a separate corrections report. "
        "This app records revisions it sees but does not decide finality.",
    )


GENERATORS = {
    "highest_hour": highest_hour,
    "negative_count": negative_count,
    "missing_not_zero": missing_not_zero,
    "not_a_bill": not_a_bill,
    "finality_unknown": finality_unknown,
}


def generate(spec: dict, day: str | None, hours: list[PriceHour] | None):
    if day is None or not hours:
        return Unavailable(spec["exercise_id"], "no day-ahead prices collected yet")
    return GENERATORS[spec["generator"]](spec["exercise_id"], day, hours)
