"""Independent benchmarks for mambo-power's DC OPF (SYNTHETIC three-bus network).

Every expected number below was derived by hand BEFORE comparing with package output.

Network: base 100 MVA; AB x = 0.10, BC x = 0.10, AC x = 0.20 pu, so susceptances AB = 10,
BC = 10, AC = 5. Reference bus A. Solving the reduced B' = [[20, -10], [-10, 15]] gives
these PTDF columns (injection at the bus, withdrawal at A):
    injection at B: AB −0.75, BC +0.25, AC −0.25
    injection at C: AB −0.50, BC −0.50, AC −0.50
With G1 at A (PTDF 0), G2 at B, and demand L at C:
    AB = −0.75·g2 + 0.5·L,   BC = 0.25·g2 + 0.5·L,   AC = −0.25·g2 + 0.5·L

Costs are linear offers c (synthetic $/MWh) on dispatch g (MW). The objective Σ c·g is a
cost RATE in $/h; over the one-hour teaching interval its value in $ is the same number.

A  Uncongested (c1 = 20, c2 = 30, L = 150, ratings 300): g1 = 150, g2 = 0, so 3000 $/h.
   Flows 75/75/75. +1 MW anywhere is served by G1: price 20 at every bus.
B  Capacity-limited (cap1 = 100): g1 = 100, g2 = 50, so 2000 + 1500 = 3500 $/h.
   Flows 37.5/87.5/62.5. G2 is marginal: price 30 everywhere. G1's capacity is worth
   20 − 30 = −10 $/h per MW (bound dual).
C  Congested (AC rating 60, other ratings 150): AC = 75 − 0.25·g2 ≤ 60, so g2 = 60 and
   g1 = 90, giving 1800 + 1800 = 3600 $/h. Flows AB 30, BC 90, AC 60 (binding).
   +1 MW at A: G1 serves it, AC unchanged, so 20.
   +1 MW at B: AC +0.25, needs Δg2 = 1, so g1 unchanged and the cost is 30.
   +1 MW at C: AC +0.5, needs Δg2 = 2 and Δg1 = −1, so 2·30 − 20 = 40.
   Relaxing the AC rating by 1 MW: g2 = 56, g1 = 94, so 3560, i.e. −40 $/h per MW.
D  Infeasible (cap1 = 100, cap2 = 50, L = 200): 150 MW < 200 MW, no dispatch exists.
E  Breakpoint (cap1 = 150 = L, ratings 300): g1 = 150, g2 = 0, 3000 $/h.
   +δ at any bus needs G2 (30); −δ reduces G1 (20). One-sided rates differ, so no
   single price exists.
E2 Congestion breakpoint (L = 120, AC rating 60): AC = 60 exactly with g2 = 0.
   At C: +δ → 40, −δ → 20.  At B: +δ → 30, −δ → 20.  At A: 20 both sides.
E3 Equal offers (c1 = c2 = 20, ratings 300): any g1 + g2 = 150 within bounds costs
   3000 $/h. The dispatch is not unique; the price (20) is.
"""

import pytest

from mambo_explorer.modeling import adapter
from mambo_explorer.modeling import opf_network as on
from mambo_explorer.modeling.runs import RunStore

TOL_MW = 1e-6
TOL_PRICE = 1e-6
STEPS = (0.01, 0.1, 1.0)  # MW; all stay inside each case's regime (checked below)


def solve(inputs, **kw):
    from mambo_power.opf import solve_dc_opf

    return solve_dc_opf(on.build_network(inputs, **kw))


def by_id(rows):
    return {r.id: r for r in rows}


CASE_A = on.OpfInputs(rating_ac=300, rating_ab_bc=300)
CASE_B = on.OpfInputs(cap_g1=100, rating_ac=300, rating_ab_bc=300)
CASE_C = on.OpfInputs()  # the default: AC 60 MW, AB/BC 150 MW
CASE_D = on.OpfInputs(cap_g1=100, cap_g2=50, load_c=200, rating_ac=300, rating_ab_bc=300)
CASE_E = on.OpfInputs(cap_g1=150, rating_ac=300, rating_ab_bc=300)
CASE_E2 = on.OpfInputs(load_c=120)
CASE_E3 = on.OpfInputs(cost_g2=20, rating_ac=300, rating_ab_bc=300)

EXPECTED = {  # hand-derived (module docstring)
    "A": {
        "g": {"G1": 150, "G2": 0},
        "rate": 3000,
        "flows": {"AB": 75, "BC": 75, "AC": 75},
        "price": {"A": 20, "B": 20, "C": 20},
    },
    "B": {
        "g": {"G1": 100, "G2": 50},
        "rate": 3500,
        "flows": {"AB": 37.5, "BC": 87.5, "AC": 62.5},
        "price": {"A": 30, "B": 30, "C": 30},
    },
    "C": {
        "g": {"G1": 90, "G2": 60},
        "rate": 3600,
        "flows": {"AB": 30, "BC": 90, "AC": 60},
        "price": {"A": 20, "B": 30, "C": 40},
    },
}
CASES = {"A": CASE_A, "B": CASE_B, "C": CASE_C}


@pytest.mark.parametrize("name", ["A", "B", "C"])
def test_dispatch_flows_and_cost_match_hand_derivation(name):
    r = solve(CASES[name])
    exp = EXPECTED[name]
    assert r.status == "Optimal"
    assert {g.id: g.p_mw for g in r.generators} == pytest.approx(exp["g"], abs=TOL_MW)
    assert {b.id: b.p_from_mw for b in r.branches} == pytest.approx(exp["flows"], abs=TOL_MW)
    assert r.objective_cost == pytest.approx(exp["rate"], abs=TOL_MW)
    assert {b.id: b.lmp for b in r.buses} == pytest.approx(exp["price"], abs=TOL_PRICE)


def test_capacity_bound_dual_sign_and_scale():
    gens = by_id(solve(CASE_B).generators)
    assert gens["G1"].bound_dual == pytest.approx(-10.0, abs=TOL_PRICE)  # 20 − 30, at upper bound
    assert gens["G2"].bound_dual == pytest.approx(0.0, abs=TOL_PRICE)
    assert by_id(solve(CASE_A).generators)["G2"].bound_dual == pytest.approx(10.0, abs=TOL_PRICE)


def _regime(r):
    """Active set: generators at a bound and lines at a limit."""
    gens = tuple(sorted((g.id, round(g.p_mw, 6) in (0.0,)) for g in r.generators))
    lines = tuple(sorted(b.id for b in r.branches if abs(b.flow_limit_dual) > TOL_PRICE))
    return gens, lines


@pytest.mark.parametrize("name", ["A", "B", "C"])
@pytest.mark.parametrize("bus", ["A", "B", "C"])
@pytest.mark.parametrize("step", STEPS)
def test_reported_price_equals_two_sided_demand_sensitivity(name, bus, step):
    """∂(cost rate $/h)/∂(demand MW) at each bus, from re-solves, equals the reported price
    ($/MWh) on both sides and at three step sizes, inside the same active-constraint regime."""
    base = solve(CASES[name])
    up = solve(CASES[name], extra_load_mw={bus: step})
    down = solve(CASES[name], extra_load_mw={bus: -step})
    assert up.status == down.status == "Optimal"
    assert _regime(up)[1] == _regime(base)[1] == _regime(down)[1]  # same binding lines
    price = by_id(base.buses)[bus].lmp
    assert price == pytest.approx(EXPECTED[name]["price"][bus], abs=TOL_PRICE)
    assert (up.objective_cost - base.objective_cost) / step == pytest.approx(price, abs=1e-6)
    assert (base.objective_cost - down.objective_cost) / step == pytest.approx(price, abs=1e-6)


@pytest.mark.parametrize("step", STEPS)
def test_line_rating_relaxation_sensitivity(step):
    """Case C: raising the AC rating by δ lowers the cost rate by 40·δ $/h, which equals the
    reported flow-limit dual (−40 $/h per MW) and the hand derivation (g2 = 60 − 4δ)."""
    base = solve(CASE_C)
    looser = solve(CASE_C, rating_delta_mw={"AC": step})
    tighter = solve(CASE_C, rating_delta_mw={"AC": -step})
    dual = by_id(base.branches)["AC"].flow_limit_dual
    assert dual == pytest.approx(-40.0, abs=TOL_PRICE)
    assert (looser.objective_cost - base.objective_cost) / step == pytest.approx(dual, abs=1e-6)
    assert (base.objective_cost - tighter.objective_cost) / step == pytest.approx(dual, abs=1e-6)
    assert by_id(looser.generators)["G2"].p_mw == pytest.approx(60 - 4 * step, abs=TOL_MW)


def test_infeasible_case_reports_infeasible_without_shedding():
    r = solve(CASE_D)
    assert r.status == "Infeasible" and r.generators == [] and r.buses == []
    run = adapter.run_dc_opf(CASE_D)
    assert run.status == "infeasible" and "never sheds load" in run.message
    assert run.dispatch == [] and run.prices == [] and run.cost_rate_per_h is None


@pytest.mark.parametrize(
    "inputs, expected",
    [
        (CASE_E, {"A": (30, 20), "B": (30, 20), "C": (30, 20)}),
        (CASE_E2, {"A": (20, 20), "B": (30, 20), "C": (40, 20)}),
    ],
)
def test_breakpoint_one_sided_sensitivities_and_withheld_prices(inputs, expected):
    base = solve(inputs)
    for bus, (up_rate, down_rate) in expected.items():
        up = solve(inputs, extra_load_mw={bus: 0.1})
        down = solve(inputs, extra_load_mw={bus: -0.1})
        assert (up.objective_cost - base.objective_cost) / 0.1 == pytest.approx(up_rate, abs=1e-6)
        assert (base.objective_cost - down.objective_cost) / 0.1 == pytest.approx(
            down_rate, abs=1e-6
        )
        reported = by_id(base.buses)[bus].lmp
        # A single solver dual is some value in [down, up]; it cannot represent both sides.
        assert (
            min(up_rate, down_rate) - TOL_PRICE <= reported <= max(up_rate, down_rate) + TOL_PRICE
        )
    run = adapter.run_dc_opf(inputs)
    assert run.status == "optimal" and run.price_status == "withheld" and run.prices == []
    assert "Breakpoint" in run.price_note


def test_equal_offers_nonunique_dispatch_verified_by_objective_not_split():
    r = solve(CASE_E3)
    assert r.objective_cost == pytest.approx(3000.0, abs=TOL_MW)  # 20 $/MWh × 150 MW
    assert sum(g.p_mw for g in r.generators) == pytest.approx(150.0, abs=TOL_MW)
    run = adapter.run_dc_opf(CASE_E3)
    assert run.status == "optimal" and run.dispatch_unique is False
    assert run.price_status == "verified"
    assert {p["bus"]: p["price_per_mwh"] for p in run.prices} == pytest.approx(
        {"A": 20, "B": 20, "C": 20}, abs=TOL_PRICE
    )


def test_unservable_perturbation_withholds_prices():
    edge = on.OpfInputs(cost_g2=20, cap_g1=150, cap_g2=0, rating_ac=300, rating_ab_bc=300)
    run = adapter.run_dc_opf(edge)
    assert run.status == "optimal" and run.price_status == "withheld"
    assert any(s["up_per_mwh"] is None for s in run.sensitivities)


# --- adapter record, checks, units, provenance -------------------------------------------


def test_adapter_record_units_and_provenance():
    run = adapter.run_dc_opf(CASE_C)
    assert run.status == "optimal" and run.price_status == "verified"
    assert run.interval_hours == 1.0
    assert run.cost_rate_per_h == pytest.approx(3600.0, abs=TOL_MW)
    assert run.interval_cost == pytest.approx(run.cost_rate_per_h * 1.0)
    assert run.solver == "highspy.Highs" and run.solver_status == "Optimal"
    assert run.package["installed_commit"] == adapter.PINNED_COMMIT
    assert run.package["highspy"] == "1.15.1"
    assert {c["name"] for c in run.checks} >= {
        "solver status",
        "system balance",
        "flows match DC power flow",
        "generator bounds",
        "branch ratings",
        "objective recomputed",
        "KKT stationarity",
        "KKT sign and complementary slackness",
    }
    assert all(c["passed"] for c in run.checks)
    binding = {b["branch"] for b in run.branches if b["binding"]}
    assert binding == {"AC"}
    assert {d["generator"]: d["energy_mwh"] for d in run.dispatch} == pytest.approx(
        {"G1": 90.0, "G2": 60.0}, abs=TOL_MW
    )  # MWh over 1 h


def _tampered(update_gen=None, update_bus=None):
    from mambo_power.opf import solve_dc_opf

    def run(net):
        r = solve_dc_opf(net)
        gens = [
            g.model_copy(update=update_gen) if update_gen and g.id == "G2" else g
            for g in r.generators
        ]
        buses = [
            b.model_copy(update=update_bus) if update_bus and b.id == "C" else b for b in r.buses
        ]
        return r.model_copy(update={"generators": gens, "buses": buses})

    return run


def test_tampered_dispatch_fails_feasibility_and_shows_nothing():
    run = adapter.run_dc_opf(CASE_C, solver=_tampered(update_gen={"p_mw": 61.0}))
    assert run.status == "failed" and run.dispatch == [] and run.prices == []
    failed = {c["name"] for c in run.checks if not c["passed"]}
    assert {"system balance", "flows match DC power flow", "objective recomputed"} & failed


def test_tampered_price_fails_kkt():
    """Bus C has no generator, so stationarity alone cannot see a wrong price there; the
    price-decomposition check (PTDF measured by the DC power flow) does."""
    run = adapter.run_dc_opf(CASE_C, solver=_tampered(update_bus={"lmp": 45.0}))
    assert run.status == "failed" and run.prices == []
    assert "price decomposition at every bus" in {c["name"] for c in run.checks if not c["passed"]}


def test_tampered_price_at_generator_bus_fails_stationarity():
    from mambo_power.opf import solve_dc_opf

    def wrong_b(net):
        r = solve_dc_opf(net)
        return r.model_copy(
            update={
                "buses": [b.model_copy(update={"lmp": 31.0}) if b.id == "B" else b for b in r.buses]
            }
        )

    run = adapter.run_dc_opf(CASE_C, solver=wrong_b)
    failed = {c["name"] for c in run.checks if not c["passed"]}
    assert (
        run.status == "failed"
        and {"KKT stationarity", "price decomposition at every bus"} <= failed
    )


def test_solver_exception_and_invalid_input_fail_cleanly():
    def broken(net):
        raise RuntimeError("HiGHS crashed")

    run = adapter.run_dc_opf(CASE_C, solver=broken)
    assert run.status == "failed" and "HiGHS crashed" in run.message and run.dispatch == []
    bad = adapter.run_dc_opf(on.OpfInputs(load_c=301))
    assert bad.status == "failed" and "outside the allowed range" in bad.message


def test_fingerprint_changes_with_every_input():
    base = CASE_C.fingerprint()
    for name in on.BOUNDS:
        low, high, default, step = on.BOUNDS[name]
        changed = on.OpfInputs(
            **{name: default + step if default + step <= high else default - step}
        )
        assert changed.fingerprint() != base, name


def test_opf_runs_persist_with_kind(tmp_path):
    store = RunStore(tmp_path / "data")
    opf = adapter.run_dc_opf(CASE_C)
    pf = adapter.run_dc_power_flow(
        __import__("mambo_explorer.modeling.teaching_network", fromlist=["Inputs"]).Inputs()
    )
    store.save(opf)
    store.save(pf)
    assert store.load(opf.run_id) == opf
    assert [r.kind for r in store.recent(kind="opf.dc")] == ["opf.dc"]
    assert [r.kind for r in store.recent(kind="pf.dc")] == ["pf.dc"]
