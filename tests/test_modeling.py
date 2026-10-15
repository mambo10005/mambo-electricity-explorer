"""mambo-power adapter: contract, independent numerical benchmarks, failures, persistence.

The teaching network is SYNTHETIC. Expected results come from an independent closed-form
solution of the 3-bus DC equations written here (Cramer's rule). They are never taken
from mambo-power's own output.
"""

import json
import math
import subprocess
from pathlib import Path

import pytest

from mambo_explorer.modeling import adapter
from mambo_explorer.modeling import teaching_network as tn
from mambo_explorer.modeling.runs import RunStore

REPO = Path(__file__).resolve().parents[1]
TOL = 1e-9  # MW; benchmark agreement (much tighter than the 1e-6 run checks)


def reference(g2: float, load: float, x_ac: float, ac_in: bool) -> dict:
    """Independent DC solution. Slack A at 0 rad; unknowns θB, θC; base 100 MVA."""
    b_ab, b_bc = 1 / 0.10, 1 / 0.10
    b_ac = 1 / x_ac if ac_in else 0.0
    p_b, p_c = g2 / 100, -load / 100
    # [[b_ab + b_bc, -b_bc], [-b_bc, b_bc + b_ac]] @ [θB, θC] = [p_b, p_c]
    a11, a12, a22 = b_ab + b_bc, -b_bc, b_bc + b_ac
    det = a11 * a22 - a12 * a12
    th_b = (p_b * a22 - a12 * p_c) / det
    th_c = (a11 * p_c - a12 * p_b) / det
    flows = {"AB": b_ab * (0 - th_b) * 100, "BC": b_bc * (th_b - th_c) * 100}
    if ac_in:
        flows["AC"] = b_ac * (0 - th_c) * 100
    return {
        "theta_b_deg": math.degrees(th_b),
        "theta_c_deg": math.degrees(th_c),
        "flows": flows,
        "g1": load - g2,
    }


def _by(rows, key):
    return {r[key]: r for r in rows}


# --- contract ------------------------------------------------------------------------------


def test_installed_package_is_the_pinned_commit():
    info = adapter.package_info()
    assert info["installed"] and info["version"] == "0.2.0"
    assert info["installed_commit"] == adapter.PINNED_COMMIT and info["matches_pin"]
    pyproject = (REPO / "pyproject.toml").read_text("utf-8")
    assert f"mambo-power@{adapter.PINNED_COMMIT}" in pyproject.replace(" ", "").replace(
        "git+https://github.com/mambo10005/mambo-power", "mambo-power"
    )
    assert f"rev={adapter.PINNED_COMMIT}" in (REPO / "uv.lock").read_text("utf-8")


def test_network_uses_the_packages_own_schema():
    from mambo_power.model import Network, validate_network

    net = tn.build_network(tn.Inputs())
    assert isinstance(net, Network) and net.base_mva == 100.0
    assert [b.type for b in net.buses] == ["slack", "pv", "pq"]
    assert {(b.id, b.from_bus, b.to_bus, b.x) for b in net.branches} == {
        ("AB", "A", "B", 0.10),
        ("BC", "B", "C", 0.10),
        ("AC", "A", "C", 0.20),
    }
    assert all(b.r == 0 and b.b == 0 for b in net.branches)
    assert validate_network(net) == []


def test_result_carries_provenance_and_rows():
    r = adapter.run_dc_power_flow(tn.Inputs())
    assert r.status == "ok" and r.solver == "scipy.sparse.linalg.splu"
    assert r.scenario_id == "three-bus-teaching" and r.scenario_version == "1.0.0"
    assert r.inputs == {**tn.Inputs().snapshot()} and len(r.input_fingerprint) == 16
    assert {b["branch"] for b in r.branches} == {"AB", "BC", "AC"}
    assert {g["generator"] for g in r.generators} == {"G1", "G2"}


# --- independent numerical benchmarks -------------------------------------------------------


def test_hand_checked_default_case():
    """Worked by hand: θB = −0.0375 rad, θC = −0.125 rad; AB 37.5, BC 87.5, AC 62.5 MW."""
    r = adapter.run_dc_power_flow(tn.Inputs(g2_mw=50, load_c_mw=150, x_ac_pu=0.2))
    flows = {k: v["flow_from_to_mw"] for k, v in _by(r.branches, "branch").items()}
    assert flows == pytest.approx({"AB": 37.5, "BC": 87.5, "AC": 62.5}, abs=TOL)
    assert _by(r.generators, "generator")["G1"]["output_mw"] == pytest.approx(100.0, abs=TOL)
    angles = {k: v["angle_deg"] for k, v in _by(r.buses, "bus").items()}
    assert angles["A"] == 0.0
    assert angles["B"] == pytest.approx(math.degrees(-0.0375), abs=1e-12)
    assert angles["C"] == pytest.approx(math.degrees(-0.125), abs=1e-12)


@pytest.mark.parametrize(
    "g2, load, x_ac, ac_in",
    [
        (0, 0, 0.2, True),
        (0, 300, 0.05, True),
        (200, 100, 0.5, True),
        (120, 260, 0.35, True),
        (50, 150, 0.2, False),
        (200, 0, 0.1, False),
    ],
)
def test_matches_independent_reference(g2, load, x_ac, ac_in):
    r = adapter.run_dc_power_flow(
        tn.Inputs(g2_mw=g2, load_c_mw=load, x_ac_pu=x_ac, ac_in_service=ac_in)
    )
    ref = reference(g2, load, x_ac, ac_in)
    assert r.solved
    flows = {k: v["flow_from_to_mw"] for k, v in _by(r.branches, "branch").items()}
    assert flows == pytest.approx(ref["flows"], abs=TOL)
    angles = {k: v["angle_deg"] for k, v in _by(r.buses, "bus").items()}
    assert angles["B"] == pytest.approx(ref["theta_b_deg"], abs=1e-9)
    assert angles["C"] == pytest.approx(ref["theta_c_deg"], abs=1e-9)
    assert _by(r.generators, "generator")["G1"]["output_mw"] == pytest.approx(ref["g1"], abs=TOL)


def test_radial_case_is_obvious():
    """With AC out, all load reaches C through BC, and AB carries load − G2."""
    r = adapter.run_dc_power_flow(tn.Inputs(g2_mw=40, load_c_mw=130, ac_in_service=False))
    flows = {k: v["flow_from_to_mw"] for k, v in _by(r.branches, "branch").items()}
    assert flows == pytest.approx({"AB": 90.0, "BC": 130.0}, abs=TOL)


def test_lower_reactance_pulls_more_flow_onto_line_ac():
    def ac_flow(x):
        r = adapter.run_dc_power_flow(tn.Inputs(g2_mw=0, load_c_mw=200, x_ac_pu=x))
        return _by(r.branches, "branch")["AC"]["flow_from_to_mw"]

    flows = [ac_flow(x) for x in (0.5, 0.3, 0.2, 0.1, 0.05)]
    assert flows == sorted(flows)
    assert ac_flow(0.2) == pytest.approx(100.0, abs=TOL)  # equal path reactance → equal split


def test_signs_reverse_when_generation_exceeds_load():
    r = adapter.run_dc_power_flow(tn.Inputs(g2_mw=200, load_c_mw=50))
    flows = {k: v["flow_from_to_mw"] for k, v in _by(r.branches, "branch").items()}
    assert flows["AB"] < 0  # power flows B → A
    assert _by(r.generators, "generator")["G1"]["output_mw"] == pytest.approx(-150.0, abs=TOL)
    assert r.status == "ok_with_violations"  # G1 below its 0 MW minimum is reported


# --- validation, violations, failures ---------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"g2_mw": -1}, "outside the allowed range"),
        ({"load_c_mw": 301}, "outside"),
        ({"x_ac_pu": 0.0}, "outside"),
        ({"x_ac_pu": float("nan")}, "outside"),
        ({"g2_mw": True}, "must be a number"),
        ({"g2_mw": "50"}, "must be a number"),
        ({"ac_in_service": "yes"}, "true or false"),
    ],
)
def test_invalid_inputs_fail_without_outputs(kwargs, message):
    r = adapter.run_dc_power_flow(tn.Inputs(**kwargs))
    assert r.status == "failed" and message in r.message
    assert r.branches == [] and r.buses == [] and r.generators == []


def test_limit_violations_are_reported_not_hidden():
    r = adapter.run_dc_power_flow(tn.Inputs(g2_mw=0, load_c_mw=300, x_ac_pu=0.05))
    assert r.status == "ok_with_violations"
    failed = {c["name"] for c in r.checks if not c["passed"]}
    assert "generator G1 within limits" in failed  # 300 MW > 250 MW
    assert any(n.startswith("branch") and "within rating" in n for n in failed)
    assert all(c["passed"] for c in r.checks if c["kind"] == "consistency")
    assert r.branches  # flows still shown, with their violations


def test_solver_exception_fails_run_without_stale_outputs():
    def broken(net):
        raise ValueError("DC power flow: reduced B' is singular")

    r = adapter.run_dc_power_flow(tn.Inputs(), solver=broken)
    assert r.status == "failed" and "singular" in r.message and r.branches == []


def test_inconsistent_result_fails_numerical_checks():
    from mambo_power.pf import solve_dc

    def tampered(net):
        result = solve_dc(net)  # result models are frozen, so build a modified copy
        first = result.branches[0]
        bad = first.model_copy(update={"p_from_mw": first.p_from_mw + 1.0})  # breaks KCL, Δθ/x
        return result.model_copy(update={"branches": [bad, *result.branches[1:]]})

    r = adapter.run_dc_power_flow(tn.Inputs(), solver=tampered)
    assert r.status == "failed" and "numerical checks" in r.message
    assert r.branches == [] and r.checks  # checks kept for diagnosis, outputs withheld
    failed = {c["name"] for c in r.checks if not c["passed"]}
    assert {"branch flow = Δθ / x", "bus balance (KCL)"} <= failed


def test_not_converged_result_fails():
    from mambo_power.pf import solve_dc

    def unconverged(net):
        return solve_dc(net).model_copy(update={"converged": False})

    r = adapter.run_dc_power_flow(tn.Inputs(), solver=unconverged)
    assert r.status == "failed" and "not converged" in r.message


def test_input_fingerprint_changes_with_every_input():
    base = tn.Inputs().fingerprint()
    for change in (
        {"g2_mw": 60.0},
        {"load_c_mw": 160.0},
        {"x_ac_pu": 0.25},
        {"ac_in_service": False},
    ):
        assert tn.Inputs(**change).fingerprint() != base
    assert tn.Inputs().fingerprint() == base


# --- persistence ---------------------------------------------------------------------------


def test_runs_persist_locally_and_round_trip(tmp_path):
    store = RunStore(tmp_path / "data")
    ok = adapter.run_dc_power_flow(tn.Inputs())
    bad = adapter.run_dc_power_flow(tn.Inputs(g2_mw=-5))
    store.save(ok)
    store.save(bad)
    assert store.load(ok.run_id) == ok
    assert {r.run_id for r in store.recent()} == {ok.run_id, bad.run_id}
    saved = json.loads((store.root / f"{bad.run_id}.json").read_text("utf-8"))
    assert saved["status"] == "failed" and saved["branches"] == []  # failures are kept, honestly
    with pytest.raises(FileExistsError):
        store.save(ok)
    with pytest.raises(ValueError):
        store.load("../../etc/passwd")


def test_default_run_location_is_gitignored():
    result = subprocess.run(["git", "check-ignore", "-q", "data/model-runs/x.json"], cwd=REPO)
    assert result.returncode == 0
