"""SYNTHETIC three-bus teaching network. It is not a model of ERCOT or of any real grid.

Topology (a triangle):

        Bus A (slack, G1) ──── line AB ──── Bus B (G2)
              \\                               /
            line AC                        line BC
                \\                           /
                 ───────── Bus C (load) ────

- System base 100 MVA. Reactances are per unit on that base; resistance and line
  charging are zero, as in the DC approximation.
- Signs: generation injects (+), demand withdraws. A branch flow is positive in its
  from → to direction (AB: A→B, BC: B→C, AC: A→C).
- G1 at the slack bus A balances the system: its output is whatever makes generation
  equal demand (the DC model is lossless).
- Learners control only bounded inputs: G2 output, the load at C, and line AC's
  reactance and service status. Everything else is fixed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from mambo_power.model import Branch, Bus, Generator, Load, Network

SCENARIO_ID = "three-bus-teaching"
SCENARIO_VERSION = "1.0.0"
BASE_MVA = 100.0
RATING_MVA = 100.0

# (from, to, reactance pu) for the fixed lines; AC's reactance is a control.
FIXED_LINES = {"AB": ("A", "B", 0.10), "BC": ("B", "C", 0.10)}
G1_LIMITS_MW = (0.0, 250.0)
G2_LIMITS_MW = (0.0, 200.0)

# Bounded learner controls: (minimum, maximum, default, step).
BOUNDS = {
    "g2_mw": (0.0, 200.0, 50.0, 10.0),
    "load_c_mw": (0.0, 300.0, 150.0, 10.0),
    "x_ac_pu": (0.05, 0.50, 0.20, 0.05),
}


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class Inputs:
    g2_mw: float = BOUNDS["g2_mw"][2]
    load_c_mw: float = BOUNDS["load_c_mw"][2]
    x_ac_pu: float = BOUNDS["x_ac_pu"][2]
    ac_in_service: bool = True

    def validate(self) -> Inputs:
        for name, (low, high, _, _) in BOUNDS.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InputError(f"{name} must be a number")
            if value != value or not low <= value <= high:  # rejects NaN too
                raise InputError(f"{name} = {value} is outside the allowed range {low}–{high}")
        if not isinstance(self.ac_in_service, bool):
            raise InputError("ac_in_service must be true or false")
        return self

    def snapshot(self) -> dict:
        return {"scenario_id": SCENARIO_ID, "scenario_version": SCENARIO_VERSION, **asdict(self)}

    def fingerprint(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def topology() -> list[dict]:
    """Accessible table of the network (one row per branch)."""
    rows = [
        {
            "Branch": name,
            "From bus": f,
            "To bus": t,
            "Reactance (pu, 100 MVA base)": x,
            "Rating (MVA)": RATING_MVA,
            "In service": "yes",
            "Adjustable": "no",
        }
        for name, (f, t, x) in FIXED_LINES.items()
    ]
    rows.append(
        {
            "Branch": "AC",
            "From bus": "A",
            "To bus": "C",
            "Reactance (pu, 100 MVA base)": "learner control",
            "Rating (MVA)": RATING_MVA,
            "In service": "learner control",
            "Adjustable": "yes",
        }
    )
    return rows


def buses_table() -> list[dict]:
    return [
        {
            "Bus": "A",
            "Role": "slack (reference angle 0°)",
            "Generator": "G1, balances the system",
            "Generator limits (MW)": f"{G1_LIMITS_MW[0]:g}–{G1_LIMITS_MW[1]:g}",
            "Demand": "none",
        },
        {
            "Bus": "B",
            "Role": "generator bus",
            "Generator": "G2, learner sets output",
            "Generator limits (MW)": f"{G2_LIMITS_MW[0]:g}–{G2_LIMITS_MW[1]:g}",
            "Demand": "none",
        },
        {
            "Bus": "C",
            "Role": "load bus",
            "Generator": "none",
            "Generator limits (MW)": "—",
            "Demand": "learner sets MW",
        },
    ]


def build_network(inputs: Inputs) -> Network:
    """The mambo-power Network for these inputs, using the package's own pydantic schema."""
    inputs.validate()
    buses = [
        Bus(id=b, base_kv=138.0, type=t) for b, t in (("A", "slack"), ("B", "pv"), ("C", "pq"))
    ]
    branches = [
        Branch(id=name, from_bus=f, to_bus=t, r=0.0, x=x, b=0.0, rating_mva=RATING_MVA)
        for name, (f, t, x) in FIXED_LINES.items()
    ]
    branches.append(
        Branch(
            id="AC",
            from_bus="A",
            to_bus="C",
            r=0.0,
            x=inputs.x_ac_pu,
            b=0.0,
            rating_mva=RATING_MVA,
            in_service=inputs.ac_in_service,
        )
    )
    generators = [
        Generator(
            id="G1",
            bus="A",
            p_mw=0.0,
            q_mvar=0.0,
            p_min_mw=G1_LIMITS_MW[0],
            p_max_mw=G1_LIMITS_MW[1],
            q_min_mvar=-100.0,
            q_max_mvar=100.0,
            v_set_pu=1.0,
        ),
        Generator(
            id="G2",
            bus="B",
            p_mw=inputs.g2_mw,
            q_mvar=0.0,
            p_min_mw=G2_LIMITS_MW[0],
            p_max_mw=G2_LIMITS_MW[1],
            q_min_mvar=-100.0,
            q_max_mvar=100.0,
            v_set_pu=1.0,
        ),
    ]
    loads = [Load(id="L_C", bus="C", p_mw=inputs.load_c_mw, q_mvar=0.0)]
    return Network(
        base_mva=BASE_MVA, buses=buses, branches=branches, generators=generators, loads=loads
    )
