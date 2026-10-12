"""SYNTHETIC three-bus economic-dispatch (DC OPF) teaching network. Not any real grid.

Same triangle as the power-flow lab (AB x = 0.10, BC x = 0.10, AC x = 0.20 pu on 100 MVA),
but both generators are dispatched by the optimizer:

- G1 at bus A (the reference bus), G2 at bus B, and the demand at bus C. Zero-MW loads at
  A and B exist only so the price check can add demand at every bus.
- Costs are **synthetic linear offers** in synthetic $ per MWh (c1). There is no quadratic
  term, no no-load (c0) cost, and no start-up cost.
- **Teaching interval: exactly one hour.** The package minimises Σ c1·p with p in MW,
  which is a cost *rate* in $/h. The interval cost in $ is that rate × 1 h. The package
  does not take a duration, so none is claimed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from mambo_power.model import Branch, Bus, Generator, Load, Network, PolynomialCost

SCENARIO_ID = "three-bus-dispatch"
SCENARIO_VERSION = "1.0.0"
BASE_MVA = 100.0
INTERVAL_HOURS = 1.0
CURRENCY = "synthetic $"
LINES = {"AB": ("A", "B", 0.10), "BC": ("B", "C", 0.10), "AC": ("A", "C", 0.20)}

# (minimum, maximum, default, step) for each learner control.
BOUNDS = {
    "cost_g1": (0.0, 100.0, 20.0, 1.0),  # $/MWh
    "cost_g2": (0.0, 100.0, 30.0, 1.0),  # $/MWh
    "cap_g1": (0.0, 300.0, 300.0, 10.0),  # MW
    "cap_g2": (0.0, 300.0, 300.0, 10.0),  # MW
    "load_c": (0.0, 300.0, 150.0, 10.0),  # MW
    "rating_ac": (10.0, 300.0, 60.0, 10.0),  # MW (DC: MVA rating used as MW limit)
    "rating_ab_bc": (10.0, 300.0, 150.0, 10.0),  # MW, applies to AB and BC
}


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class OpfInputs:
    cost_g1: float = BOUNDS["cost_g1"][2]
    cost_g2: float = BOUNDS["cost_g2"][2]
    cap_g1: float = BOUNDS["cap_g1"][2]
    cap_g2: float = BOUNDS["cap_g2"][2]
    load_c: float = BOUNDS["load_c"][2]
    rating_ac: float = BOUNDS["rating_ac"][2]
    rating_ab_bc: float = BOUNDS["rating_ab_bc"][2]

    def validate(self) -> OpfInputs:
        for name, (low, high, _, _) in BOUNDS.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InputError(f"{name} must be a number")
            if value != value or not low <= value <= high:
                raise InputError(f"{name} = {value} is outside the allowed range {low}–{high}")
        return self

    def snapshot(self) -> dict:
        return {
            "scenario_id": SCENARIO_ID,
            "scenario_version": SCENARIO_VERSION,
            "interval_hours": INTERVAL_HOURS,
            **asdict(self),
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_network(
    inputs: OpfInputs,
    extra_load_mw: dict[str, float] | None = None,
    rating_delta_mw: dict[str, float] | None = None,
) -> Network:
    """The package's own Network. `extra_load_mw` and `rating_delta_mw` exist only for the
    price-sensitivity checks; learners never set them."""
    inputs.validate()
    extra = {"A": 0.0, "B": 0.0, "C": 0.0, **(extra_load_mw or {})}
    delta = {"AB": 0.0, "BC": 0.0, "AC": 0.0, **(rating_delta_mw or {})}
    ratings = {"AB": inputs.rating_ab_bc, "BC": inputs.rating_ab_bc, "AC": inputs.rating_ac}
    buses = [
        Bus(id=b, base_kv=138.0, type=t) for b, t in (("A", "slack"), ("B", "pv"), ("C", "pq"))
    ]
    branches = [
        Branch(id=k, from_bus=f, to_bus=t, r=0.0, x=x, b=0.0, rating_mva=ratings[k] + delta[k])
        for k, (f, t, x) in LINES.items()
    ]
    generators = [
        Generator(
            id=gid,
            bus=bus,
            p_mw=0.0,
            q_mvar=0.0,
            p_min_mw=0.0,
            p_max_mw=cap,
            q_min_mvar=-100.0,
            q_max_mvar=100.0,
            v_set_pu=1.0,
            cost=PolynomialCost(coefficients=[cost, 0.0]),
        )  # c1·p + 0 (linear)
        for gid, bus, cost, cap in (
            ("G1", "A", inputs.cost_g1, inputs.cap_g1),
            ("G2", "B", inputs.cost_g2, inputs.cap_g2),
        )
    ]
    loads = [
        Load(id=f"L_{b}", bus=b, p_mw=(inputs.load_c if b == "C" else 0.0) + extra[b], q_mvar=0.0)
        for b in ("A", "B", "C")
    ]
    return Network(
        base_mva=BASE_MVA, buses=buses, branches=branches, generators=generators, loads=loads
    )


def topology() -> list[dict]:
    return [
        {
            "Branch": k,
            "From → to": f"{f} → {t}",
            "Reactance (pu, 100 MVA base)": x,
            "Rating": "learner control",
        }
        for k, (f, t, x) in LINES.items()
    ]
