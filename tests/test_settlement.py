"""Energy-settlement teaching calculation: hand-derived benchmarks, signs, units, inputs,
provenance, and modeled-price import safeguards. All inputs are SYNTHETIC.

Hand derivations (S = D·P_DA + (A − D)·P_RT; D scheduled MWh, A actual MWh):
- equal:        D=100, A=100, P_DA=40, P_RT=55 → 4000 + 0      = 4000
- above:        D=100, A=120                    → 4000 + 20·55 = 5100
- below:        D=100, A=80                     → 4000 − 20·55 = 2900
- zero schedule D=0,   A=100                    → 0    + 100·55 = 5500
- zero actual:  D=100, A=0                      → 4000 − 100·55 = −1500 (buyer credit)
- negative:     D=100, A=120, P_DA=−10, P_RT=−20 → −1000 + 20·(−20) = −1400
- equal prices: D=100, A=130, P=40 both         → 4000 + 1200 = 5200 = 130·40
"""

import copy
import math

import pytest

from mambo_explorer import settlement as sm
from mambo_explorer import settlement_exercises as sx
from mambo_explorer.exercises import Exercise, Unavailable
from mambo_explorer.modeling import adapter
from mambo_explorer.modeling import cases as mc


def _s(d, a, p_da=40.0, p_rt=55.0):
    return sm.settle(sm.Inputs(d, a, p_da, p_rt))


@pytest.mark.parametrize(
    ("d", "a", "p_da", "p_rt", "da", "dev_mwh", "rt", "total"),
    [
        (100, 100, 40, 55, 4000, 0, 0, 4000),
        (100, 120, 40, 55, 4000, 20, 1100, 5100),
        (100, 80, 40, 55, 4000, -20, -1100, 2900),
        (0, 100, 40, 55, 0, 100, 5500, 5500),
        (100, 0, 40, 55, 4000, -100, -5500, -1500),
        (100, 120, -10, -20, -1000, 20, -400, -1400),
        (100, 130, 40, 40, 4000, 30, 1200, 5200),
    ],
    ids=["equal", "above", "below", "zero-schedule", "zero-actual", "negative", "equal-prices"],
)
def test_benchmarks(d, a, p_da, p_rt, da, dev_mwh, rt, total):
    r = _s(d, a, p_da, p_rt)
    assert r.day_ahead_component == pytest.approx(da)
    assert r.deviation_mwh == pytest.approx(dev_mwh)
    assert r.deviation_component == pytest.approx(rt)
    assert r.total == pytest.approx(total)
    assert r.total == pytest.approx(r.day_ahead_component + r.deviation_component)


@pytest.mark.parametrize("price", [-50.0, 0.0, 12.5, 40.0, 9_999.0])
@pytest.mark.parametrize(("d", "a"), [(0, 0), (100, 0), (0, 100), (100, 130), (75.5, 20.25)])
def test_equal_prices_identity(price, d, a):
    assert _s(d, a, price, price).total == pytest.approx(a * price, abs=1e-6)


def test_exposures_match_the_identity():
    base = _s(100, 120, 40, 55)
    assert _s(100, 121, 40, 55).total - base.total == pytest.approx(55)  # dS/dA = P_RT
    assert _s(100, 120, 40, 56).total - base.total == pytest.approx(20)  # dS/dP_RT = A − D
    assert _s(100, 120, 41, 55).total - base.total == pytest.approx(100)  # dS/dP_DA = D


def test_sign_readings_are_explicit_per_role():
    pay, credit, zero = _s(100, 120), _s(100, 0), _s(0, 0)
    assert pay.buyer_reading() == "The buyer pays this amount."
    assert pay.seller_reading() == "The seller receives this amount."
    assert "credit to the buyer" in credit.buyer_reading() and credit.total < 0
    assert "the seller pays" in credit.seller_reading()
    assert zero.total == 0 and "neither" in zero.buyer_reading()


def test_energy_from_power_requires_an_explicit_duration():
    assert sm.energy_from_power(50, 2) == pytest.approx(100.0)
    assert sm.energy_from_power(50, 0.25) == pytest.approx(12.5)
    for bad in (None, 0, -1, 25, math.nan, math.inf, True, "2"):
        with pytest.raises(sm.SettlementError):
            sm.energy_from_power(50, bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scheduled_energy_mwh", math.nan),
        ("scheduled_energy_mwh", -1.0),
        ("actual_energy_mwh", math.inf),
        ("actual_energy_mwh", 100_001.0),
        ("day_ahead_price", -math.inf),
        ("day_ahead_price", 10_001.0),
        ("real_time_price", -1_001.0),
        ("real_time_price", "55"),
        ("scheduled_energy_mwh", True),
    ],
)
def test_invalid_inputs_are_rejected(field, value):
    good = {
        "scheduled_energy_mwh": 100.0,
        "actual_energy_mwh": 120.0,
        "day_ahead_price": 40.0,
        "real_time_price": 55.0,
    }
    with pytest.raises(sm.SettlementError):
        sm.settle(sm.Inputs(**{**good, field: value}))


def test_result_records_provenance_and_changes_with_any_input():
    r = _s(100, 120)
    assert r.formula_version == sm.FORMULA_VERSION and r.assumptions and r.sources
    assert r.inputs["day_ahead_source"]["kind"] == "synthetic"
    ids = {
        _s(100, 120).snapshot_id,
        _s(100, 121).snapshot_id,
        _s(101, 120).snapshot_id,
        _s(100, 120, 41).snapshot_id,
        _s(100, 120, 40, 56).snapshot_id,
    }
    assert len(ids) == 5 and r.snapshot_id == _s(100, 120).snapshot_id


# --- modeled-price import ---------------------------------------------------------------


@pytest.fixture(scope="module")
def runs():
    return mc.run_lesson_runs(["congested", "breakpoint", "infeasible"], {})


def test_verified_price_imports_with_full_provenance(runs):
    price, src = sm.modeled_price(runs["congested"], "C")
    assert price == pytest.approx(40.0)
    assert src.kind == "modeled" and src.verification == "verified" and src.bus == "C"
    assert src.run_id == runs["congested"].run_id
    assert "26be8c18b7ef" in src.package and src.checks_version == adapter.CHECKS_VERSION
    r = sm.settle(sm.Inputs(100, 120, 40.0, price, real_time_source=src))
    assert r.inputs["real_time_source"]["run_id"] == runs["congested"].run_id
    assert r.snapshot_id != _s(100, 120, 40.0, price).snapshot_id  # provenance is part of it


@pytest.mark.parametrize("key", ["breakpoint", "infeasible"])
def test_withheld_or_infeasible_prices_are_never_imported(runs, key):
    with pytest.raises(sm.SettlementError):
        sm.modeled_price(runs[key], "C")


def test_failed_stale_unpinned_and_power_flow_runs_are_rejected(runs):
    good = runs["congested"]
    for change in (
        {"status": "failed"},
        {"price_status": "withheld"},
        {"checks_version": "1.1.0"},
        {"kind": "pf.dispatch"},
    ):
        bad = copy.deepcopy(good)
        for k, v in change.items():
            setattr(bad, k, v)
        with pytest.raises(sm.SettlementError):
            sm.modeled_price(bad, "C")
    unpinned = copy.deepcopy(good)
    unpinned.package["matches_pin"] = False
    with pytest.raises(sm.SettlementError, match="pinned"):
        sm.modeled_price(unpinned, "C")
    with pytest.raises(sm.SettlementError, match="no price at bus"):
        sm.modeled_price(good, "Z")


def test_one_run_cannot_supply_both_stages(runs):
    p_a, src_a = sm.modeled_price(runs["congested"], "A")
    p_c, src_c = sm.modeled_price(runs["congested"], "C")
    with pytest.raises(sm.SettlementError, match="both"):
        sm.settle(sm.Inputs(100, 120, p_a, p_c, day_ahead_source=src_a, real_time_source=src_c))


def test_an_unverified_modeled_source_is_rejected():
    fake = sm.PriceSource(kind="modeled", run_id="x", verification="withheld")
    with pytest.raises(sm.SettlementError, match="verified"):
        sm.settle(sm.Inputs(100, 120, 40, 55, day_ahead_source=fake))


# --- exercises ----------------------------------------------------------------------------


def _ex(name, r):
    e = sx.generate({"exercise_id": name, "generator": name}, r)
    assert isinstance(e, Exercise), getattr(e, "reason", e)
    return e


def _answer(e):
    return e.options[e.answer_index]


def test_exercise_answers_come_from_the_service():
    r = _s(100, 120, 40, 55)
    assert _answer(_ex("total_amount", r)) == "5,100 synthetic $"
    assert _answer(_ex("deviation_component", r)).startswith("1,100 synthetic $")
    assert _answer(_ex("role_reading", r)) == "Buyer: The buyer pays this amount."
    assert _answer(_ex("volume_exposure", r)) == "By 55 synthetic $: the real-time price"
    assert _answer(_ex("price_exposure", r)) == "By 20 synthetic $: one per MWh of deviation"
    credit = _s(100, 0, 40, 55)
    assert "credit to the buyer" in _answer(_ex("role_reading", credit))
    for name in sx.GENERATORS:
        e = _ex(name, r)
        assert e.snapshot_id == r.snapshot_id and e.synthetic
        assert all(o.count("$") <= 1 and "\\" not in o for o in e.options)


def test_changed_inputs_give_a_new_question_and_no_result_gives_none():
    a, b = _ex("total_amount", _s(100, 120)), _ex("total_amount", _s(100, 121))
    assert a.snapshot_id != b.snapshot_id and _answer(a) != _answer(b)
    assert isinstance(
        sx.generate({"exercise_id": "x", "generator": "total_amount"}, None), Unavailable
    )


def test_exposure_at_the_input_bound_is_unavailable_not_a_crash():
    top = _s(100, sm.ENERGY_BOUNDS_MWH[1])
    result = sx.generate({"exercise_id": "x", "generator": "volume_exposure"}, top)
    assert isinstance(result, Unavailable)


def test_service_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _s(100, 120)
    assert list(tmp_path.iterdir()) == []
