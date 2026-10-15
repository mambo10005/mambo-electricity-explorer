"""Exercise generators. Answers come from the shared calculation services.

A data exercise is generated from a fixed observation snapshot (calculations.snapshot_id)
and is deterministic for that snapshot: the same snapshot always produces the same
question, options, and answer. A new snapshot (different selection or revised data)
produces a new question. Nothing about current row counts or missing blocks is
hardcoded.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from mambo_explorer import calculations as calc
from mambo_explorer.calculations import Observation, Selection
from mambo_explorer.eia.dataset import unit_label


@dataclass(frozen=True)
class Exercise:
    exercise_id: str
    snapshot_id: str
    question: str
    options: tuple[str, ...]
    answer_index: int
    explanation: str
    calculation_id: str
    synthetic: bool = False
    result_refs: tuple[str, ...] = ()  # model run ids the answer was computed from


@dataclass(frozen=True)
class Unavailable:
    exercise_id: str
    reason: str


def _fmt(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


def _pick(seed: str, items: list):
    """Deterministic choice from a snapshot fingerprint (no global random state)."""
    index = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(items)
    return items[index]


def _order(seed: str, correct: str, decoys: list[str]) -> tuple[tuple[str, ...], int]:
    options = [correct]
    for d in decoys:
        if d not in options:
            options.append(d)
    options.sort(key=lambda o: hashlib.sha256((seed + o).encode()).hexdigest())
    return tuple(options), options.index(correct)


# --- concept exercises (synthetic numbers, always labeled) -----------------------------------


def power_energy_synthetic(ex_id: str, observations=None, selection=None):
    result = calc.power_energy(average_mw=250, hours=4)
    energy = result.values["energy_mwh"]
    options, answer = _order(
        "power-energy", f"{_fmt(energy)} MWh", ["250 MWh", "62.5 MWh", "1,000 MW"]
    )
    return Exercise(
        ex_id,
        "synthetic",
        "SYNTHETIC EXAMPLE (not real data): a generator runs at an "
        "average of 250 MW for 4 hours. How much energy does it produce?",
        options,
        answer,
        f"Energy = average power × duration = 250 MW × 4 h = {_fmt(energy)} MWh. "
        "'1,000 MW' has the right number but the wrong unit: MW measures a rate, MWh an amount.",
        "power_energy",
        synthetic=True,
    )


def one_hour_equivalence(ex_id: str, observations=None, selection=None):
    result = calc.power_energy(energy_mwh=48_000, hours=1)
    mw = result.values["average_mw"]
    options, answer = _order(
        "one-hour",
        f"{_fmt(mw)} MW, but only because the duration is exactly 1 hour",
        ["48,000 MW for any duration", "2,000 MW (48,000 ÷ 24)", "It cannot be converted"],
    )
    return Exercise(
        ex_id,
        "synthetic",
        "SYNTHETIC EXAMPLE: 48,000 MWh of energy was used during one "
        "1-hour period. What was the average power over that hour?",
        options,
        answer,
        f"Average power = energy ÷ duration = 48,000 MWh ÷ 1 h = {_fmt(mw)} MW. The numbers "
        "match only because the duration is 1 hour; over 2 hours the same energy would mean "
        "24,000 MW.",
        "power_energy",
        synthetic=True,
    )


def absent_not_zero(ex_id: str, observations=None, selection=None):
    correct = "Nothing is known about that hour's forecast from this data; it is not zero"
    options, answer = _order(
        "absent-zero",
        correct,
        [
            "The forecast was 0 MWh",
            "Demand was 0 MWh in that hour",
            "The actual demand row must also be missing",
        ],
    )
    return Exercise(
        ex_id,
        "concept",
        "If an hour has an actual-demand row but NO forecast row, what does "
        "that tell you about the forecast for that hour?",
        options,
        answer,
        "An absent row means the value is not in the data you have. It is different from a "
        "reported 0. Demand that hour is still shown by its own row. This lesson does not "
        "say why the row is missing.",
        "coverage",
    )


# --- data exercises (from the selected snapshot) -----------------------------------------


def demand_max(ex_id: str, observations: list[Observation], selection: Selection):
    result = calc.series_summary(observations, selection, "D")
    if not result.ok:
        return Unavailable(ex_id, result.reason or "summary unavailable")
    v = result.values
    sid = calc.snapshot_id(observations, selection)
    correct = f"{_fmt(v['max'])} {unit_label(result.unit)} at {v['max_period']}"
    decoys = [
        f"{_fmt(v['min'])} {unit_label(result.unit)} at {v['min_period']}",
        f"{_fmt(v['mean'])} {unit_label(result.unit)} (the average)",
        f"{_fmt(v['range'])} {unit_label(result.unit)} (the range, max − min)",
    ]
    options, answer = _order(sid, correct, decoys)
    return Exercise(
        ex_id,
        sid,
        f"In the selected window ({selection.start_period} to "
        f"{selection.end_period} UTC labels), what was the highest actual-demand value?",
        options,
        answer,
        f"The largest valid value among {v['valid_values']} observations is {_fmt(v['max'])} "
        f"{unit_label(result.unit)}, labeled {v['max_period']}. The range "
        f"({_fmt(v['range'])}) is the difference between the highest and lowest values, "
        "not a value itself.",
        "series_summary",
    )


def error_sign(ex_id: str, observations: list[Observation], selection: Selection):
    result = calc.forecast_error(observations, selection)
    if not result.ok:
        return Unavailable(ex_id, result.reason or "no matched pairs")
    sid = calc.snapshot_id(observations, selection)
    nonzero = [p for p in result.values["pair_errors"] if p["error"] != 0]
    if not nonzero:
        return Unavailable(ex_id, "every matched pair has zero error")
    pair = _pick(sid, nonzero)
    e = pair["error"]
    unit = unit_label(result.unit)
    above = f"{'+' if e > 0 else '−'}{_fmt(abs(e))} {unit}: actual was " + (
        "ABOVE the forecast (under-forecast)" if e > 0 else "BELOW the forecast (over-forecast)"
    )
    flipped = f"{'−' if e > 0 else '+'}{_fmt(abs(e))} {unit}: actual was " + (
        "BELOW the forecast (over-forecast)" if e > 0 else "ABOVE the forecast (under-forecast)"
    )
    options, answer = _order(
        sid,
        above,
        [
            flipped,
            f"{_fmt(abs(e))} {unit}: the sign does not matter",
            f"{_fmt(pair['actual'] + pair['forecast'])} {unit}: actual plus forecast",
        ],
    )
    return Exercise(
        ex_id,
        sid,
        f"At label {pair['period']}, actual demand was {_fmt(pair['actual'])} {unit} "
        f"and the published forecast was {_fmt(pair['forecast'])} {unit}. Using "
        "error = actual − forecast, what is the error and what does its sign mean?",
        options,
        answer,
        f"{_fmt(pair['actual'])} − {_fmt(pair['forecast'])} = {'+' if e > 0 else '−'}"
        f"{_fmt(abs(e))} {unit}. A positive error means demand came in above the forecast; "
        "a negative error means it came in below.",
        "forecast_error",
    )


def mae_value(ex_id: str, observations: list[Observation], selection: Selection):
    result = calc.forecast_error(observations, selection)
    if not result.ok:
        return Unavailable(ex_id, result.reason or "no matched pairs")
    sid = calc.snapshot_id(observations, selection)
    v, unit = result.values, unit_label(result.unit)
    correct = f"{_fmt(v['mae'])} {unit}"
    decoys = [
        f"{_fmt(v['mean_error'])} {unit} (mean error)",
        f"{_fmt(v['rmse'])} {unit} (RMSE)",
        f"{_fmt(v['mae'] * v['pairs'])} {unit} (sum, not average)",
    ]
    options, answer = _order(sid, correct, decoys)
    excluded = len(result.exclusions)
    return Exercise(
        ex_id,
        sid,
        f"Over the {v['pairs']} matched hours in this window, what is the mean "
        "absolute error (MAE) of the published forecast?",
        options,
        answer,
        f"MAE averages the size of each error ignoring its sign: Σ|actual − forecast| ÷ "
        f"{v['pairs']} = {_fmt(v['mae'])} {unit}. Mean error ({_fmt(v['mean_error'])}) lets "
        f"positive and negative errors cancel; RMSE ({_fmt(v['rmse'])}) weights large misses "
        f"more. {excluded} hour(s) in the window were excluded because a value was missing.",
        "forecast_error",
    )


def forecast_absent_count(ex_id: str, observations: list[Observation], selection: Selection):
    result = calc.coverage(observations, selection, "DF")
    actual = calc.coverage(observations, selection, "D")
    if not result.ok or not actual.ok:
        return Unavailable(ex_id, "coverage unavailable")
    sid = calc.snapshot_id(observations, selection)
    n, expected = result.values["absent_rows"], result.values["expected_labels"]
    correct = f"{n} of {expected} hourly labels"
    decoys = [
        f"{actual.values['absent_rows']} of {expected} hourly labels (that is actual demand)",
        f"{expected - n} of {expected} hourly labels (those are present)",
        f"{n + 24} of {expected} hourly labels",
    ]
    options, answer = _order(sid, correct, decoys)
    return Exercise(
        ex_id,
        sid,
        f"Between labels {selection.start_period} and {selection.end_period} "
        f"there are {expected} hourly labels. For how many is the FORECAST row absent?",
        options,
        answer,
        f"Counting labels with no forecast row gives {n}. Actual demand has its own count "
        f"({actual.values['absent_rows']} absent). Coverage is measured separately for each "
        "series.",
        "coverage",
    )


GENERATORS = {
    "power_energy_synthetic": power_energy_synthetic,
    "one_hour_equivalence": one_hour_equivalence,
    "absent_not_zero": absent_not_zero,
    "demand_max": demand_max,
    "error_sign": error_sign,
    "mae_value": mae_value,
    "forecast_absent_count": forecast_absent_count,
}


def generate(spec: dict, observations: list[Observation] | None, selection: Selection | None):
    generator = GENERATORS[spec["generator"]]
    if spec["kind"] == "data" and (observations is None or selection is None):
        return Unavailable(spec["exercise_id"], "no observations collected yet")
    return generator(spec["exercise_id"], observations, selection)
