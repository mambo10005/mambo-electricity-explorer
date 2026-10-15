"""Generation-mix exercises (lesson 13). Answers come from calculations.generation_mix over the
learner's current window; the snapshot is calculations.snapshot_id of the generation
observations, so a new window, a revision, or a newly published category gives new questions
and invalidates old answers. Nothing about current categories, totals, or row counts is
hardcoded.
"""

from __future__ import annotations

from mambo_explorer import calculations as calc
from mambo_explorer.calculations import Observation, Selection
from mambo_explorer.eia import dataset as ds
from mambo_explorer.eia.dataset import unit_label
from mambo_explorer.exercises import Exercise, Unavailable, _fmt, _order

CALCULATION_ID = "generation_mix"
NEGATIVE_MEANING = (
    "Net storage (or station use above gross output): the category consumed more than it "
    "generated in that hour, as the EIA-930 instructions describe"
)
NOT_TOTAL = (
    "Not necessarily: it is the sum of the categories reported for that hour; the source's "
    "total net generation is not in this dataset"
)
ABSENT_MEANING = "No value was published for them; they are not zero and are not filled"
MIX_NOT_PRICE = (
    "Nothing: the mix does not identify the marginal unit or fuel, and prices are not in this data"
)


def _name(code: str) -> str:
    return f"{code} ({ds.energy_source_name(code).split(' (')[0]})"


def _ready(ex_id, observations, selection):
    result = calc.generation_mix(observations, selection)
    if not result.ok:
        return None, Unavailable(ex_id, result.reason or "generation mix unavailable")
    return result, None


def _ex(ex_id, sid, question, correct, decoys, explanation, calc_id=CALCULATION_ID):
    chosen = []
    for d in decoys:
        if d != correct and d not in chosen:
            chosen.append(d)
    options, answer = _order(sid, correct, chosen[:3])
    if len(options) < 3:
        return Unavailable(ex_id, "this window makes the options coincide; change the window")
    return Exercise(ex_id, sid, question, options, answer, explanation, calc_id)


def largest_category(ex_id: str, observations: list[Observation], selection: Selection):
    result, err = _ready(ex_id, observations, selection)
    if err:
        return err
    v = result.values
    largest = v["largest_category_by_energy"]
    if largest is None:
        return Unavailable(ex_id, "no category has a valid value in this window")
    sid = calc.snapshot_id(observations, selection)
    unit = unit_label(result.unit)
    sums = {c: p["energy_sum"] for c, p in v["per_category"].items() if p["energy_sum"] is not None}
    others = sorted((c for c in sums if c != largest), key=lambda c: -sums[c])
    decoys = [_name(c) for c in others[:3]]
    fallback = ["It cannot be told from signed hourly values", "The category with the most hours"]
    return _ex(
        ex_id,
        sid,
        f"Over the selected window ({selection.start_period} to {selection.end_period} UTC "
        "labels), which category had the largest net generation, summing its valid hourly "
        "values?",
        _name(largest),
        decoys + fallback,
        f"Summing valid hourly values per category, {_name(largest)} is largest at "
        f"{_fmt(sums[largest])} {unit}. Absent and null hours add nothing; negative hours "
        "subtract. This says nothing about capacity, fuel used, or which unit set the price.",
    )


def negative_meaning(ex_id: str, observations: list[Observation], selection: Selection):
    result, err = _ready(ex_id, observations, selection)
    if err:
        return err
    v = result.values
    sid = calc.snapshot_id(observations, selection)
    negatives = v["categories_with_negative_hours"]
    if negatives:
        code = negatives[0]
        n = v["per_category"][code]["negative_hours"]
        question = (
            f"In this window, {_name(code)} is negative in {n} hour(s). According to the "
            "EIA-930 instructions, what does a negative net-generation value mean?"
        )
    else:
        question = (
            "No category is negative in this window. If one were, what would a negative "
            "net-generation value mean according to the EIA-930 instructions?"
        )
    return _ex(
        ex_id,
        sid,
        question,
        NEGATIVE_MEANING,
        [
            "A data error that this app corrects to zero",
            "Electricity exported to a neighboring balancing authority",
            "A forecast that turned out lower than actual demand",
        ],
        "The instructions say that for hours when storage devices store more electricity than "
        "they generate, the net storage is reported as negative net generation; station use "
        "above gross output also gives a negative value. This app keeps the sign exactly as "
        "published.",
    )


def absent_category_hours(ex_id: str, observations: list[Observation], selection: Selection):
    result, err = _ready(ex_id, observations, selection)
    if err:
        return err
    v = result.values
    sid = calc.snapshot_id(observations, selection)
    n, k = v["absent_category_hours"], len(v["categories"])
    correct = f"{_fmt(n)} absent category-hours. {ABSENT_MEANING}"
    return _ex(
        ex_id,
        sid,
        f"The window has {v['expected_labels']} hourly labels and {k} categories appear "
        "somewhere in it. How many category-hours have no row at all, and what do they mean?",
        correct,
        [
            f"{_fmt(n)} absent category-hours, each counted as 0 {unit_label(result.unit)}",
            f"{_fmt(v['expected_labels'] * k)} absent category-hours: every hour is missing",
            "0 absent category-hours: a category that exists always has a row",
            f"{_fmt(n + 1)} absent category-hours, filled from the previous hour",
        ],
        f"{k} categories × {v['expected_labels']} labels = {_fmt(v['expected_labels'] * k)} "
        f"possible rows; {_fmt(n)} of them are absent. An absent row is not a zero: the "
        "source published no value, and this app never fills gaps.",
    )


def partial_sum_not_total(ex_id: str, observations: list[Observation], selection: Selection):
    result, err = _ready(ex_id, observations, selection)
    if err:
        return err
    v = result.values
    sid = calc.snapshot_id(observations, selection)
    hour = next((h for h in v["hours"] if h["category_sum"] is not None), None)
    if hour is None:
        return Unavailable(ex_id, "no hour has a valid value in this window")
    unit = unit_label(result.unit)
    return _ex(
        ex_id,
        sid,
        f"At label {hour['period']}, the {hour['categories_present']} reported categor"
        f"{'y' if hour['categories_present'] == 1 else 'ies'} sum to "
        f"{_fmt(hour['category_sum'])} {unit}. Is that ERCOT's total net generation for the hour?",
        NOT_TOTAL,
        [
            "Yes: adding the categories always gives the system total",
            "Yes, and it also equals demand in that hour",
            "No: total generation is demand minus this sum",
        ],
        "The sum covers only the categories published for that hour. The instructions say the "
        "by-source values are expected to equal the reported total 'to the extent possible', "
        "and that total (data code SYS) is not collected here. Generation is not demand, and "
        "interchange or losses cannot be inferred from a difference.",
    )


def mix_not_price(ex_id: str, observations: list[Observation], selection: Selection):
    result, err = _ready(ex_id, observations, selection)
    if err:
        return err
    sid = calc.snapshot_id(observations, selection)
    largest = result.values["largest_category_by_energy"]
    lead = f"{_name(largest)} generated the most energy in this window. " if largest else ""
    return _ex(
        ex_id,
        sid,
        lead + "What does the generation mix alone tell you about which unit or fuel set the "
        "price in these hours?",
        MIX_NOT_PRICE,
        [
            "The largest category set the price",
            "The category with negative hours set the price",
            "The smallest positive category set the price, because it is marginal",
        ],
        "Which unit is marginal depends on offers, constraints, and dispatch (lessons 5–7), "
        "none of which are in net-generation observations. A large share is not evidence of "
        "price-setting.",
    )


GENERATORS = {
    "largest_category": largest_category,
    "negative_meaning": negative_meaning,
    "absent_category_hours": absent_category_hours,
    "partial_sum_not_total": partial_sum_not_total,
    "mix_not_price": mix_not_price,
}


def generate(spec: dict, observations: list[Observation] | None, selection: Selection | None):
    if observations is None or selection is None:
        return Unavailable(spec["exercise_id"], "no generation observations collected yet")
    return GENERATORS[spec["generator"]](spec["exercise_id"], observations, selection)
