"""Basis exposure with a simplified fixed-price hedge: hand-derived benchmarks, identities,
signs, positions, inputs, provenance, and same-run modeled imports. All inputs SYNTHETIC.

Derived before running (K = 40 unless stated). net = Q·P_L − H·(P_H − K):
- equal:      Q=H=100, P_L=P_H=50  → phys 5000, receipt 100·10=1000, net 4000 = Q·K
- +basis:     Q=H=100, P_L=60, P_H=50 → 6000, 1000, net 5000 = 100·(40+10)
- −basis:     Q=H=100, P_L=45, P_H=50 → 4500, 1000, net 3500 = 100·(40−5)
- no hedge:   Q=100, H=0,   P_L=60, P_H=50 → 6000, 0,    net 6000
- under:      Q=100, H=60,  P_L=60, P_H=50 → 6000, 600,  net 5400
- over:       Q=100, H=150, P_L=60, P_H=50 → 6000, 1500, net 4500
- negative:   Q=H=100, P_L=−20, P_H=−10 → −2000, 100·(−50)=−5000 (buyer pays), net 3000
- Q=0, H=100: P_L=60, P_H=50 → 0, 1000, net −1000 (credit; a financial position only)
- hedge costs more: Q=H=100, P_L=P_H=30 → 3000, −1000, net 4000 > unhedged 3000
Decomposition Q·K + Q·(P_L−P_H) + (Q−H)·(P_H−K), e.g. under: 4000 + 1000 + 40·10 = 5400.
"""

import copy
import itertools
import math

import pytest

from mambo_explorer import basis as bx
from mambo_explorer import basis_exercises as bxe
from mambo_explorer import settlement as sm
from mambo_explorer.exercises import Exercise, Unavailable
from mambo_explorer.modeling import cases as mc


def _e(q, h, p_l, p_h, k=40.0):
    return bx.evaluate(bx.Inputs(q, h, p_l, p_h, k))


@pytest.mark.parametrize(
    ("q", "h", "p_l", "p_h", "phys", "receipt", "net", "position"),
    [
        (100, 100, 50, 50, 5000, 1000, 4000, "equals"),
        (100, 100, 60, 50, 6000, 1000, 5000, "equals"),
        (100, 100, 45, 50, 4500, 1000, 3500, "equals"),
        (100, 0, 60, 50, 6000, 0, 6000, "no hedge"),
        (100, 60, 60, 50, 6000, 600, 5400, "underhedged"),
        (100, 150, 60, 50, 6000, 1500, 4500, "overhedged"),
        (100, 100, -20, -10, -2000, -5000, 3000, "equals"),
        (0, 100, 60, 50, 0, 1000, -1000, "financial position without physical consumption"),
    ],
    ids=["equal", "pos-basis", "neg-basis", "no-hedge", "under", "over", "negative", "q0"],
)
def test_benchmarks(q, h, p_l, p_h, phys, receipt, net, position):
    r = _e(q, h, p_l, p_h)
    assert r.physical_cost == pytest.approx(phys)
    assert r.hedge_receipt == pytest.approx(receipt)
    assert r.net_cost == pytest.approx(net)
    assert r.basis == pytest.approx(p_l - p_h)
    assert position in r.position


def test_specific_decompositions():
    under = _e(100, 60, 60, 50)
    assert (under.fixed_component, under.basis_component, under.mismatch_component) == (
        pytest.approx(4000),
        pytest.approx(1000),
        pytest.approx(400),
    )
    q0 = _e(0, 100, 60, 50)
    assert (q0.fixed_component, q0.basis_component, q0.mismatch_component) == (0, 0, -1000)


GRID = list(
    itertools.product(
        [0.0, 1.0, 50.0, 100.0, 1_000.0],
        [0.0, 1.0, 60.0, 100.0, 1_500.0],
        [-1_000.0, -20.0, 0.0, 45.5, 10_000.0],
        [-500.0, 0.0, 50.0, 9_999.0],
        [-1_000.0, 0.0, 40.0, 10_000.0],
    )
)


def test_decomposition_holds_across_bounded_inputs():
    for q, h, p_l, p_h, k in GRID:
        r = _e(q, h, p_l, p_h, k)
        expected = q * p_l - h * (p_h - k)
        parts = q * k + q * (p_l - p_h) + (q - h) * (p_h - k)
        assert r.net_cost == pytest.approx(expected, rel=1e-12, abs=1e-6)
        assert parts == pytest.approx(expected, rel=1e-12, abs=1e-6)
        assert r.fixed_component + r.basis_component + r.mismatch_component == pytest.approx(
            r.net_cost, rel=1e-12, abs=1e-6
        )
    assert len(GRID) == 2000


def test_matched_hedge_identities():
    for q, p_l, p_h, k in itertools.product(
        [0.0, 7.5, 100.0], [-30.0, 0.0, 61.0], [-10.0, 50.0], [0.0, 40.0]
    ):
        r = _e(q, q, p_l, p_h, k)
        assert r.net_cost == pytest.approx(q * (k + (p_l - p_h)), abs=1e-9)
        assert r.mismatch_component == 0
        same = _e(q, q, p_h, p_h, k)
        assert same.net_cost == pytest.approx(q * k, abs=1e-9)


def test_signs_and_readings():
    pays = _e(100, 100, 30, 30)  # P_H < K: the buyer pays on the hedge
    assert pays.hedge_receipt == pytest.approx(-1000)
    assert pays.hedge_reading() == "Negative: the buyer pays this amount on the hedge."
    assert pays.net_cost == pytest.approx(4000)
    assert pays.net_cost > 100 * 30  # the hedge raised the cost above the unhedged 3,000
    credit = _e(0, 100, 60, 50)
    assert credit.net_cost < 0 and "credit to the buyer" in credit.net_reading()
    assert _e(100, 0, 60, 50).hedge_reading() == "Zero: no hedge cash flow."


@pytest.mark.parametrize(
    "field,value",
    [
        ("physical_mwh", -1.0),
        ("hedge_mwh", -0.5),
        ("physical_mwh", math.nan),
        ("hedge_mwh", math.inf),
        ("delivery_price", 10_001.0),
        ("reference_price", -math.inf),
        ("fixed_price", math.nan),
        ("fixed_price", "40"),
        ("hedge_mwh", True),
    ],
)
def test_invalid_inputs_are_rejected(field, value):
    good = dict(
        physical_mwh=100.0,
        hedge_mwh=100.0,
        delivery_price=60.0,
        reference_price=50.0,
        fixed_price=40.0,
    )
    with pytest.raises(sm.SettlementError):
        bx.evaluate(bx.Inputs(**{**good, field: value}))


def test_provenance_and_snapshot_change_with_any_input():
    r = _e(100, 100, 60, 50)
    assert (
        r.formula_version == bx.FORMULA_VERSION
        and r.assumptions
        and r.sources == ("ferc-glossary",)
    )
    ids = {
        _e(*args).snapshot_id
        for args in [
            (100, 100, 60, 50),
            (101, 100, 60, 50),
            (100, 99, 60, 50),
            (100, 100, 61, 50),
            (100, 100, 60, 51),
            (100, 100, 60, 50, 41),
        ]
    }
    assert len(ids) == 6


# --- modeled imports ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def runs():
    return mc.run_lesson_runs(["congested", "uncongested", "breakpoint", "infeasible"], {})


def test_same_run_pair_import_gives_a_modeled_basis(runs):
    (p_l, src_l), (p_h, src_h) = bx.modeled_pair(runs["congested"], "C", "A")
    assert (p_l, p_h) == (pytest.approx(40.0), pytest.approx(20.0))
    assert src_l.run_id == src_h.run_id == runs["congested"].run_id
    assert (src_l.bus, src_h.bus) == ("C", "A") and src_l.verification == "verified"
    r = bx.evaluate(
        bx.Inputs(100, 100, p_l, p_h, 40.0, delivery_source=src_l, reference_source=src_h)
    )
    assert r.basis == pytest.approx(20.0)  # modeled basis within one modeled state
    assert r.net_cost == pytest.approx(100 * (40 + 20))
    assert r.inputs["delivery_source"]["kind"] == "modeled"


def test_pair_import_refuses_same_bus_withheld_infeasible_failed_stale_and_unpinned(runs):
    with pytest.raises(sm.SettlementError, match="different buses"):
        bx.modeled_pair(runs["congested"], "C", "C")
    for key in ("breakpoint", "infeasible"):
        with pytest.raises(sm.SettlementError):
            bx.modeled_pair(runs[key], "C", "A")
    for change in ({"status": "failed"}, {"price_status": "withheld"}, {"checks_version": "0.9"}):
        bad = copy.deepcopy(runs["congested"])
        for k, v in change.items():
            setattr(bad, k, v)
        with pytest.raises(sm.SettlementError):
            bx.modeled_pair(bad, "C", "A")
    unpinned = copy.deepcopy(runs["congested"])
    unpinned.package["matches_pin"] = False
    with pytest.raises(sm.SettlementError):
        bx.modeled_pair(unpinned, "C", "A")


def test_two_modeled_prices_must_share_one_run(runs):
    p_l, src_l = sm.modeled_price(runs["congested"], "C")
    p_h, src_h = sm.modeled_price(runs["uncongested"], "A")
    with pytest.raises(sm.SettlementError, match="same run"):
        bx.evaluate(
            bx.Inputs(100, 100, p_l, p_h, 40.0, delivery_source=src_l, reference_source=src_h)
        )
    # One modeled and one synthetic price is allowed (e.g. after editing one of them).
    r = bx.evaluate(bx.Inputs(100, 100, p_l, 55.0, 40.0, delivery_source=src_l))
    assert r.inputs["reference_source"]["kind"] == "synthetic"


def test_stage_11_restriction_is_unchanged(runs):
    p_a, src_a = sm.modeled_price(runs["congested"], "A")
    p_c, src_c = sm.modeled_price(runs["congested"], "C")
    with pytest.raises(sm.SettlementError, match="both"):
        sm.settle(sm.Inputs(100, 120, p_a, p_c, day_ahead_source=src_a, real_time_source=src_c))


def test_fixed_price_has_no_modeled_source():
    assert "fixed_source" not in bx.Inputs.__dataclass_fields__
    assert any("never inferred from a model run" in a for a in bx.ASSUMPTIONS)


# --- exercises ----------------------------------------------------------------------------


def _ex(name, r):
    e = bxe.generate({"exercise_id": name, "generator": name}, r)
    assert isinstance(e, Exercise), getattr(e, "reason", e)
    return e


def _answer(e):
    return e.options[e.answer_index]


def test_exercise_answers_come_from_the_service():
    r = _e(100, 60, 60, 50)
    assert _answer(_ex("net_cost", r)) == "5,400 synthetic $"
    assert _answer(_ex("hedge_cash_flow", r)) == "The buyer receives 600 synthetic $"
    assert _answer(_ex("basis_component", r)) == "1,000 synthetic $: Q × (P_L − P_H)"
    assert _answer(_ex("mismatch_component", r)) == "400 synthetic $"
    assert _answer(_ex("hedge_effect", r)) == "The hedge lowered the cost by 600 synthetic $"
    worse = _e(100, 100, 30, 30)
    assert _answer(_ex("hedge_effect", worse)) == "The hedge raised the cost by 1,000 synthetic $"
    assert _answer(_ex("hedge_cash_flow", worse)) == "The buyer pays 1,000 synthetic $"
    for name in bxe.GENERATORS:
        e = _ex(name, r)
        assert e.snapshot_id == r.snapshot_id and e.synthetic
        assert all(o.count("$") <= 1 and "\\" not in o for o in e.options)


def test_changed_inputs_give_new_questions_and_no_result_gives_none():
    a, b = _ex("net_cost", _e(100, 60, 60, 50)), _ex("net_cost", _e(100, 61, 60, 50))
    assert a.snapshot_id != b.snapshot_id and _answer(a) != _answer(b)
    assert isinstance(
        bxe.generate({"exercise_id": "x", "generator": "net_cost"}, None), Unavailable
    )


def test_service_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _e(100, 100, 60, 50)
    assert list(tmp_path.iterdir()) == []
