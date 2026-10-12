"""Bounded, predefined teaching cases on the SYNTHETIC dispatch network (opf_network).

- LAB_CASES are the economic-dispatch lab's presets. Lessons link to them by key.
- LESSON_RUNS are the fixed runs lessons use (no sweeps). Each starts from a lab case and
  may override fixed inputs. A "pf.dispatch" run evaluates a SPECIFIED dispatch with the
  verified DC power flow. Its G2 output is either fixed or taken from a verified OPF run
  (`g2_from`), never typed in by a learner.

A stored result is *current* only while its input fingerprint matches what the case would
produce now, its scenario version and checks version match, and the installed package
matches the pin.
Anything else is stale and must be run again (see `is_current`).
"""

from __future__ import annotations

from dataclasses import dataclass

from mambo_explorer.modeling import adapter
from mambo_explorer.modeling import opf_network as on

# key: (title, overrides of opf_network.BOUNDS defaults)
LAB_CASES: dict[str, tuple[str, dict[str, float]]] = {
    "congested": ("Congested line (default)", {}),
    "uncongested": ("Uncongested: cheapest generator serves everything", {"rating_ac": 300.0}),
    "capacity": ("Cheap generator hits its capacity", {"cap_g1": 100.0, "rating_ac": 300.0}),
    "breakpoint": (
        "Breakpoint: demand exactly equals the cheap generator's capacity",
        {"cap_g1": 150.0, "rating_ac": 300.0},
    ),
    "equal": (
        "Equal offers: more than one cheapest dispatch",
        {"cost_g2": 20.0, "rating_ac": 300.0},
    ),
    "infeasible": (
        "Infeasible: not enough capacity",
        {"cap_g1": 100.0, "cap_g2": 50.0, "load_c": 200.0, "rating_ac": 300.0},
    ),
    "relaxed": ("Congested line with AC's rating raised to 70 MW", {"rating_ac": 70.0}),
    "ac-at-limit": ("Line AC exactly at its rating (demand 120 MW)", {"load_c": 120.0}),
    "capacity-edge": (
        "Edge of capacity: demand equals total capacity",
        {"cap_g1": 100.0, "cap_g2": 50.0, "rating_ac": 300.0},
    ),
}

OPF, PF = "opf.dc", "pf.dispatch"


@dataclass(frozen=True)
class LessonRun:
    title: str
    kind: str  # OPF or PF
    case: str  # LAB_CASES key the inputs start from
    overrides: tuple[tuple[str, float], ...] = ()
    g2_mw: float | None = None  # PF only: a fixed, specified G2 output
    g2_from: str | None = None  # PF only: G2 output of this verified OPF run


LESSON_RUNS: dict[str, LessonRun] = {
    "uncongested": LessonRun("Uncongested", OPF, "uncongested"),
    "uncongested-plus10": LessonRun(
        "Uncongested, demand +10 MW", OPF, "uncongested", (("load_c", 160.0),)
    ),
    "congested": LessonRun("Congested", OPF, "congested"),
    "congested-plus10": LessonRun(
        "Congested, demand +10 MW", OPF, "congested", (("load_c", 160.0),)
    ),
    "relaxed": LessonRun("Congested, AC rating 70 MW", OPF, "relaxed"),
    "pf-no-limit-cheapest": LessonRun(
        "Power flow: cheapest if lines had no limits", PF, "congested", g2_from="uncongested"
    ),
    "pf-chosen": LessonRun("Power flow: a dispatch chosen by hand", PF, "congested", g2_mw=90.0),
    "breakpoint": LessonRun("Breakpoint", OPF, "breakpoint"),
    # Demand 0.05 MW below the cheap generator's capacity: the +0.1 MW change crosses it.
    "near-breakpoint": LessonRun(
        "0.05 MW below a breakpoint", OPF, "breakpoint", (("load_c", 149.95),)
    ),
    # No demand at all: a −0.1 MW change would need negative generation.
    "zero-demand": LessonRun("No demand", OPF, "uncongested", (("load_c", 0.0),)),
    "ac-at-limit": LessonRun("Line AC exactly at its rating", OPF, "ac-at-limit"),
    "capacity-edge": LessonRun("Edge of capacity", OPF, "capacity-edge"),
    "equal": LessonRun("Equal offers", OPF, "equal"),
    "infeasible": LessonRun("Not enough capacity", OPF, "infeasible"),
}


def case_inputs(case: str) -> on.OpfInputs:
    overrides = LAB_CASES[case][1]
    return on.OpfInputs(
        **{
            name: float(overrides.get(name, default))
            for name, (_, _, default, _) in on.BOUNDS.items()
        }
    ).validate()


def run_inputs(key: str) -> on.OpfInputs:
    spec = LESSON_RUNS[key]
    base = case_inputs(spec.case).snapshot()
    values = {name: base[name] for name in on.BOUNDS}
    values.update(dict(spec.overrides))
    return on.OpfInputs(**values).validate()


def _g2_for(key: str, records: dict) -> float | None:
    """The specified G2 output of a PF run, or None if its verified source is unavailable."""
    spec = LESSON_RUNS[key]
    if spec.g2_mw is not None:
        return spec.g2_mw
    source = records.get(spec.g2_from)
    if source is None or source.status != "optimal" or not is_current(spec.g2_from, records):
        return None
    g2 = next(d["dispatch_mw"] for d in source.dispatch if d["generator"] == "G2")
    return round(g2, 6) + 0.0  # + 0.0 turns -0.0 into 0.0 (stable fingerprint)


def expected_fingerprint(key: str, records: dict) -> str | None:
    spec = LESSON_RUNS[key]
    inputs = run_inputs(key)
    if spec.kind == OPF:
        return inputs.fingerprint()
    g2 = _g2_for(key, records)
    return None if g2 is None else adapter.dispatch_fingerprint(inputs, g2)


def is_current(key: str, records: dict) -> bool:
    """True only if the stored result still matches the case, the scenario, and the pin."""
    record = records.get(key)
    if record is None:
        return False
    return (
        record.kind == LESSON_RUNS[key].kind
        and getattr(record, "checks_version", None) == adapter.CHECKS_VERSION
        and record.scenario_id == on.SCENARIO_ID
        and record.scenario_version == on.SCENARIO_VERSION
        and bool(record.package.get("matches_pin"))
        and record.input_fingerprint == expected_fingerprint(key, records)
    )


def run_lesson_runs(keys: list[str], records: dict, solvers: dict | None = None) -> dict:
    """Run every key that is not current; OPF runs first (PF runs may depend on them).

    Returns a new dict. A PF run whose verified source is unavailable is left out, so no
    answer can be built from it. `solvers` ({"opf": ..., "pf": ...}) is for tests only.
    """
    solvers = solvers or {}
    out = dict(records)
    ordered = sorted(keys, key=lambda k: LESSON_RUNS[k].kind != OPF)
    for key in ordered:
        if is_current(key, out):
            continue
        spec = LESSON_RUNS[key]
        if spec.kind == OPF:
            out[key] = adapter.run_dc_opf(run_inputs(key), solver=solvers.get("opf"))
            continue
        g2 = _g2_for(key, out)
        if g2 is None:
            out.pop(key, None)
            continue
        out[key] = adapter.run_dispatch_power_flow(run_inputs(key), g2, solver=solvers.get("pf"))
    return out
