"""Lesson 15 exercises. Answers come from the stored HB_NORTH real-time intervals for the chosen
DeliveryDate; the snapshot is rt_price_view.snapshot_id, so a revision, a newly collected
interval, or another day gives new questions and invalidates old answers. No current price,
extreme, or interval count is hardcoded.
"""

from __future__ import annotations

from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.exercises import Exercise, Unavailable, _order
from mambo_explorer.rt_price_view import RtInterval, coverage, snapshot_id

CALCULATION_ID = "rt_price_reading"
SPP_NOT_LMP = (
    "A 15-minute settlement price produced from SCED LMPs, including ERCOT's reliability "
    "deployment price adder and a -$251/MWh floor"
)
NOT_INVOICE = (
    "No: an invoice also depends on metered quantities, day-ahead positions, ancillary "
    "services, and other charge types"
)
ABSENT = (
    "Unknown from this data: it may not be published yet, not collected, or outside ERCOT's "
    "public list; it is never treated as zero"
)


def _p(v: float) -> str:
    return f"{v:,.2f} {rt.UNIT}"


def _ex(ex_id, sid, question, correct, decoys, explanation):
    chosen = [d for d in dict.fromkeys(decoys) if d and d != correct][:3]
    options, answer = _order(sid, correct, chosen)
    if len(options) < 3:
        return Unavailable(ex_id, "this day makes the options coincide; choose another day")
    return Exercise(ex_id, sid, question, options, answer, explanation, CALCULATION_ID)


def highest_interval(ex_id, day: str, xs: list[RtInterval]):
    valid = [x for x in xs if x.value is not None]
    if not valid:
        return Unavailable(ex_id, "no valid prices for this DeliveryDate")
    top = max(valid, key=lambda x: (x.value, x.order))
    low = min(valid, key=lambda x: (x.value, x.order))
    first, last = valid[0], valid[-1]
    return _ex(
        ex_id,
        snapshot_id(day, xs),
        f"Among the {len(valid)} stored real-time intervals for DeliveryDate {day} (ERCOT "
        f"labels), which had the highest price at {rt.LOCATION}?",
        f"{top.label}: {_p(top.value)}",
        [
            f"{low.label}: {_p(low.value)}",
            f"{first.label}: {_p(first.value)}" if first is not top else "",
            f"{last.label}: {_p(last.value)}" if last is not top else "",
            "It cannot be read without the day-ahead price",
        ],
        f"The largest stored valid price is {_p(top.value)} at {top.label} (H = DeliveryHour, "
        "I = DeliveryInterval). Each value is one 15-minute interval; this says nothing about "
        "why that interval was highest, and intervals not stored are not considered.",
    )


def negative_count(ex_id, day: str, xs: list[RtInterval]):
    n = coverage(xs)["negative"]
    return _ex(
        ex_id,
        snapshot_id(day, xs),
        f"How many stored intervals on {day} have a NEGATIVE real-time price at {rt.LOCATION}?",
        f"{n}, kept below zero as published",
        [
            f"{n}, but this app sets them to zero",
            f"{n + 1}, kept below zero as published",
            "0: real-time prices cannot go below zero",
        ],
        f"Counting stored prices below zero gives {n}. ERCOT's Protocols allow negative real-time "
        "prices down to a -$251/MWh floor; the app keeps the sign.",
    )


def absent_interval(ex_id, day: str, xs: list[RtInterval]):
    c = coverage(xs)
    if not xs:
        return Unavailable(ex_id, "no intervals for this DeliveryDate")
    return _ex(
        ex_id,
        snapshot_id(day, xs),
        f"{c['stored']} intervals are stored for {day}. What does an interval that is NOT "
        "stored tell you about its price?",
        ABSENT,
        [
            "Its price was zero",
            "Its price equals the previous interval's",
            "Its price equals the hour's average of the stored intervals",
        ],
        "An absent interval has no stored value at all. Filling it from neighbours or averaging "
        "the stored intervals would invent a price ERCOT may never have published here.",
    )


def spp_vs_lmp(ex_id, day: str, xs: list[RtInterval]):
    if not xs:
        return Unavailable(ex_id, "no intervals for this DeliveryDate")
    return _ex(
        ex_id,
        snapshot_id(day, xs),
        f"What is the {rt.LOCATION} value shown for {xs[-1].label} on {day}?",
        SPP_NOT_LMP,
        [
            "A single SCED LMP from one five-minute dispatch run",
            "The day-ahead price for that hour",
            "A forecast of the next interval's price",
        ],
        "ERCOT describes this report as Settlement Point Prices 'produced from SCED LMPs every "
        "15 minutes'. For the North Hub, Protocols Section 3.5.2.1(4) adds the Real-Time "
        "Reliability Deployment Price Adder to time-weighted Hub Bus prices and floors the "
        "result at -$251/MWh.",
    )


def not_invoice(ex_id, day: str, xs: list[RtInterval]):
    if not xs:
        return Unavailable(ex_id, "no intervals for this DeliveryDate")
    return _ex(
        ex_id,
        snapshot_id(day, xs),
        f"Multiplying a meter reading by these {rt.LOCATION} prices: is that a complete "
        "real-time settlement invoice?",
        NOT_INVOICE,
        [
            "Yes: the price times energy is the whole invoice",
            "Yes, once the price is final",
            "Only for negative-price intervals",
        ],
        "Real-time settlement uses Settlement Point Prices, but an invoice has many charge "
        "types and quantities (lesson 8 shows a two-settlement teaching formula). This app does "
        "not reconstruct settlement, and finality is not determined.",
    )


GENERATORS = {
    "highest_interval": highest_interval,
    "negative_count": negative_count,
    "absent_interval": absent_interval,
    "spp_vs_lmp": spp_vs_lmp,
    "not_invoice": not_invoice,
}


def generate(spec: dict, day: str | None, xs: list[RtInterval] | None):
    if day is None or not xs:
        return Unavailable(spec["exercise_id"], "no real-time prices collected yet")
    return GENERATORS[spec["generator"]](spec["exercise_id"], day, xs)
