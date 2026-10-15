"""Time-shape exposure under a flat-block hedge: hand-derived benchmarks, both decompositions,
duration weighting, signs, inputs, provenance, exercises. All inputs SYNTHETIC.

Derived before running (B = 100 MW, K = 40 unless stated; h_t = B·d_t; r_t = q_t − h_t):
- peaky: d=(1,1) q=(50,150) p=(20,80) → physical 1,000+12,000 = 13,000; receipts
  100·(−20) + 100·40 = 2,000; net 11,000; B·D·K = 8,000; R = 0; p̄ = 50;
  shape = (−50)(−30) + (50)(30) = 3,000.
- reversed: q=(150,50) → physical 7,000; receipt 2,000; net 5,000; shape = −3,000.
- flat-match: q=(100,100) → physical 10,000; net 8,000; shape 0.
- constant prices p=(50,50), q=(50,150) → physical 10,000; receipt 2,000; net 8,000; shape 0.
- no hedge (B=0): net 13,000; fixed 0; R = 200; R·p̄ = 10,000; shape 3,000.
- underhedge (B=50): receipts 50·(−20)+50·40 = 1,000; net 12,000; fixed 4,000; R=100 →
  5,000; shape 3,000.
- overhedge (B=150): receipts −3,000+6,000 = 3,000; net 10,000; fixed 12,000; R=−100 →
  −5,000; shape 3,000.
- negative price p=(−10,30): physical −500+4,500 = 4,000; receipts −5,000−1,000 = −6,000
  (buyer pays); net 10,000; p̄ = 10; shape (−50)(−20) + (50)(20) = 2,000.
- hedge only q=(0,0): physical 0; receipt 2,000; net −2,000 (credit); R = −200 → −10,000;
  shape (−100)(−30) + (−100)(30) = 0.
- unequal durations d=(1,3) q=(50,300) p=(20,60): h=(100,300); physical 19,000; receipts
  −2,000+6,000 = 4,000; net 15,000; D=4; fixed 16,000; R=−50; p̄ = (20+180)/4 = 50 →
  −2,500; shape (−50)(−30) = 1,500. (An unweighted mean, 40, would give −2,000 and 1,000.)
"""

import itertools
import math

import pytest

from mambo_explorer import basis as bx
from mambo_explorer import settlement as sm
from mambo_explorer import shape as sh
from mambo_explorer import shape_exercises as sx
from mambo_explorer.exercises import Exercise, Unavailable

BENCH = {
    # key: (physical, receipt, net, fixed, R, p_bar, aggregate, shape)
    "peaky": (13000, 2000, 11000, 8000, 0, 50, 0, 3000),
    "reversed": (7000, 2000, 5000, 8000, 0, 50, 0, -3000),
    "flat-match": (10000, 2000, 8000, 8000, 0, 50, 0, 0),
    "constant-prices": (10000, 2000, 8000, 8000, 0, 50, 0, 0),
    "no-hedge": (13000, 0, 13000, 0, 200, 50, 10000, 3000),
    "underhedge": (13000, 1000, 12000, 4000, 100, 50, 5000, 3000),
    "overhedge": (13000, 3000, 10000, 12000, -100, 50, -5000, 3000),
    "negative-prices": (4000, -6000, 10000, 8000, 0, 10, 0, 2000),
    "hedge-only": (0, 2000, -2000, 8000, -200, 50, -10000, 0),
    "unequal-durations": (19000, 4000, 15000, 16000, -50, 50, -2500, 1500),
}


@pytest.mark.parametrize("key", list(BENCH))
def test_benchmarks(key):
    r = sh.evaluate(sh.scenario_inputs(key))
    phys, rec, net, fixed, big_r, p_bar, agg, shape = BENCH[key]
    assert r.physical_cost == pytest.approx(phys)
    assert r.hedge_receipt == pytest.approx(rec)
    assert r.net_cost == pytest.approx(net)
    assert r.fixed_hedge_total == pytest.approx(fixed)
    assert r.residual_mwh == pytest.approx(big_r)
    assert r.average_price == pytest.approx(p_bar)
    assert r.aggregate_mismatch == pytest.approx(agg)
    assert r.time_shape == pytest.approx(shape)


def test_required_two_hour_case_explicitly():
    inputs = sh.Inputs(
        intervals=(sh.Interval("t1", 1.0, 50.0, 20.0), sh.Interval("t2", 1.0, 150.0, 80.0)),
        hedge_mw=100.0,
        fixed_price=40.0,
    )
    r = sh.evaluate(inputs)
    assert (r.physical_cost, r.hedge_receipt, r.net_cost) == (13_000, 2_000, 11_000)
    assert (r.fixed_hedge_total, r.aggregate_mismatch, r.time_shape) == (8_000, 0, 3_000)
    assert r.total_energy_mwh == r.total_hedge_mwh == 200  # equal totals …
    assert r.time_shape != 0  # … yet a non-zero price-weighted residual
    assert [x.status for x in r.rows] == ["overhedged", "underhedged"]


def test_duration_weighting_matters_for_the_components():
    r = sh.evaluate(sh.scenario_inputs("unequal-durations"))
    assert r.average_price == pytest.approx(50.0)  # (1·20 + 3·60) / 4, not (20 + 60) / 2
    assert (r.aggregate_mismatch, r.time_shape) == (pytest.approx(-2500), pytest.approx(1500))
    assert [x.hedge_mwh for x in r.rows] == [100.0, 300.0]  # B × d, not B


def _grid():
    durations = [(1.0, 1.0), (0.25, 3.0), (2.0, 0.5, 1.5)]
    energies = [(0.0, 0.0, 0.0), (50.0, 150.0, 75.0), (300.0, 10.0, 1_000.0)]
    prices = [(20.0, 80.0, -15.0), (-1_000.0, 10_000.0, 0.0), (50.0, 50.0, 50.0)]
    for d, q, p, b, k in itertools.product(
        durations, energies, prices, [0.0, 40.0, 100.0, 750.0], [-1_000.0, 0.0, 40.0, 10_000.0]
    ):
        n = len(d)
        yield sh.Inputs(tuple(sh.Interval(f"t{i}", d[i], q[i], p[i]) for i in range(n)), b, k)


def test_both_decompositions_hold_across_bounded_inputs():
    count = 0
    for inputs in _grid():
        r = sh.evaluate(inputs)
        direct = sum(
            iv.energy_mwh * iv.price
            - inputs.hedge_mw * iv.duration_h * (iv.price - inputs.fixed_price)
            for iv in inputs.intervals
        )
        d_total = sum(iv.duration_h for iv in inputs.intervals)
        p_bar = sum(iv.duration_h * iv.price for iv in inputs.intervals) / d_total
        scale = max(1.0, abs(direct))
        assert r.net_cost == pytest.approx(direct, rel=1e-12, abs=1e-9 * scale)
        assert r.fixed_hedge_total + r.residual_cost == pytest.approx(direct, rel=1e-12, abs=1e-6)
        assert r.fixed_hedge_total + r.aggregate_mismatch + r.time_shape == pytest.approx(
            direct, rel=1e-12, abs=1e-6
        )
        assert r.average_price == pytest.approx(p_bar)
        count += 1
    assert count == 3 * 3 * 3 * 4 * 4


def test_equal_total_energy_does_not_force_a_zero_residual():
    peaky, reversed_ = (
        sh.evaluate(sh.scenario_inputs("peaky")),
        sh.evaluate(sh.scenario_inputs("reversed")),
    )
    assert peaky.total_energy_mwh == reversed_.total_energy_mwh
    assert peaky.residual_mwh == reversed_.residual_mwh == 0
    assert peaky.time_shape == -reversed_.time_shape == 3000
    assert peaky.net_cost != reversed_.net_cost


def test_reversed_profile_keeps_durations_prices_and_total_energy():
    base = sh.scenario_inputs("unequal-durations")
    rev = sh.reversed_profile(base)
    assert [iv.duration_h for iv in rev.intervals] == [iv.duration_h for iv in base.intervals]
    assert [iv.price for iv in rev.intervals] == [iv.price for iv in base.intervals]
    assert sum(iv.energy_mwh for iv in rev.intervals) == sum(iv.energy_mwh for iv in base.intervals)


def test_signs_statuses_and_power_conversion():
    neg = sh.evaluate(sh.scenario_inputs("negative-prices"))
    assert neg.rows[0].hedge_receipt == pytest.approx(-5000)  # p < K: the buyer pays
    only = sh.evaluate(sh.scenario_inputs("hedge-only"))
    assert only.net_cost < 0 and all(x.status == "overhedged" for x in only.rows)
    assert sh.energy_from_power(50, 3) == pytest.approx(150.0)
    for bad in (0, -1, 25, math.nan, None, True):
        with pytest.raises((sm.SettlementError, TypeError)):
            sh.energy_from_power(50, bad)


def _iv(*rows):
    return tuple(sh.Interval(*r) for r in rows)


@pytest.mark.parametrize(
    "inputs,match",
    [
        (sh.Inputs((), 100, 40), "1 to 24"),
        (sh.Inputs(_iv(*[(f"t{i}", 1.0, 1.0, 1.0) for i in range(25)]), 100, 40), "1 to 24"),
        (sh.Inputs(_iv(("t1", 0.0, 50, 20)), 100, 40), "greater than 0"),
        (sh.Inputs(_iv(("t1", -1.0, 50, 20)), 100, 40), "outside"),
        (sh.Inputs(_iv(("t1", 1.0, -5, 20)), 100, 40), "outside"),
        (sh.Inputs(_iv(("t1", 1.0, math.nan, 20)), 100, 40), "finite"),
        (sh.Inputs(_iv(("t1", 1.0, 50, math.inf)), 100, 40), "finite"),
        (sh.Inputs(_iv(("t1", 1.0, 50, "20")), 100, 40), "number"),
        (sh.Inputs(_iv(("t1", 1.0, 50, 20)), -1, 40), "outside"),
        (sh.Inputs(_iv(("t1", 1.0, 50, 20)), True, 40), "number"),
        (sh.Inputs(_iv(("t1", 1.0, 50, 20)), 100, math.nan), "finite"),
        (sh.Inputs(_iv(("t1", 1.0, 50, 20), ("t1", 1.0, 50, 20)), 100, 40), "repeated"),
        (sh.Inputs(_iv(("", 1.0, 50, 20)), 100, 40), "identifier"),
    ],
)
def test_invalid_inputs_are_rejected(inputs, match):
    with pytest.raises(sm.SettlementError, match=match):
        sh.evaluate(inputs)


def test_provenance_and_snapshot():
    r = sh.evaluate(sh.scenario_inputs("peaky"))
    assert r.formula_version == sh.FORMULA_VERSION and r.scenario_version == sh.SCENARIO_VERSION
    assert r.inputs["scenario"] == "peaky" and r.sources == ("eia-texas-heat-wave-2011",)
    base = sh.scenario_inputs("peaky")
    variants = [
        base,
        sh.Inputs(base.intervals, 101.0, base.fixed_price, base.scenario),
        sh.Inputs(base.intervals, base.hedge_mw, 41.0, base.scenario),
        sh.Inputs(base.intervals, base.hedge_mw, base.fixed_price, "edited:peaky"),
        sh.Inputs(_iv(("t1", 1.0, 51.0, 20.0), ("t2", 1.0, 150.0, 80.0)), 100.0, 40.0, "peaky"),
    ]
    assert len({sh.evaluate(v).snapshot_id for v in variants}) == 5


def _ex(name, r):
    e = sx.generate({"exercise_id": name, "generator": name}, r)
    assert isinstance(e, Exercise), getattr(e, "reason", e)
    return e


def test_exercise_answers_come_from_the_service():
    r = sh.evaluate(sh.scenario_inputs("peaky"))
    ans = {g: _ex(g, r) for g in sx.GENERATORS}
    pick = lambda e: e.options[e.answer_index]  # noqa: E731
    assert pick(ans["interval_status"]) == "Overhedged by 50 MWh"
    assert pick(ans["shape_component"]).startswith("3,000 synthetic $")
    assert pick(ans["mw_vs_mwh"]) == "100 MWh (power × duration)"
    assert pick(ans["profile_compare"]) == "Lower by 6,000 synthetic $"  # 5,000 vs 11,000
    assert pick(ans["negative_receipt"]) == "The buyer pays 2,000 synthetic $ on the hedge in t1"


@pytest.mark.parametrize("key", list(sh.SCENARIOS))
def test_every_scenario_gives_four_distinct_options_per_exercise(key):
    r = sh.evaluate(sh.scenario_inputs(key))
    for g in sx.GENERATORS:
        e = _ex(g, r)
        assert len(e.options) == len(set(e.options)) == 4, (key, g, e.options)
        assert all(o.count("$") <= 1 and "\\" not in o for o in e.options)
        assert e.snapshot_id == r.snapshot_id


def test_zero_shape_answer_is_worded_for_zero():
    r = sh.evaluate(sh.scenario_inputs("flat-match"))
    e = _ex("shape_component", r)
    assert e.options[e.answer_index].startswith("0 synthetic $: no mismatch")


def test_changed_inputs_give_new_questions_and_no_result_gives_none():
    a = _ex("profile_compare", sh.evaluate(sh.scenario_inputs("peaky")))
    b = _ex("profile_compare", sh.evaluate(sh.scenario_inputs("underhedge")))
    assert a.snapshot_id != b.snapshot_id
    assert isinstance(
        sx.generate({"exercise_id": "x", "generator": "mw_vs_mwh"}, None), Unavailable
    )


def test_existing_finance_calculators_are_unchanged():
    assert sm.settle(sm.Inputs(100, 120, 40, 55)).total == pytest.approx(5100)
    assert bx.evaluate(bx.Inputs(100, 60, 60, 50, 40)).net_cost == pytest.approx(5400)
    assert sm.FORMULA_VERSION == bx.FORMULA_VERSION == "1.0.0"


def test_service_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sh.evaluate(sh.scenario_inputs("peaky"))
    assert list(tmp_path.iterdir()) == []
