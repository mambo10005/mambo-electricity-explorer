"""Introductory energy settlement: a TEACHING calculation, not a market settlement engine.

Teaching formula (one location, one settlement interval, energy only):

    day-ahead component  = scheduled_energy_mwh × day_ahead_price
    deviation component  = (actual_energy_mwh − scheduled_energy_mwh) × real_time_price
    energy settlement    = day-ahead component + deviation component

Quantities are energy in MWh (never MW); prices are synthetic currency per MWh; every
amount is synthetic currency. The result is one **signed energy-settlement amount** for an
energy position. Its meaning depends on the role, and this module states it explicitly
instead of flipping signs:

- buyer (e.g. a load):  the amount is what the buyer pays. A negative amount is a credit
  to the buyer under these teaching assumptions.
- seller (e.g. a generator): the same amount is what the seller receives. A negative amount
  is a payment by the seller.

What the cited source supports (ISO New England only; see docs/source-register.md): a
day-ahead settlement of cleared quantities at the day-ahead LMP, and a separate real-time
settlement of deviations from day-ahead commitments at the real-time LMP, per location;
real-time in five-minute intervals; invoices that also include other items. ISO-NE's own
invoice sign convention (a positive net amount is a credit) is NOT used here.

Everything else is a teaching assumption: a single location and a single interval with one
price per stage, no loss or uplift allocations, no ancillary services, capacity,
transmission, or fees, and no bilateral or virtual transactions. A day-ahead schedule
here is an input, not a forecast, and nothing here says how energy physically flows.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field

FORMULA_VERSION = "1.0.0"
CURRENCY = "synthetic $"
SOURCES = ("iso-ne-da-rt-markets", "iso-ne-da-energy-bill", "iso-ne-rt-energy-bill")
ASSUMPTIONS = (
    "One location and one settlement interval; one day-ahead price and one real-time price.",
    "Energy only: no loss, uplift, ancillary-service, capacity, transmission, or "
    "administrative charges, and no bilateral or virtual transactions.",
    "The day-ahead schedule is a given input, not a forecast and not a physical delivery path.",
    "Sign convention: one signed amount; a buyer pays it, a seller receives it.",
    "All numbers are synthetic (or explicitly modeled); none is an actual ISO settlement.",
)

# Bounded inputs: (minimum, maximum). Prices may be negative.
ENERGY_BOUNDS_MWH = (0.0, 100_000.0)
PRICE_BOUNDS = (-1_000.0, 10_000.0)
POWER_BOUNDS_MW = (0.0, 100_000.0)
DURATION_BOUNDS_H = (0.0, 24.0)  # exclusive of 0


class SettlementError(ValueError):
    pass


def _number(name: str, value, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettlementError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise SettlementError(f"{name} must be finite (got {value})")
    if not low <= value <= high:
        raise SettlementError(f"{name} = {value:g} is outside {low:g} to {high:g}")
    return value


def energy_from_power(average_mw, hours) -> float:
    """MWh from an average MW over an explicit duration. A duration is always required."""
    mw = _number("average power (MW)", average_mw, *POWER_BOUNDS_MW)
    if hours is None:
        raise SettlementError("a duration in hours is required to turn MW into MWh")
    h = _number("duration (h)", hours, *DURATION_BOUNDS_H)
    if h <= 0:
        raise SettlementError("duration must be greater than 0 hours")
    return mw * h


@dataclass(frozen=True)
class PriceSource:
    """Where a price came from: 'synthetic' (typed in) or 'modeled' (a verified run)."""

    kind: str = "synthetic"  # "synthetic" | "modeled"
    run_id: str | None = None
    scenario: str | None = None
    bus: str | None = None
    package: str | None = None  # package name, version, and commit
    checks_version: str | None = None
    verification: str | None = None  # "verified" for modeled prices


@dataclass(frozen=True)
class Inputs:
    scheduled_energy_mwh: float
    actual_energy_mwh: float
    day_ahead_price: float
    real_time_price: float
    day_ahead_source: PriceSource = field(default_factory=PriceSource)
    real_time_source: PriceSource = field(default_factory=PriceSource)

    def validate(self) -> Inputs:
        _number("scheduled energy (MWh)", self.scheduled_energy_mwh, *ENERGY_BOUNDS_MWH)
        _number("actual energy (MWh)", self.actual_energy_mwh, *ENERGY_BOUNDS_MWH)
        _number("day-ahead price", self.day_ahead_price, *PRICE_BOUNDS)
        _number("real-time price", self.real_time_price, *PRICE_BOUNDS)
        for name, src in (
            ("day-ahead", self.day_ahead_source),
            ("real-time", self.real_time_source),
        ):
            if src.kind not in ("synthetic", "modeled"):
                raise SettlementError(f"{name} price source must be synthetic or modeled")
            if src.kind == "modeled" and (src.verification != "verified" or not src.run_id):
                raise SettlementError(f"{name} modeled price lacks a verified run")
        if (
            self.day_ahead_source.kind == "modeled"
            and self.real_time_source.kind == "modeled"
            and self.day_ahead_source.run_id == self.real_time_source.run_id
        ):
            raise SettlementError(
                "one model run cannot supply both the day-ahead and the real-time price"
            )
        return self


@dataclass(frozen=True)
class Result:
    inputs: dict
    day_ahead_component: float
    deviation_mwh: float
    deviation_component: float
    total: float
    formula_version: str
    assumptions: tuple[str, ...]
    sources: tuple[str, ...]
    snapshot_id: str

    def buyer_reading(self) -> str:
        if self.total > 0:
            return "The buyer pays this amount."
        if self.total < 0:
            return "Negative: under these teaching assumptions it is a credit to the buyer."
        return "Zero: the buyer neither pays nor is credited."

    def seller_reading(self) -> str:
        if self.total > 0:
            return "The seller receives this amount."
        if self.total < 0:
            return "Negative: under these teaching assumptions the seller pays this amount."
        return "Zero: the seller neither receives nor pays."


def snapshot_id(inputs: Inputs) -> str:
    payload = {"formula_version": FORMULA_VERSION, **asdict(inputs)}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"settle-{digest}"


def settle(inputs: Inputs) -> Result:
    """The teaching energy settlement. Raises SettlementError on any invalid input."""
    inputs.validate()
    da = inputs.scheduled_energy_mwh * inputs.day_ahead_price
    deviation = inputs.actual_energy_mwh - inputs.scheduled_energy_mwh
    rt = deviation * inputs.real_time_price
    total = da + rt
    for name, value in (("day-ahead component", da), ("deviation component", rt), ("total", total)):
        if not math.isfinite(value):  # cannot happen within the bounds; kept as a guard
            raise SettlementError(f"{name} is not finite")
    return Result(
        inputs=asdict(inputs),
        day_ahead_component=da + 0.0,
        deviation_mwh=deviation + 0.0,
        deviation_component=rt + 0.0,
        total=total + 0.0,
        formula_version=FORMULA_VERSION,
        assumptions=ASSUMPTIONS,
        sources=SOURCES,
        snapshot_id=snapshot_id(inputs),
    )


def modeled_price(record, bus: str) -> tuple[float, PriceSource]:
    """A verified teaching-model nodal price as a MODELED scenario input.

    Refuses anything but an optimal OPF run whose price check passed, produced by the
    current checks and the pinned package. Withheld, unavailable, failed, infeasible, or
    stale runs are never imported.
    """
    from mambo_explorer.modeling import adapter

    if getattr(record, "kind", None) != "opf.dc":
        raise SettlementError("only economic-dispatch (opf.dc) runs carry modeled prices")
    if record.status != "optimal":
        raise SettlementError(f"run {record.run_id} is {record.status}; no price to import")
    if record.price_status != "verified" or not record.prices:
        raise SettlementError(
            f"run {record.run_id}: prices were {record.price_status}; only verified prices "
            "can be imported"
        )
    if getattr(record, "checks_version", None) != adapter.CHECKS_VERSION:
        raise SettlementError(f"run {record.run_id} was produced by older checks; run it again")
    if not record.package.get("matches_pin"):
        raise SettlementError(f"run {record.run_id} was not produced by the pinned package")
    price = next((p["price_per_mwh"] for p in record.prices if p["bus"] == bus), None)
    if price is None:
        raise SettlementError(f"run {record.run_id} has no price at bus {bus}")
    price = round(price, 6) + 0.0
    pkg = record.package
    return price, PriceSource(
        kind="modeled",
        run_id=record.run_id,
        scenario=f"{record.scenario_id} v{record.scenario_version}",
        bus=bus,
        package=f"{pkg.get('name')} {pkg.get('version')} @ {str(pkg.get('installed_commit'))[:12]}",
        checks_version=record.checks_version,
        verification="verified",
    )
