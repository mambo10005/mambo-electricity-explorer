"""Time-shape exposure under a flat-block financial hedge (TEACHING only; one location).

Synthetic intervals t, each with an elapsed duration d_t (hours), physical energy q_t (MWh),
and a spot price p_t (synthetic $/MWh). A flat-block financial hedge has a constant power
B (MW) and a fixed price K: the buyer pays K and receives p_t on h_t = B × d_t MWh.

    physical cost_t = q_t × p_t
    hedge receipt_t = h_t × (p_t − K)          (negative = a payment by the buyer)
    net cost_t      = physical cost_t − hedge receipt_t   (negative = a credit)

Totals, with r_t = q_t − h_t, D = Σ d_t, Q = Σ q_t, R = Σ r_t, p̄ = Σ d_t p_t / D:

    total net = Σ h_t × K + Σ r_t × p_t                              (decomposition 1)
              = B·D·K  +  R × p̄  +  Σ r_t (p_t − p̄)                   (decomposition 2)
                fixed     aggregate   time-shape component
                hedge     energy
                          mismatch

Decomposition 2 is an algebraic identity for this teaching contract and this choice of p̄
(the duration-weighted average price). The "time-shape component" is an accounting split,
not a universal industry risk metric. When Q = B·D the aggregate mismatch is zero, yet the
time-shape component can be non-zero: equal total energy is not equal interval exposure.

Intervals are identifiers with elapsed durations, not calendar times: no time zones, DST,
or market calendars. The hedge is a synthetic financial contract, not an exchange product,
and it delivers no electricity.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

from mambo_explorer import settlement as sm

FORMULA_VERSION = "1.0.0"
SCENARIO_VERSION = "1.0.0"
CURRENCY = "synthetic $"
MAX_INTERVALS = 24
DURATION_BOUNDS_H = (0.0, 24.0)  # exclusive of 0
ENERGY_BOUNDS_MWH = (0.0, 100_000.0)
POWER_BOUNDS_MW = (0.0, 100_000.0)
PRICE_BOUNDS = sm.PRICE_BOUNDS
SOURCES = ("eia-texas-heat-wave-2011",)
ASSUMPTIONS = (
    "One location; intervals are identifiers with elapsed durations, not calendar times "
    "(no time zones, DST, or market calendars).",
    "Flat-block hedge: constant power B (MW) in every interval, so hedge energy is B × d_t.",
    "The buyer pays a fixed price K and receives the interval spot price on the hedge energy.",
    "No forecasting, optimization, margin, credit, fees, or settlement timing.",
    "The hedge is a synthetic financial contract: no physical delivery, not an exchange product.",
    "All numbers are synthetic; the time-shape component is an accounting split, not a "
    "standard risk metric.",
)


@dataclass(frozen=True)
class Interval:
    interval_id: str
    duration_h: float
    energy_mwh: float
    price: float


@dataclass(frozen=True)
class Inputs:
    intervals: tuple[Interval, ...]
    hedge_mw: float
    fixed_price: float
    scenario: str = "custom"  # a predefined scenario key, or "edited:<key>", or "custom"
    scenario_version: str = SCENARIO_VERSION

    def validate(self) -> Inputs:
        if not isinstance(self.intervals, tuple) or not 1 <= len(self.intervals) <= MAX_INTERVALS:
            raise sm.SettlementError(f"use 1 to {MAX_INTERVALS} intervals")
        ids = set()
        for i, iv in enumerate(self.intervals, start=1):
            name = str(iv.interval_id).strip()
            if not name or len(name) > 20:
                raise sm.SettlementError(f"interval {i}: identifier must be 1 to 20 characters")
            if name in ids:
                raise sm.SettlementError(f"interval identifier {name!r} is repeated")
            ids.add(name)
            d = sm._number(f"interval {name}: duration (h)", iv.duration_h, *DURATION_BOUNDS_H)
            if d <= 0:
                raise sm.SettlementError(f"interval {name}: duration must be greater than 0 hours")
            sm._number(f"interval {name}: physical energy (MWh)", iv.energy_mwh, *ENERGY_BOUNDS_MWH)
            sm._number(f"interval {name}: spot price", iv.price, *PRICE_BOUNDS)
        sm._number("hedge power B (MW)", self.hedge_mw, *POWER_BOUNDS_MW)
        sm._number("fixed price K", self.fixed_price, *PRICE_BOUNDS)
        return self


def energy_from_power(average_mw, duration_h) -> float:
    """Physical MWh from an average MW over the interval's explicit duration."""
    mw = sm._number("average physical power (MW)", average_mw, *POWER_BOUNDS_MW)
    d = sm._number("duration (h)", duration_h, *DURATION_BOUNDS_H)
    if d <= 0:
        raise sm.SettlementError("duration must be greater than 0 hours")
    return mw * d


@dataclass(frozen=True)
class Row:
    interval_id: str
    duration_h: float
    energy_mwh: float
    hedge_mwh: float
    price: float
    physical_cost: float
    hedge_receipt: float
    net_cost: float
    residual_mwh: float
    status: str  # "underhedged" | "overhedged" | "matched"


@dataclass(frozen=True)
class Result:
    inputs: dict
    rows: tuple[Row, ...]
    total_duration_h: float
    total_energy_mwh: float
    total_hedge_mwh: float
    average_price: float  # duration-weighted p̄
    residual_mwh: float  # R
    physical_cost: float
    hedge_receipt: float
    net_cost: float
    fixed_hedge_total: float  # Σ h K  (= B·D·K)
    residual_cost: float  # Σ r p
    aggregate_mismatch: float  # R × p̄
    time_shape: float  # Σ r (p − p̄)
    formula_version: str
    scenario_version: str
    assumptions: tuple[str, ...]
    sources: tuple[str, ...]
    snapshot_id: str


def _status(r: float) -> str:
    if r > 1e-9:
        return "underhedged"
    if r < -1e-9:
        return "overhedged"
    return "matched"


def snapshot_id(inputs: Inputs) -> str:
    payload = {"formula_version": FORMULA_VERSION, **asdict(inputs)}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"shape-{digest}"


def _close(a: float, b: float, scale: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9 * max(1.0, scale))


def evaluate(inputs: Inputs) -> Result:
    inputs.validate()
    b, k = inputs.hedge_mw, inputs.fixed_price
    rows = []
    for iv in inputs.intervals:
        h = b * iv.duration_h
        physical = iv.energy_mwh * iv.price
        receipt = h * (iv.price - k)
        r = iv.energy_mwh - h
        rows.append(
            Row(
                interval_id=str(iv.interval_id).strip(),
                duration_h=iv.duration_h,
                energy_mwh=iv.energy_mwh,
                hedge_mwh=h + 0.0,
                price=iv.price,
                physical_cost=physical + 0.0,
                hedge_receipt=receipt + 0.0,
                net_cost=physical - receipt + 0.0,
                residual_mwh=r + 0.0,
                status=_status(r),
            )
        )
    d_total = sum(x.duration_h for x in rows)
    q_total = sum(x.energy_mwh for x in rows)
    h_total = sum(x.hedge_mwh for x in rows)
    p_bar = sum(x.duration_h * x.price for x in rows) / d_total
    r_total = sum(x.residual_mwh for x in rows)
    physical = sum(x.physical_cost for x in rows)
    receipt = sum(x.hedge_receipt for x in rows)
    net = sum(x.net_cost for x in rows)
    fixed_1 = h_total * k
    residual_cost = sum(x.residual_mwh * x.price for x in rows)
    fixed_2 = b * d_total * k
    aggregate = r_total * p_bar
    shape = sum(x.residual_mwh * (x.price - p_bar) for x in rows)
    # Both decompositions are computed independently and must reproduce the net cost.
    scale = sum(abs(x.physical_cost) + abs(x.hedge_receipt) for x in rows) + abs(fixed_2)
    checks = (
        _close(net, physical - receipt, scale),
        _close(net, fixed_1 + residual_cost, scale),
        _close(net, fixed_2 + aggregate + shape, scale),
        _close(fixed_1, fixed_2, scale),
    )
    if not all(checks):
        raise sm.SettlementError("a decomposition does not reproduce the net cost")
    return Result(
        inputs=asdict(inputs),
        rows=tuple(rows),
        total_duration_h=d_total,
        total_energy_mwh=q_total,
        total_hedge_mwh=h_total,
        average_price=p_bar + 0.0,
        residual_mwh=r_total + 0.0,
        physical_cost=physical + 0.0,
        hedge_receipt=receipt + 0.0,
        net_cost=net + 0.0,
        fixed_hedge_total=fixed_2 + 0.0,
        residual_cost=residual_cost + 0.0,
        aggregate_mismatch=aggregate + 0.0,
        time_shape=shape + 0.0,
        formula_version=FORMULA_VERSION,
        scenario_version=inputs.scenario_version,
        assumptions=ASSUMPTIONS,
        sources=SOURCES,
        snapshot_id=snapshot_id(inputs),
    )


def _iv(rows):
    return tuple(
        Interval(f"t{i}", float(d), float(q), float(p)) for i, (d, q, p) in enumerate(rows, start=1)
    )


# Predefined SYNTHETIC scenarios: (title, intervals as (duration h, energy MWh, price), B, K).
SCENARIOS: dict[str, tuple[str, tuple[Interval, ...], float, float]] = {
    "peaky": ("Load peaks in the high-price hour", _iv([(1, 50, 20), (1, 150, 80)]), 100.0, 40.0),
    "reversed": (
        "Same total energy, load peaks in the low-price hour",
        _iv([(1, 150, 20), (1, 50, 80)]),
        100.0,
        40.0,
    ),
    "flat-match": (
        "Flat load exactly matching the hedge",
        _iv([(1, 100, 20), (1, 100, 80)]),
        100.0,
        40.0,
    ),
    "constant-prices": ("Constant prices", _iv([(1, 50, 50), (1, 150, 50)]), 100.0, 40.0),
    "no-hedge": ("No hedge", _iv([(1, 50, 20), (1, 150, 80)]), 0.0, 40.0),
    "underhedge": ("Underhedged (B = 50 MW)", _iv([(1, 50, 20), (1, 150, 80)]), 50.0, 40.0),
    "overhedge": ("Overhedged (B = 150 MW)", _iv([(1, 50, 20), (1, 150, 80)]), 150.0, 40.0),
    "negative-prices": ("A negative price", _iv([(1, 50, -10), (1, 150, 30)]), 100.0, 40.0),
    "hedge-only": ("No physical energy, hedge only", _iv([(1, 0, 20), (1, 0, 80)]), 100.0, 40.0),
    "unequal-durations": (
        "Unequal interval durations (1 h and 3 h)",
        _iv([(1, 50, 20), (3, 300, 60)]),
        100.0,
        40.0,
    ),
}


def scenario_inputs(key: str) -> Inputs:
    _, intervals, b, k = SCENARIOS[key]
    return Inputs(intervals=intervals, hedge_mw=b, fixed_price=k, scenario=key)


def reversed_profile(inputs: Inputs) -> Inputs:
    """Same durations, prices, and total energy; the physical energies in reverse order."""
    energies = [iv.energy_mwh for iv in inputs.intervals][::-1]
    intervals = tuple(
        Interval(iv.interval_id, iv.duration_h, q, iv.price)
        for iv, q in zip(inputs.intervals, energies, strict=True)
    )
    return Inputs(intervals, inputs.hedge_mw, inputs.fixed_price, f"reversed:{inputs.scenario}")
