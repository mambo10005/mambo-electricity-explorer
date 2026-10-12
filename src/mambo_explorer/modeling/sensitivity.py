"""Shared terminology for finite demand changes (the per-run price check). Pure; no Streamlit.

Every page that shows the price check's re-solves uses these words and formulas, so the
lab, the lessons, the exercises, and the adapter's notes cannot drift apart.

For a demand change of h MW at one bus, with C(·) the optimal cost rate in $/h:

    increase rate = [C(D + h) − C(D)] / h      (average incremental cost rate)
    decrease rate = [C(D) − C(D − h)] / h      (average decremental cost rate)

Both are in ($/h) per MW = $/MWh. Over the one-hour teaching interval, a change of h MW is
h MWh of energy and changes the interval cost by ΔC × 1 h dollars, so the same number is
also dollars per MWh of energy over the interval. Nothing else is converted.

These are **averages over the stated change**, not local derivatives. C is piecewise
linear and convex in demand (a linear program), so if no breakpoint lies in [D − h, D + h]
both averages equal the local slope. If they differ, a breakpoint lies somewhere in that
range (possibly exactly at D), and an average over a change that crosses it blends the
slopes on either side. The check cannot tell where in the range the breakpoint is, so it
never calls either average a one-sided local marginal rate.

The price gate itself (adapter.run_dc_opf) is unchanged: it uses these averages only to
decide whether a single reported price can be shown.
"""

from __future__ import annotations

# Bump when the wording's meaning or the fields below change (part of CHECKS_VERSION).
TERMINOLOGY_VERSION = "2.0.0"

INCREASE = "increase"
DECREASE = "decrease"
INCREASE_FORMULA = "[C(D + h) − C(D)] / h"
DECREASE_FORMULA = "[C(D) − C(D − h)] / h"
RATE_UNIT = "$/MWh"  # ($/h) per MW
CHANGE_UNIT = "$/h"


def _fmt_mw(step_mw: float) -> str:
    return f"{step_mw:g} MW"


def directions(s: dict, step_mw: float) -> list[dict]:
    """The two finite changes at one bus, each with its own feasibility.

    `s` is one entry of OpfRunRecord.sensitivities. Records saved before Stage 9 lack the
    cost-change fields; they are rebuilt from the rates (rate × h), which is exact.
    """
    out = []
    for key, sign, name in (("up", 1, INCREASE), ("down", -1, DECREASE)):
        rate = s.get(f"{key}_per_mwh")
        change = s.get(f"{key}_cost_change_per_h")
        if change is None and rate is not None:
            change = sign * rate * step_mw  # increase: +h·rate; decrease: C(D−h) − C(D) = −h·rate
        out.append(
            {
                "bus": s["bus"],
                "direction": name,
                "change_mw": sign * step_mw,
                "feasible": rate is not None,
                "cost_change_per_h": change,
                "rate_per_mwh": rate,
            }
        )
    return out


def infeasible_sides(sensitivities: list[dict]) -> dict[str, list[str]]:
    """{bus: ["increase"] | ["decrease"] | ["increase", "decrease"]} for buses with any
    infeasible direction."""
    out = {}
    for s in sensitivities:
        sides = [
            name
            for key, name in (("up", INCREASE), ("down", DECREASE))
            if s.get(f"{key}_per_mwh") is None
        ]
        if sides:
            out[s["bus"]] = sides
    return out


def _bus_list(buses: list[str]) -> str:
    return ("bus " if len(buses) == 1 else "buses ") + ", ".join(buses)


def unservable_note(sensitivities: list[dict], step_mw: float) -> str:
    """Direction-specific note: names exactly the directions that were infeasible."""
    groups: dict[tuple[str, ...], list[str]] = {}
    for bus, sides in infeasible_sides(sensitivities).items():
        groups.setdefault(tuple(sides), []).append(bus)
    h = _fmt_mw(step_mw)
    parts = []
    for sides, buses in groups.items():
        if sides == (INCREASE, DECREASE):
            parts.append(
                f"At {_bus_list(buses)}, both a +{h} and a −{h} change of demand are infeasible."
            )
        elif sides == (INCREASE,):
            parts.append(
                f"At {_bus_list(buses)}, a +{h} change of demand is infeasible (no dispatch meets "
                f"it within the generator limits and line ratings); the −{h} change is feasible."
            )
        else:
            parts.append(
                f"At {_bus_list(buses)}, a −{h} change of demand is infeasible (no dispatch meets "
                f"it within the generator limits and line ratings); the +{h} change is feasible."
            )
    return (
        " ".join(parts)
        + " With a direction missing, a unique two-sided marginal price was not verified for "
        "this run, so no price is shown. The base run itself is optimal and verified."
    )


def differing_note(buses: list[str], step_mw: float) -> str:
    h = _fmt_mw(step_mw)
    return (
        f"At {_bus_list(buses)}, the average cost rates over a +{h} and a −{h} change of demand "
        f"differ, so a unique two-sided marginal price was not verified for this run and no "
        f"price is shown. Because cost is piecewise linear in demand, this means a breakpoint "
        f"(a capacity or line limit being reached) lies within {h} of this operating point, "
        f"possibly exactly at it. If it lies inside a change, that change's average blends the "
        f"rates on either side. The check cannot tell where in that range it lies, so neither "
        f"average is presented as a local (one-sided) marginal rate."
    )


def mismatch_note(buses: list[str], step_mw: float) -> str:
    h = _fmt_mw(step_mw)
    return (
        f"At {_bus_list(buses)}, the average cost rates over ±{h} agree with each other but not "
        "with the reported price, so no price is shown."
    )


TABLE_CAPTION = (
    "Each row re-solves the model with demand changed by h at one bus. Increase rate = "
    f"{INCREASE_FORMULA}; decrease rate = {DECREASE_FORMULA}; C is the cost rate in "
    "synthetic $/h, so a rate is in synthetic $/MWh. These are averages over the stated "
    "change, not local derivatives: if a limit is reached inside a change, its average "
    "blends two regimes. A negative change at a bus with no demand is a mathematical "
    "perturbation for the check only."
)
