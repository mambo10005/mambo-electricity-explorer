"""The only place application code calls mambo-power: DC power flow and linear-cost DC OPF.

`run_dc_power_flow(inputs)` builds the package's own `Network`, calls
`mambo_power.pf.solve_dc`, then checks the result with this application's independent
checks. Run status:
- "ok": solved, every check passed
- "ok_with_violations": solved and numerically consistent, but a branch is over its rating
  or the slack generator is outside its limits. DC power flow does not enforce limits,
  so these are reported, not hidden.
- "failed": invalid input, a solver error, or a failed numerical consistency check. A
  failed run carries no outputs, so nothing stale is shown.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, distribution

from mambo_explorer.modeling import sensitivity
from mambo_explorer.modeling import teaching_network as tn
from mambo_explorer.storage import now_utc

PACKAGE = "mambo-power"
PINNED_COMMIT = "26be8c18b7efb865419054bec7b0b171478bc37a"
PINNED_VERSION = "0.2.0"
# Version of this module's check and record logic, recorded in exercise snapshots. Bump it
# when a check, tolerance, or record field changes meaning.
CHECKS_VERSION = "1.2.0"  # 1.1.0: power flow at a specified dispatch (Stage 8)
# 1.2.0: finite-change terminology and fields (modeling/sensitivity.py, Stage 9). The
# price gate's decisions are unchanged; only what it records and says changed.
TOLERANCE_MW = 1e-6  # numerical consistency tolerance for balance, KCL, and flow checks


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    kind: str = "consistency"  # "consistency" failures fail the run; "limit" ones are violations


@dataclass
class RunRecord:
    run_id: str
    created_at_utc: str
    scenario_id: str
    scenario_version: str
    inputs: dict
    input_fingerprint: str
    package: dict
    status: str
    kind: str = "pf.dc"
    message: str | None = None
    solver: str | None = None
    elapsed_s: float | None = None
    checks_version: str | None = None  # CHECKS_VERSION that produced this record
    checks: list[dict] = field(default_factory=list)
    buses: list[dict] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    generators: list[dict] = field(default_factory=list)

    @property
    def solved(self) -> bool:
        return self.status in ("ok", "ok_with_violations")

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def package_info() -> dict:
    """Installed package version and the commit it was installed from (PEP 610 metadata)."""
    info = {"name": PACKAGE, "pinned_version": PINNED_VERSION, "pinned_commit": PINNED_COMMIT}
    try:
        dist = distribution(PACKAGE)
    except PackageNotFoundError:
        return {**info, "installed": False}
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    commit = direct.get("vcs_info", {}).get("commit_id")
    info.update(
        installed=True,
        version=dist.version,
        installed_commit=commit,
        matches_pin=dist.version == PINNED_VERSION and commit == PINNED_COMMIT,
    )
    try:
        info["scipy"] = distribution("scipy").version
    except PackageNotFoundError:
        info["scipy"] = None
    return info


def _checks(net, result, inputs: tn.Inputs) -> list[Check]:
    """Independent checks on the package's result (they do not reuse its internal arrays)."""
    base = net.base_mva
    angle = {b.id: math.radians(b.va_deg) for b in result.buses}
    p_bus = {b.id: b.p_mw for b in result.buses}
    branches = {b.id: b for b in net.branches if b.in_service}
    flows = {f.id: f for f in result.branches}
    gens = {g.id: g.p_mw for g in result.generators}
    load = sum(ld.p_mw for ld in net.loads if ld.in_service)
    checks: list[Check] = []

    gap = abs(sum(gens.values()) - load)
    checks.append(
        Check(
            "power balance",
            gap <= TOLERANCE_MW,
            f"generation − demand = {gap:.2e} MW (lossless DC; tolerance {TOLERANCE_MW} MW)",
        )
    )
    slack = next(b.id for b in net.buses if b.type == "slack")
    checks.append(
        Check(
            "reference bus",
            angle[slack] == 0.0,
            f"bus {slack} angle = {math.degrees(angle[slack]):g}° (must be exactly 0)",
        )
    )
    worst_flow = 0.0
    for fid, row in flows.items():
        br = branches[fid]
        expected = (angle[br.from_bus] - angle[br.to_bus]) / br.x * base
        worst_flow = max(
            worst_flow, abs(row.p_from_mw - expected), abs(row.p_to_mw + row.p_from_mw)
        )
    checks.append(
        Check(
            "branch flow = Δθ / x",
            worst_flow <= TOLERANCE_MW,
            f"largest deviation {worst_flow:.2e} MW, including from/to symmetry",
        )
    )
    worst_kcl = 0.0
    for bus in p_bus:
        out = sum(f.p_from_mw for f in flows.values() if branches[f.id].from_bus == bus)
        out += sum(f.p_to_mw for f in flows.values() if branches[f.id].to_bus == bus)
        worst_kcl = max(worst_kcl, abs(p_bus[bus] - out))
    checks.append(
        Check(
            "bus balance (KCL)",
            worst_kcl <= TOLERANCE_MW,
            f"largest |injection − outgoing flow| {worst_kcl:.2e} MW",
        )
    )
    finite = all(math.isfinite(v) for v in [*angle.values(), *p_bus.values(), *gens.values()])
    checks.append(Check("finite results", finite, "all angles, injections, and outputs finite"))

    for fid, row in flows.items():
        rating = branches[fid].rating_mva
        if rating:
            within = abs(row.p_from_mw) <= rating + TOLERANCE_MW
            checks.append(
                Check(
                    f"branch {fid} within rating",
                    within,
                    f"|flow| {abs(row.p_from_mw):.1f} MW vs rating {rating:g} MVA",
                    kind="limit",
                )
            )
    for g in net.generators:
        p = gens[g.id]
        within = g.p_min_mw - TOLERANCE_MW <= p <= g.p_max_mw + TOLERANCE_MW
        checks.append(
            Check(
                f"generator {g.id} within limits",
                within,
                f"{p:.1f} MW vs {g.p_min_mw:g}–{g.p_max_mw:g} MW",
                kind="limit",
            )
        )
    return checks


def run_dc_power_flow(inputs: tn.Inputs, solver=None) -> RunRecord:
    """Run the teaching scenario. `solver` replaces `solve_dc` in tests only."""
    record = RunRecord(
        run_id=now_utc().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8],
        created_at_utc=now_utc().isoformat(),
        scenario_id=tn.SCENARIO_ID,
        scenario_version=tn.SCENARIO_VERSION,
        inputs=inputs.snapshot(),
        input_fingerprint=inputs.fingerprint(),
        package=package_info(),
        status="failed",
        checks_version=CHECKS_VERSION,
    )
    try:
        net = tn.build_network(inputs)
        if solver is None:
            from mambo_power.pf import solve_dc as solver
        result = solver(net)
    except tn.InputError as exc:
        record.message = f"invalid input: {exc}"
        return record
    except Exception as exc:  # the package raises ValueError / UnsolvableNetworkError etc.
        record.message = f"solver error ({type(exc).__name__}): {exc}"
        return record

    return _finish_power_flow(record, net, result, inputs)


def _finish_power_flow(record: RunRecord, net, result, inputs) -> RunRecord:
    """Shared tail of the power-flow runs: checks, then outputs only if they pass."""
    record.solver = result.provenance.solver
    record.elapsed_s = result.provenance.elapsed_s
    checks = _checks(net, result, inputs)
    record.checks = [asdict(c) for c in checks]
    failed = [c for c in checks if c.kind == "consistency" and not c.passed]
    if not result.converged or failed:
        record.message = (
            "result failed numerical checks: " + ", ".join(c.name for c in failed)
            if failed
            else "solver reported not converged"
        )
        return record  # no outputs on failure
    record.status = "ok_with_violations" if any(not c.passed for c in checks) else "ok"
    record.buses = [
        {"bus": b.id, "angle_deg": b.va_deg, "net_injection_mw": b.p_mw} for b in result.buses
    ]
    record.branches = [
        {
            "branch": f.id,
            "from_bus": f.from_bus,
            "to_bus": f.to_bus,
            "flow_from_to_mw": f.p_from_mw,
            "loading_pct": f.loading_pct,
        }
        for f in result.branches
    ]
    record.generators = [
        {"generator": g.id, "bus": g.bus, "output_mw": g.p_mw} for g in result.generators
    ]
    return record


# --- Power flow at a specified dispatch on the dispatch scenario (Stage 8) -----------------


def dispatch_snapshot(inputs, g2_mw: float) -> dict:
    return {**inputs.snapshot(), "g2_mw": g2_mw}


def dispatch_fingerprint(inputs, g2_mw: float) -> str:
    payload = json.dumps(dispatch_snapshot(inputs, g2_mw), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def run_dispatch_power_flow(inputs, g2_mw: float, solver=None) -> RunRecord:
    """Evaluate a SPECIFIED dispatch on the economic-dispatch scenario with the verified DC
    power flow: G2 is fixed at g2_mw and G1 at the reference bus covers the rest.

    Nothing is optimised and no limit is enforced. Ratings and capacities are reported as
    "limit" checks (violations), exactly as in the power-flow lab. `solver` is for tests.
    """
    from mambo_explorer.modeling import opf_network as on

    record = RunRecord(
        run_id=now_utc().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8],
        created_at_utc=now_utc().isoformat(),
        scenario_id=on.SCENARIO_ID,
        scenario_version=on.SCENARIO_VERSION,
        inputs=dispatch_snapshot(inputs, g2_mw),
        input_fingerprint="",
        package=package_info(),
        status="failed",
        kind="pf.dispatch",
        checks_version=CHECKS_VERSION,
    )
    try:
        if isinstance(g2_mw, bool) or not isinstance(g2_mw, (int, float)):
            raise on.InputError("g2_mw must be a number")
        if not math.isfinite(g2_mw) or not 0.0 <= g2_mw <= on.BOUNDS["cap_g2"][1]:
            raise on.InputError(f"g2_mw = {g2_mw} is outside 0–{on.BOUNDS['cap_g2'][1]}")
        record.input_fingerprint = dispatch_fingerprint(inputs, g2_mw)
        base = on.build_network(inputs)
        net = base.model_copy(
            update={
                "generators": [
                    g.model_copy(update={"p_mw": g2_mw if g.id == "G2" else 0.0})
                    for g in base.generators
                ]
            }
        )
        if solver is None:
            from mambo_power.pf import solve_dc as solver
        result = solver(net)
    except on.InputError as exc:
        record.message = f"invalid input: {exc}"
        return record
    except Exception as exc:
        record.message = f"solver error ({type(exc).__name__}): {exc}"
        return record
    return _finish_power_flow(record, net, result, inputs)


def linear_cost_rate(inputs, outputs_mw: dict[str, float]) -> float:
    """Σ offer × output in synthetic $/h for a dispatch on the dispatch scenario (linear offers,
    the same convention the verified OPF objective uses)."""
    offers = {"G1": inputs.cost_g1, "G2": inputs.cost_g2}
    return sum(offers[g] * p for g, p in outputs_mw.items())


# --- DC optimal power flow (Stage 7) -------------------------------------------------------
#
# Verified conventions (docs/calculations.md, "DC OPF"; tests/test_opf_benchmarks.py):
# - objective_cost = Σ c1·p with c1 in $/MWh and p in MW, which is a cost RATE in $/h
# - bus lmp = ∂(cost rate)/∂(demand at that bus), in $/MWh, checked by perturbation per run
# - flow_limit_dual = ∂(cost rate)/∂(branch upper rating); ≤ 0 when the upper limit binds
# - bound_dual = reduced cost of the generator bound; ≤ 0 at the upper bound, ≥ 0 at the lower

OPF_TOL_MW = 1e-6  # HiGHS default primal feasibility tolerance is 1e-7 (MW model), plus headroom
OPF_TOL_PRICE = 1e-6  # $/MWh, for the KKT stationarity check (dual feasibility tolerance 1e-7)
OPF_TOL_COST_REL = 1e-9  # relative, on the cost rate
PRICE_STEP_MW = 0.1  # finite demand change h (MW) for the per-run price check
PRICE_FD_TOL = 1e-4  # $/MWh; a ±0.1 MW re-solve difference amplifies 1e-7-scale solver noise


@dataclass
class OpfRunRecord:
    run_id: str
    created_at_utc: str
    scenario_id: str
    scenario_version: str
    inputs: dict
    input_fingerprint: str
    package: dict
    status: str  # "optimal" | "infeasible" | "failed"
    kind: str = "opf.dc"
    checks_version: str | None = None  # CHECKS_VERSION that produced this record
    solver_status: str | None = None
    message: str | None = None
    solver: str | None = None
    interval_hours: float = 1.0
    cost_rate_per_h: float | None = None
    interval_cost: float | None = None
    price_status: str = "not available"  # "verified" | "withheld" | "not available"
    price_note: str | None = None
    dispatch_unique: bool | None = None
    dispatch_note: str | None = None
    checks: list[dict] = field(default_factory=list)
    dispatch: list[dict] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    prices: list[dict] = field(default_factory=list)
    sensitivities: list[dict] = field(default_factory=list)

    @property
    def solved(self) -> bool:
        return self.status == "optimal"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def _close(a: float, b: float, abs_tol: float, rel_tol: float = 0.0) -> bool:
    return abs(a - b) <= abs_tol + rel_tol * max(abs(a), abs(b))


def _linear_cost(generator) -> float:
    coefficients = generator.cost.coefficients  # [c1, c0], highest order first
    if len(coefficients) != 2 or coefficients[1] != 0.0:
        raise ValueError("the teaching lab supports linear costs c1·p only")
    return float(coefficients[0])


def _opf_checks(net, result) -> list[Check]:
    """Primal feasibility, recomputed flows and cost, and KKT conditions (linear costs)."""
    gens = {g.id: g for g in result.generators}
    spec = {g.id: g for g in net.generators}
    lmp = {b.id: b.lmp for b in result.buses}
    rows = {b.id: b for b in result.branches}
    rating = {b.id: b.rating_mva for b in net.branches}
    load = sum(ld.p_mw for ld in net.loads)
    checks: list[Check] = [
        Check("solver status", result.status == "Optimal", f"HiGHS model status {result.status!r}")
    ]
    values = [g.p_mw for g in gens.values()] + [b.p_from_mw for b in rows.values()]
    values += list(lmp.values())
    checks.append(
        Check(
            "finite results",
            all(math.isfinite(v) for v in values),
            "dispatch, flows, and prices finite",
        )
    )
    gap = abs(sum(g.p_mw for g in gens.values()) - load)
    checks.append(
        Check(
            "system balance",
            gap <= OPF_TOL_MW,
            f"generation − demand = {gap:.2e} MW (tolerance {OPF_TOL_MW} MW)",
        )
    )

    # Flows recomputed with the separately verified DC power flow at the optimal dispatch.
    from mambo_power.pf import solve_dc

    dispatched = net.model_copy(
        update={
            "generators": [g.model_copy(update={"p_mw": gens[g.id].p_mw}) for g in net.generators]
        }
    )
    pf = solve_dc(dispatched)
    worst = max(abs(f.p_from_mw - rows[f.id].p_from_mw) for f in pf.branches)
    pf_g1 = next(g.p_mw for g in pf.generators if g.id == "G1")
    slack_gap = abs(pf_g1 - gens["G1"].p_mw)
    checks.append(
        Check(
            "flows match DC power flow",
            worst <= OPF_TOL_MW and slack_gap <= OPF_TOL_MW,
            f"largest flow difference {worst:.2e} MW; reference-bus generator "
            f"difference {slack_gap:.2e} MW",
        )
    )

    bound_ok = all(
        spec[g].p_min_mw - OPF_TOL_MW <= gens[g].p_mw <= spec[g].p_max_mw + OPF_TOL_MW for g in gens
    )
    checks.append(Check("generator bounds", bound_ok, "every dispatch within [min, max]"))
    flow_ok = all(abs(rows[k].p_from_mw) <= rating[k] + OPF_TOL_MW for k in rows)
    checks.append(Check("branch ratings", flow_ok, "every |flow| ≤ rating"))

    cost = sum(_linear_cost(spec[g]) * gens[g].p_mw for g in gens)
    checks.append(
        Check(
            "objective recomputed",
            _close(cost, result.objective_cost, OPF_TOL_MW, OPF_TOL_COST_REL),
            f"Σ c1·p = {cost:.6f} vs reported {result.objective_cost:.6f} $/h",
        )
    )

    # KKT for the linear-cost LP: stationarity c1_g − price(bus_g) − bound_dual_g = 0, dual sign
    # feasibility, and complementary slackness. Together with primal feasibility above, this
    # certifies optimality of this convex LP within tolerance. Feasibility alone would not.
    stat = max(abs(_linear_cost(spec[g]) - lmp[gens[g].bus] - gens[g].bound_dual) for g in gens)
    checks.append(
        Check(
            "KKT stationarity",
            stat <= OPF_TOL_PRICE,
            f"max |c1 − price at bus − bound dual| = {stat:.2e} $/MWh",
            kind="optimality",
        )
    )
    complementary = True
    for g in gens.values():
        at_max = g.p_mw >= spec[g.id].p_max_mw - OPF_TOL_MW
        at_min = g.p_mw <= spec[g.id].p_min_mw + OPF_TOL_MW
        if (g.bound_dual > OPF_TOL_PRICE and not at_min) or (
            g.bound_dual < -OPF_TOL_PRICE and not at_max
        ):
            complementary = False
    for k, row in rows.items():
        mu = row.flow_limit_dual
        at_upper = row.p_from_mw >= rating[k] - OPF_TOL_MW
        at_lower = row.p_from_mw <= -rating[k] + OPF_TOL_MW
        if (mu < -OPF_TOL_PRICE and not at_upper) or (mu > OPF_TOL_PRICE and not at_lower):
            complementary = False
    checks.append(
        Check(
            "KKT sign and complementary slackness",
            complementary,
            "nonzero duals only on active bounds or limits, with the correct sign",
            kind="optimality",
        )
    )

    # Price decomposition at every bus (including buses without generators, which
    # stationarity alone does not constrain): price_j = λ + Σ_k μ_k·PTDF[k, j], with the PTDF
    # columns measured independently by the verified DC power flow (+1 MW of demand at bus j,
    # absorbed by the reference bus, changes each flow by −PTDF[k, j]).
    base_flows = {f.id: f.p_from_mw for f in pf.branches}
    worst_price = 0.0
    for bus in lmp:
        bumped = dispatched.model_copy(
            update={
                "loads": [
                    ld.model_copy(update={"p_mw": ld.p_mw + (1.0 if ld.bus == bus else 0.0)})
                    for ld in dispatched.loads
                ]
            }
        )
        flows = {f.id: f.p_from_mw for f in solve_dc(bumped).branches}
        expected = result.balance_dual + sum(
            rows[k].flow_limit_dual * -(flows[k] - base_flows[k]) for k in rows
        )
        worst_price = max(worst_price, abs(lmp[bus] - expected))
    checks.append(
        Check(
            "price decomposition at every bus",
            worst_price <= OPF_TOL_PRICE,
            f"max |price − (balance dual + Σ line dual × PTDF)| = {worst_price:.2e} $/MWh "
            "(PTDF measured with the DC power flow)",
            kind="optimality",
        )
    )
    return checks


def price_sensitivities(inputs, base_cost: float, solver, step_mw: float = PRICE_STEP_MW):
    """Average cost rates over finite demand changes of ±step_mw at each bus.

    increase rate = [C(D+h) − C(D)] / h and decrease rate = [C(D) − C(D−h)] / h, in $/MWh.
    They are averages over the change, not local derivatives (see modeling/sensitivity.py).
    Each direction records its own feasibility (rate None = infeasible) and its cost-rate
    change C(D±h) − C(D) in $/h.

    Both sides are computed at every bus. At A and B (0 MW of demand) the downward
    perturbation is a load of −step_mw. It is a mathematical perturbation for the check
    only, never a learner input, and the package accepts it (validate_network: no issues).
    """
    from mambo_explorer.modeling import opf_network as on

    out = []
    for bus in ("A", "B", "C"):
        entry: dict = {"bus": bus, "step_mw": step_mw}
        for sign, label in ((1, "up"), (-1, "down")):
            r = solver(on.build_network(inputs, extra_load_mw={bus: sign * step_mw}))
            feasible = r.status == "Optimal"
            change = r.objective_cost - base_cost if feasible else None
            entry[f"{label}_per_mwh"] = None if change is None else change / (sign * step_mw)
            entry[f"{label}_cost_change_per_h"] = change
        out.append(entry)
    return out


def alternative_optimum(net, dispatch_mw: dict[str, float], step_mw: float = PRICE_STEP_MW) -> bool:
    """True if shifting step_mw between two equal-offer generators stays feasible.

    Moving output between generators with the same offer keeps the cost unchanged. If the
    shifted dispatch also respects every bound and rating (checked with the verified DC power
    flow), another dispatch is equally optimal, so this one is not unique.
    """
    from mambo_power.pf import solve_dc

    spec = {g.id: g for g in net.generators}
    rating = {b.id: b.rating_mva for b in net.branches}
    ids = list(spec)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if not _close(_linear_cost(spec[a]), _linear_cost(spec[b]), 1e-12):
                continue
            for sign in (1, -1):
                shifted = {
                    **dispatch_mw,
                    a: dispatch_mw[a] + sign * step_mw,
                    b: dispatch_mw[b] - sign * step_mw,
                }
                if any(not spec[g].p_min_mw <= shifted[g] <= spec[g].p_max_mw for g in shifted):
                    continue
                trial = net.model_copy(
                    update={
                        "generators": [
                            g.model_copy(update={"p_mw": shifted[g.id]}) for g in net.generators
                        ]
                    }
                )
                pf = solve_dc(trial)
                if all(abs(f.p_from_mw) <= rating[f.id] + OPF_TOL_MW for f in pf.branches):
                    return True
    return False


def run_dc_opf(inputs, solver=None) -> OpfRunRecord:
    """Run the economic-dispatch teaching scenario. `solver` replaces solve_dc_opf in tests."""
    from mambo_explorer.modeling import opf_network as on

    record = OpfRunRecord(
        run_id=now_utc().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8],
        created_at_utc=now_utc().isoformat(),
        scenario_id=on.SCENARIO_ID,
        scenario_version=on.SCENARIO_VERSION,
        inputs=inputs.snapshot(),
        input_fingerprint=inputs.fingerprint(),
        package=package_info(),
        status="failed",
        interval_hours=on.INTERVAL_HOURS,
        checks_version=CHECKS_VERSION,
    )
    try:
        record.package["highspy"] = distribution("highspy").version
    except PackageNotFoundError:
        record.package["highspy"] = None
    try:
        net = on.build_network(inputs)
        if solver is None:
            from mambo_power.opf import solve_dc_opf as solver
        result = solver(net)
    except on.InputError as exc:
        record.message = f"invalid input: {exc}"
        return record
    except Exception as exc:
        record.message = f"solver error ({type(exc).__name__}): {exc}"
        return record

    record.solver_status = result.status
    record.solver = result.provenance.solver
    if result.status == "Infeasible":
        record.status = "infeasible"
        record.message = (
            "No dispatch can meet the demand within the generator capacities and "
            "line ratings. This model never sheds load automatically."
        )
        return record
    if result.status != "Optimal":
        record.message = f"solver status {result.status!r}: {result.message}"
        return record

    checks = _opf_checks(net, result)
    record.checks = [asdict(c) for c in checks]
    failed = [c.name for c in checks if not c.passed]
    if failed:
        record.message = "result failed checks: " + ", ".join(failed)
        return record  # no outputs: an unverified result is never shown
    record.status = "optimal"
    record.cost_rate_per_h = result.objective_cost
    record.interval_cost = result.objective_cost * on.INTERVAL_HOURS
    spec = {g.id: g for g in net.generators}
    rating = {b.id: b.rating_mva for b in net.branches}
    record.dispatch = [
        {
            "generator": g.id,
            "bus": g.bus,
            "dispatch_mw": g.p_mw,
            "energy_mwh": g.p_mw * on.INTERVAL_HOURS,
            "offer_per_mwh": _linear_cost(spec[g.id]),
            "at_capacity": g.p_mw >= spec[g.id].p_max_mw - OPF_TOL_MW,
        }
        for g in result.generators
    ]
    record.branches = [
        {
            "branch": b.id,
            "from_bus": b.from_bus,
            "to_bus": b.to_bus,
            "flow_mw": b.p_from_mw,
            "rating_mw": rating[b.id],
            "binding": abs(abs(b.p_from_mw) - rating[b.id]) <= OPF_TOL_MW,
            "limit_sensitivity_per_mw": b.flow_limit_dual,
        }
        for b in result.branches
    ]

    if alternative_optimum(net, {g.id: g.p_mw for g in result.generators}):
        record.dispatch_unique = False
        record.dispatch_note = (
            "Generators with the same offer can trade output without changing "
            "the cost or breaking a limit, so this is one optimal dispatch, "
            "not the only one. The total cost and the prices do not depend "
            "on which one the solver picks."
        )
    else:
        record.dispatch_unique = True

    # Prices are shown only if, at every bus, both finite changes are feasible and their
    # average rates agree with each other and with the reported value. The decisions below are
    # unchanged since Stage 7; the notes use the shared finite-change terminology.
    sens = price_sensitivities(inputs, result.objective_cost, solver)
    record.sensitivities = sens
    reported = {b.id: b for b in result.buses}
    ambiguous, mismatch, unservable = [], [], []
    for s in sens:
        up, down = s["up_per_mwh"], s["down_per_mwh"]
        if up is None or down is None:
            unservable.append(s["bus"])  # a perturbed re-solve was infeasible
        elif not _close(up, down, PRICE_FD_TOL):
            ambiguous.append(s["bus"])
        elif not _close(up, reported[s["bus"]].lmp, PRICE_FD_TOL):
            mismatch.append(s["bus"])
    if unservable:
        record.price_status = "withheld"
        record.price_note = sensitivity.unservable_note(sens, PRICE_STEP_MW)
    elif ambiguous:
        record.price_status = "withheld"
        record.price_note = sensitivity.differing_note(ambiguous, PRICE_STEP_MW)
    elif mismatch:
        record.price_status = "withheld"
        record.price_note = sensitivity.mismatch_note(mismatch, PRICE_STEP_MW)
    else:
        record.price_status = "verified"
        record.prices = [
            {
                "bus": b.id,
                "price_per_mwh": b.lmp,
                "energy_per_mwh": b.energy,
                "congestion_per_mwh": b.congestion,
            }
            for b in result.buses
        ]
    return record
