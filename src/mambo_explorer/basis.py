"""Locational basis exposure with a simplified fixed-price financial hedge (TEACHING only).

Separate from the two-stage energy settlement in settlement.py. Synthetic scenario:

- a buyer purchases Q MWh of actual energy at delivery location L, at price P_L;
- separately, the buyer holds a financial hedge on H MWh that references location H_ref:
  the buyer pays a fixed price K and receives the floating reference price P_H.

    basis                = P_L − P_H
    physical cost        = Q × P_L
    hedge receipt        = H × (P_H − K)        (negative = a payment by the buyer)
    net buyer cost       = Q × P_L − H × (P_H − K)   (negative = a credit to the buyer)

Algebraically, net buyer cost = Q·K + Q·(P_L − P_H) + (Q − H)·(P_H − K):
fixed-price component + location-basis component + quantity-mismatch component.
With H = Q: Q·(K + basis). With H = Q and P_L = P_H: Q·K. These identities follow from
THIS teaching contract only, not from every real hedge.

Source-supported concepts (FERC market-assessment glossary; general/natural-gas context):
basis as the price difference between otherwise identical products in different markets;
a fixed-for-floating swap (pay fixed, receive a changing price); hedging as protecting
value with instruments whose price changes are expected to offset a loss. The sign of
"basis" here (delivery minus reference) is this app's convention. Nothing here is an
exchange contract, a legal classification, or a valuation, and a financial hedge never
delivers electricity.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field

from mambo_explorer import settlement as sm

FORMULA_VERSION = "1.0.0"
CURRENCY = "synthetic $"
QUANTITY_BOUNDS_MWH = (0.0, 100_000.0)  # nonnegative in this milestone
PRICE_BOUNDS = sm.PRICE_BOUNDS  # −1,000 to 10,000 per MWh; K uses the same bounds
SOURCES = ("ferc-glossary",)
ASSUMPTIONS = (
    "Synthetic scenario: one interval, one delivery location L and one hedge reference "
    "location H, one price at each.",
    "The hedge is a simplified cash-flow agreement: the buyer pays a fixed price K and "
    "receives the floating reference price on H MWh. No margin, credit, fees, or timing.",
    "K is an explicit synthetic assumption, never inferred from a model run.",
    "The hedge is financial: it delivers no electricity. The physical purchase is paid at "
    "the delivery-location price.",
    "Basis = delivery price − reference price (this app's sign convention).",
    "All numbers are synthetic (or explicitly modeled); none is an actual contract or hub.",
)


def _number(name, value, low, high) -> float:
    return sm._number(name, value, low, high)  # same finite/bounds/no-bool rules


@dataclass(frozen=True)
class Inputs:
    physical_mwh: float  # Q
    hedge_mwh: float  # H
    delivery_price: float  # P_L
    reference_price: float  # P_H
    fixed_price: float  # K (always synthetic)
    delivery_source: sm.PriceSource = field(default_factory=sm.PriceSource)
    reference_source: sm.PriceSource = field(default_factory=sm.PriceSource)

    def validate(self) -> Inputs:
        _number("physical energy Q (MWh)", self.physical_mwh, *QUANTITY_BOUNDS_MWH)
        _number("hedge quantity H (MWh)", self.hedge_mwh, *QUANTITY_BOUNDS_MWH)
        _number("delivery price P_L", self.delivery_price, *PRICE_BOUNDS)
        _number("reference price P_H", self.reference_price, *PRICE_BOUNDS)
        _number("fixed price K", self.fixed_price, *PRICE_BOUNDS)
        for name, src in (("delivery", self.delivery_source), ("reference", self.reference_source)):
            if src.kind not in ("synthetic", "modeled"):
                raise sm.SettlementError(f"{name} price source must be synthetic or modeled")
            if src.kind == "modeled" and (src.verification != "verified" or not src.run_id):
                raise sm.SettlementError(f"{name} modeled price lacks a verified run")
        d, r = self.delivery_source, self.reference_source
        if d.kind == "modeled" and r.kind == "modeled":
            if d.run_id != r.run_id:
                raise sm.SettlementError(
                    "two modeled location prices must come from the same run (one modeled state)"
                )
            if d.bus == r.bus:
                raise sm.SettlementError("the delivery and reference buses must differ")
        return self


@dataclass(frozen=True)
class Result:
    inputs: dict
    basis: float
    physical_cost: float
    hedge_receipt: float
    net_cost: float
    fixed_component: float
    basis_component: float
    mismatch_component: float
    position: str
    formula_version: str
    assumptions: tuple[str, ...]
    sources: tuple[str, ...]
    snapshot_id: str

    def hedge_reading(self) -> str:
        if self.hedge_receipt > 0:
            return "The buyer receives this hedge payment."
        if self.hedge_receipt < 0:
            return "Negative: the buyer pays this amount on the hedge."
        return "Zero: no hedge cash flow."

    def net_reading(self) -> str:
        if self.net_cost > 0:
            return "The buyer's net cost."
        if self.net_cost < 0:
            return "Negative: a net credit to the buyer under these teaching assumptions."
        return "Zero: no net cost."


def describe_position(q: float, h: float) -> str:
    if q == 0 and h == 0:
        return "no physical energy and no hedge"
    if q == 0 and h > 0:
        return "financial position without physical consumption (not ordinary procurement)"
    if h == 0:
        return "no hedge: the whole purchase is exposed to the delivery price"
    if h < q:
        return "underhedged: hedge quantity below physical energy"
    if h > q:
        return "overhedged: hedge quantity above physical energy"
    return "hedge quantity equals physical energy"


def snapshot_id(inputs: Inputs) -> str:
    payload = {"formula_version": FORMULA_VERSION, **asdict(inputs)}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"basis-{digest}"


def evaluate(inputs: Inputs) -> Result:
    """The teaching cash flows and their decomposition. Raises SettlementError if invalid."""
    inputs.validate()
    q, h = inputs.physical_mwh, inputs.hedge_mwh
    p_l, p_h, k = inputs.delivery_price, inputs.reference_price, inputs.fixed_price
    physical = q * p_l
    receipt = h * (p_h - k)
    net = physical - receipt
    fixed_c, basis_c, mismatch_c = q * k, q * (p_l - p_h), (q - h) * (p_h - k)
    # The decomposition is computed independently; it must reproduce the net cost.
    if not math.isclose(net, fixed_c + basis_c + mismatch_c, rel_tol=1e-12, abs_tol=1e-6):
        raise sm.SettlementError("decomposition does not reproduce the net cost")
    return Result(
        inputs=asdict(inputs),
        basis=p_l - p_h + 0.0,
        physical_cost=physical + 0.0,
        hedge_receipt=receipt + 0.0,
        net_cost=net + 0.0,
        fixed_component=fixed_c + 0.0,
        basis_component=basis_c + 0.0,
        mismatch_component=mismatch_c + 0.0,
        position=describe_position(q, h),
        formula_version=FORMULA_VERSION,
        assumptions=ASSUMPTIONS,
        sources=SOURCES,
        snapshot_id=snapshot_id(inputs),
    )


def modeled_pair(record, delivery_bus: str, reference_bus: str):
    """Two verified nodal prices from the SAME economic-dispatch run (one modeled state).

    Uses the Stage 11 import checks for each bus (optimal, verified prices, current checks,
    pinned package). The fixed price K is never taken from a run.
    """
    if delivery_bus == reference_bus:
        raise sm.SettlementError("choose two different buses for delivery and reference")
    p_l, src_l = sm.modeled_price(record, delivery_bus)
    p_h, src_h = sm.modeled_price(record, reference_bus)
    return (p_l, src_l), (p_h, src_h)
