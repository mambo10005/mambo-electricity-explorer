"""Deterministic calculation services shared by lessons, exercises, and tests.

Every function takes explicit observation records (no I/O) and returns a CalcResult that
preserves its inputs, unit, formula version, valid-pair count, exclusions, and the
(metric, period, revision, run) of every observation used. Insufficient or ambiguous
input gives status "unavailable" with a reason. Nothing is filled, imputed, or
computed over empty input.

Periods are the source's UTC labels ("YYYY-MM-DDTHH"). They are compared and
enumerated as labels only; no interval boundaries are derived (see
eia/dataset.INTERVAL_CONVENTION).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from mambo_explorer.eia import dataset as ds

LABEL_FORMAT = "%Y-%m-%dT%H"


@dataclass(frozen=True)
class Observation:
    entity: str
    metric: str
    period: str
    value: float | None
    value_raw: str | None
    unit: str
    quality_flags: str = ""
    revision: int = 1
    run_id: str = ""


@dataclass(frozen=True)
class Selection:
    entity: str
    start_period: str  # inclusive UTC source label
    end_period: str  # inclusive UTC source label

    def __post_init__(self) -> None:
        if _parse_label(self.start_period) > _parse_label(self.end_period):
            raise ValueError("start_period must not be after end_period")


@dataclass
class CalcResult:
    calculation_id: str
    formula_version: str
    status: str  # "ok" | "unavailable"
    selection: dict
    unit: str | None = None
    values: dict = field(default_factory=dict)
    valid_count: int = 0
    exclusions: list[dict] = field(default_factory=list)
    references: list[dict] = field(default_factory=list)
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict:
        return asdict(self)


# --- label helpers ---------------------------------------------------------------------


def _parse_label(label: str) -> datetime:
    return datetime.strptime(label, LABEL_FORMAT)


def labels_between(start: str, end: str) -> list[str]:
    """Every hourly source label from start to end inclusive (label arithmetic only)."""
    first, last = _parse_label(start), _parse_label(end)
    count = int((last - first) / timedelta(hours=1)) + 1
    return [(first + timedelta(hours=h)).strftime(LABEL_FORMAT) for h in range(max(count, 0))]


def label_runs(labels: list[str]) -> list[tuple[str, str, int]]:
    """Group sorted labels into contiguous hourly runs: (first, last, count)."""
    runs: list[tuple[str, str, int]] = []
    for label in sorted(labels):
        if runs and _parse_label(label) - _parse_label(runs[-1][1]) == timedelta(hours=1):
            first, _, count = runs[-1]
            runs[-1] = (first, label, count + 1)
        else:
            runs.append((label, label, 1))
    return runs


def _ref(o: Observation) -> dict:
    return {"metric": o.metric, "period": o.period, "revision": o.revision, "run_id": o.run_id}


def _valid(o: Observation) -> bool:
    return o.value is not None and math.isfinite(o.value)


def _invalid_reason(o: Observation) -> str:
    if o.value_raw is None or o.value_raw.strip() == "":
        return "null value"
    return "non-numeric value"


def _scoped(observations: list[Observation], selection: Selection, metric: str):
    """Rows for one metric inside the selection. Returns (rows, duplicate_periods)."""
    rows = [
        o
        for o in observations
        if o.entity == selection.entity
        and o.metric == metric
        and selection.start_period <= o.period <= selection.end_period
    ]
    seen: dict[str, int] = {}
    for o in rows:
        seen[o.period] = seen.get(o.period, 0) + 1
    return sorted(rows, key=lambda o: o.period), sorted(p for p, n in seen.items() if n > 1)


def _unavailable(calc_id: str, version: str, selection: Selection, reason: str, **kw) -> CalcResult:
    return CalcResult(calc_id, version, "unavailable", asdict(selection), reason=reason, **kw)


# --- calculations ------------------------------------------------------------------------


def power_energy(
    *, average_mw: float | None = None, energy_mwh: float | None = None, hours: float
) -> CalcResult:
    """energy (MWh) = average power (MW) × duration (h). Exactly one of the two is given."""
    calc, version = "power_energy", "1"
    selection = {"average_mw": average_mw, "energy_mwh": energy_mwh, "hours": hours}
    if (average_mw is None) == (energy_mwh is None):
        return CalcResult(
            calc,
            version,
            "unavailable",
            selection,
            reason="give exactly one of average_mw or energy_mwh",
        )
    if not (isinstance(hours, (int, float)) and math.isfinite(hours) and hours > 0):
        return CalcResult(
            calc,
            version,
            "unavailable",
            selection,
            reason="duration must be a positive number of hours",
        )
    if average_mw is not None:
        return CalcResult(
            calc,
            version,
            "ok",
            selection,
            unit="MWh",
            values={"energy_mwh": average_mw * hours},
            valid_count=1,
        )
    return CalcResult(
        calc,
        version,
        "ok",
        selection,
        unit="MW",
        values={"average_mw": energy_mwh / hours},
        valid_count=1,
    )


def series_summary(
    observations: list[Observation], selection: Selection, metric: str = "D"
) -> CalcResult:
    """Min, max, mean, and range of valid values for one metric, in the source unit."""
    calc, version = "series_summary", "1"
    rows, dupes = _scoped(observations, selection, metric)
    if dupes:
        return _unavailable(
            calc, version, selection, f"duplicate observations for periods {dupes[:3]}"
        )
    exclusions = [
        {"metric": o.metric, "period": o.period, "reason": _invalid_reason(o)}
        for o in rows
        if not _valid(o)
    ]
    valid = [o for o in rows if _valid(o)]
    units = {o.unit for o in valid}
    expected = labels_between(selection.start_period, selection.end_period)
    present = {o.period for o in rows}
    absent = [p for p in expected if p not in present]
    exclusions += [{"metric": metric, "period": p, "reason": "absent row"} for p in absent]
    if not valid:
        return _unavailable(
            calc,
            version,
            selection,
            "no valid observations in the selection",
            exclusions=exclusions,
        )
    if len(units) != 1:
        return _unavailable(
            calc, version, selection, f"mixed units {sorted(units)}", exclusions=exclusions
        )
    hi = max(valid, key=lambda o: (o.value, o.period))
    lo = min(valid, key=lambda o: (o.value, o.period))
    mean = sum(o.value for o in valid) / len(valid)
    return CalcResult(
        calc,
        version,
        "ok",
        asdict(selection) | {"metric": metric},
        unit=units.pop(),
        values={
            "max": hi.value,
            "max_period": hi.period,
            "min": lo.value,
            "min_period": lo.period,
            "mean": mean,
            "range": hi.value - lo.value,
            "expected_labels": len(expected),
            "present_rows": len(rows),
            "valid_values": len(valid),
            "absent_rows": len(absent),
        },
        valid_count=len(valid),
        exclusions=exclusions,
        references=[_ref(o) for o in valid],
    )


def coverage(observations: list[Observation], selection: Selection, metric: str) -> CalcResult:
    """Classify every expected label for one metric. Zero is a value, not missing."""
    calc, version = "coverage", "1"
    rows, dupes = _scoped(observations, selection, metric)
    if dupes:
        return _unavailable(
            calc, version, selection, f"duplicate observations for periods {dupes[:3]}"
        )
    expected = labels_between(selection.start_period, selection.end_period)
    by_period = {o.period: o for o in rows}
    absent = [p for p in expected if p not in by_period]
    nulls = [o.period for o in rows if not _valid(o) and _invalid_reason(o) == "null value"]
    non_numeric = [o.period for o in rows if not _valid(o) and _invalid_reason(o) != "null value"]
    zeros = [o.period for o in rows if _valid(o) and o.value == 0]
    valid = [o for o in rows if _valid(o)]
    return CalcResult(
        calc,
        version,
        "ok",
        asdict(selection) | {"metric": metric},
        unit=next(iter({o.unit for o in rows}), None),
        values={
            "expected_labels": len(expected),
            "present_rows": len(rows),
            "valid_values": len(valid),
            "zero_values": len(zeros),
            "null_values": len(nulls),
            "non_numeric_values": len(non_numeric),
            "absent_rows": len(absent),
            "absent_runs": label_runs(absent),
            "null_periods": nulls,
            "zero_periods": zeros,
        },
        valid_count=len(valid),
        exclusions=[{"metric": metric, "period": p, "reason": "absent row"} for p in absent]
        + [{"metric": metric, "period": p, "reason": "null value"} for p in nulls]
        + [{"metric": metric, "period": p, "reason": "non-numeric value"} for p in non_numeric],
        references=[_ref(o) for o in rows],
    )


def forecast_error(observations: list[Observation], selection: Selection) -> CalcResult:
    """error = actual (D) − forecast (DF), over matched valid pairs by entity and period label.

    mean_error = Σe/n; MAE = Σ|e|/n; RMSE = √(Σe²/n).
    """
    calc, version = "forecast_error", "1"
    actual, dupes_a = _scoped(observations, selection, "D")
    forecast, dupes_f = _scoped(observations, selection, "DF")
    if dupes_a or dupes_f:
        return _unavailable(
            calc,
            version,
            selection,
            f"duplicate observations for periods {(dupes_a + dupes_f)[:3]}",
        )
    a_by, f_by = {o.period: o for o in actual}, {o.period: o for o in forecast}
    pairs, exclusions = [], []
    for period in labels_between(selection.start_period, selection.end_period):
        a, f = a_by.get(period), f_by.get(period)
        reasons = []
        if a is None:
            reasons.append("actual absent")
        elif not _valid(a):
            reasons.append(f"actual {_invalid_reason(a)}")
        if f is None:
            reasons.append("forecast absent")
        elif not _valid(f):
            reasons.append(f"forecast {_invalid_reason(f)}")
        if not reasons and a.unit != f.unit:
            reasons.append(f"unit mismatch ({a.unit} vs {f.unit})")
        if reasons:
            exclusions.append({"period": period, "reason": "; ".join(reasons)})
        else:
            pairs.append((period, a, f))
    if not pairs:
        return _unavailable(
            calc,
            version,
            selection,
            "no matched valid actual/forecast pairs",
            exclusions=exclusions,
        )
    errors = [a.value - f.value for _, a, f in pairs]
    n = len(errors)
    largest = max(pairs, key=lambda p: (abs(p[1].value - p[2].value), p[0]))
    return CalcResult(
        calc,
        version,
        "ok",
        asdict(selection),
        unit=pairs[0][1].unit,
        values={
            "pairs": n,
            "mean_error": sum(errors) / n,
            "mae": sum(abs(e) for e in errors) / n,
            "rmse": math.sqrt(sum(e * e for e in errors) / n),
            "over_forecast_hours": sum(e < 0 for e in errors),
            "under_forecast_hours": sum(e > 0 for e in errors),
            "exact_hours": sum(e == 0 for e in errors),
            "largest_abs_error": largest[1].value - largest[2].value,
            "largest_abs_error_period": largest[0],
            "pair_errors": [
                {"period": p, "actual": a.value, "forecast": f.value, "error": a.value - f.value}
                for p, a, f in pairs
            ],
        },
        valid_count=n,
        exclusions=exclusions,
        references=[_ref(o) for _, a, f in pairs for o in (a, f)],
    )


def snapshot_id(observations: list[Observation], selection: Selection) -> str:
    """Stable fingerprint of a selection and the exact revisions/values inside it."""
    scoped = sorted(
        (o.metric, o.period, o.revision, o.value_raw, o.unit)
        for o in observations
        if o.entity == selection.entity
        and selection.start_period <= o.period <= selection.end_period
    )
    payload = json.dumps([asdict(selection), scoped], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_observations(
    store, selection: Selection, metrics: tuple[str, ...] = ds.METRICS
) -> list[Observation]:
    """Latest revision of each observation in the selection, from committed files only."""
    with store.query() as con:
        rows = con.execute(
            "SELECT entity, metric, period, value, value_raw, unit, quality_flags, "
            "revision, run_id "
            "FROM latest WHERE entity = ? AND list_contains(?, metric) "
            "AND period BETWEEN ? AND ? ORDER BY metric, period",
            [selection.entity, list(metrics), selection.start_period, selection.end_period],
        ).fetchall()
    return [Observation(*r) for r in rows]


# --- generation by energy source (Stage 16; ADR 0014) --------------------------------------
# Generation observations reuse Observation with `metric` = the energy-source code, so the
# per-series functions above (series_summary, coverage, snapshot_id) apply per category.


def load_generation(store, selection: Selection) -> list[Observation]:
    """Latest revision of each (category, period) in the selection, from committed files."""
    with store.query() as con:
        rows = con.execute(
            "SELECT entity, energy_source, period, value, value_raw, unit, quality_flags, "
            "revision, run_id FROM latest WHERE entity = ? AND period BETWEEN ? AND ? "
            "ORDER BY energy_source, period",
            [selection.entity, selection.start_period, selection.end_period],
        ).fetchall()
    return [Observation(*r) for r in rows]


def generation_mix(observations: list[Observation], selection: Selection) -> CalcResult:
    """Signed category sums, per-category coverage, and per-hour sums with completeness.

    Rules (documented in docs/calculations.md):
    - A category's energy is the sum of its VALID values; absent or null hours add nothing
      and are counted, never filled.
    - An hour is "complete" when every category seen anywhere in the window has a valid
      value in that hour. An hour sum is the sum of the categories reported in that hour;
      it is never called total system generation (the source's SYS total is not collected).
    - Shares are offered only over complete hours and only when no category is negative in
      any complete hour (denominator: the sum of all categories over the complete hours).
      Otherwise they are withheld with a reason.
    """
    calc, version = "generation_mix", "1.0.0"
    scoped = [
        o
        for o in observations
        if o.entity == selection.entity
        and selection.start_period <= o.period <= selection.end_period
    ]
    if not scoped:
        return _unavailable(calc, version, selection, "no generation observations in the window")
    categories = sorted({o.metric for o in scoped})
    units = {o.unit for o in scoped}
    if len(units) != 1:
        return _unavailable(calc, version, selection, f"mixed units {sorted(units)}")
    expected = labels_between(selection.start_period, selection.end_period)
    by_key = {}
    for o in scoped:
        if (o.metric, o.period) in by_key:
            return _unavailable(
                calc, version, selection, f"duplicate observation {(o.metric, o.period)}"
            )
        by_key[(o.metric, o.period)] = o

    per_category = {}
    for code in categories:
        rows = [by_key[(code, p)] for p in expected if (code, p) in by_key]
        valid = [o for o in rows if _valid(o)]
        per_category[code] = {
            "energy_sum": sum(o.value for o in valid) if valid else None,
            "min": min((o.value for o in valid), default=None),
            "max": max((o.value for o in valid), default=None),
            "valid_values": len(valid),
            "negative_hours": sum(o.value < 0 for o in valid),
            "zero_hours": sum(o.value == 0 for o in valid),
            "null_values": sum(1 for o in rows if not _valid(o)),
            "absent_rows": len(expected) - len(rows),
            "unreviewed": any("unreviewed_category" in o.quality_flags for o in rows),
        }

    hours = []
    for p in expected:
        present = [
            by_key[(c, p)] for c in categories if (c, p) in by_key and _valid(by_key[(c, p)])
        ]
        hours.append(
            {
                "period": p,
                "categories_present": len(present),
                "complete": len(present) == len(categories),
                "category_sum": sum(o.value for o in present) if present else None,
                "has_negative": any(o.value < 0 for o in present),
            }
        )
    complete = [h for h in hours if h["complete"]]
    negative_in_complete = any(h["has_negative"] for h in complete)
    window_sum = sum(h["category_sum"] for h in complete) if complete else None
    if not complete:
        shares, share_reason = None, "no hour has a valid value for every category"
    elif negative_in_complete:
        shares, share_reason = (
            None,
            (
                "withheld: at least one category is negative (net storage) in a complete hour, "
                "so a share of a signed sum would be misleading"
            ),
        )
    elif not window_sum:
        shares, share_reason = None, "withheld: the sum over complete hours is zero"
    else:
        totals = {c: sum(by_key[(c, h["period"])].value for h in complete) for c in categories}
        shares = {c: totals[c] / window_sum for c in categories}
        share_reason = (
            f"share of the sum of all reported categories over the {len(complete)} complete "
            "hour(s); not a share of total system generation"
        )
    sums = {c: v["energy_sum"] for c, v in per_category.items() if v["energy_sum"] is not None}
    largest = max(sums, key=lambda c: (sums[c], c)) if sums else None
    return CalcResult(
        calc,
        version,
        "ok",
        asdict(selection),
        unit=next(iter(units)),
        values={
            "categories": categories,
            "per_category": per_category,
            "hours": hours,
            "expected_labels": len(expected),
            "complete_hours": len(complete),
            "incomplete_hours": len(hours) - len(complete),
            "absent_category_hours": sum(v["absent_rows"] for v in per_category.values()),
            "null_category_hours": sum(v["null_values"] for v in per_category.values()),
            "categories_with_negative_hours": [
                c for c in categories if per_category[c]["negative_hours"]
            ],
            "window_sum_complete_hours": window_sum,
            "largest_category_by_energy": largest,
            "shares": shares,
            "share_note": share_reason,
        },
        valid_count=sum(v["valid_values"] for v in per_category.values()),
        exclusions=[
            {"metric": c, "period": p, "reason": "absent row"}
            for c in categories
            for p in expected
            if (c, p) not in by_key
        ]
        + [
            {"metric": o.metric, "period": o.period, "reason": _invalid_reason(o)}
            for o in scoped
            if not _valid(o)
        ],
        references=[_ref(o) for o in scoped],
    )
