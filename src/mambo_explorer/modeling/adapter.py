"""The only place application code calls mambo-power. DC power flow only.

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

import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, distribution

from mambo_explorer.modeling import teaching_network as tn
from mambo_explorer.storage import now_utc

PACKAGE = "mambo-power"
PINNED_COMMIT = "26be8c18b7efb865419054bec7b0b171478bc37a"
PINNED_VERSION = "0.2.0"
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
    message: str | None = None
    solver: str | None = None
    elapsed_s: float | None = None
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
