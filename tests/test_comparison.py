"""Stage 25: governed day-ahead vs RT-summary comparison (offline, credential-free, SYNTHETIC).

Expected values are worked by hand in comments, independently of the implementation. Approvals
name a synthetic reviewer, are marked synthetic, and count only in temporary data directories
marked with approvals.SYNTHETIC_MARKER. No quantity or amount of money appears anywhere.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import alignment_fixtures as fx
import pytest
from guards import data_elements
from price_fixtures import FakePrices, day_doc
from rt_price_fixtures import FakeRt, day_docs, interval_doc
from streamlit.testing.v1 import AppTest

from mambo_explorer import alignment_view, cli, routes
from mambo_explorer.ercot import aggregation as ag
from mambo_explorer.ercot import aggregation_policy as agp
from mambo_explorer.ercot import alignment as al
from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot import assumed_alignment as aa
from mambo_explorer.ercot import comparison as cmp
from mambo_explorer.ercot import comparison_policy as cmpp
from mambo_explorer.ercot import prices as px
from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.client import ErcotClient
from mambo_explorer.ercot.m1_policy import M1

SRC = Path(__file__).resolve().parents[1] / "src" / "mambo_explorer"
NOW = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)
SYN = {
    "reviewer": "Synthetic Reviewer",
    "role": "synthetic test role",
    "evidence": "SYN-approval-note",
    "approved_on": "2026-10-01",
}
A, B = cmpp.CMP_A, cmpp.CMP_B

# --- independent benchmarks (hand-worked) -----------------------------------------------------

BENCH = [
    # (RT summary, DAM, RT − DAM by hand)
    ("40", "30", "10"),  # 40 − 30 = +10
    ("20", "50", "-30"),  # 20 − 50 = −30
    ("20", "-10", "30"),  # 20 − (−10) = +30
    ("-10", "20", "-30"),  # −10 − 20 = −30
    ("-5", "-20", "15"),  # −5 − (−20) = +15
    ("42.5", "42.5", "0"),  # equal prices: 0
    ("9001.25", "0.75", "9000.5"),  # large: 9001.25 − 0.75 = 9000.50
    ("0.01", "0.02", "-0.01"),  # small: 0.01 − 0.02 = −0.01
    ("0", "0", "0"),  # zero prices
]


@pytest.mark.parametrize("rt_summary,dam,expected", BENCH)
def test_cmp_a_and_cmp_b_benchmarks(rt_summary, dam, expected):
    assert cmp.difference_rt_first(rt_summary, dam) == Decimal(expected)
    assert cmp.difference_dam_first(rt_summary, dam) == -Decimal(expected)  # exact reversal
    a = cmp.candidate(cmp.RT_FIRST, rt_summary, dam)
    b = cmp.candidate(cmp.DAM_FIRST, rt_summary, dam)
    assert a.status == b.status == cmp.CANDIDATE_ONLY and a.units == "$/MWh"
    assert Decimal(a.output) == -Decimal(b.output)


def test_absolute_and_percentage_candidates():
    # |20 − 50| = 30; (40 − 30) / 30 × 100 = 33.33…; (−5 − (−20)) / (−20) × 100 = −75
    assert cmp.absolute_difference("20", "50") == Decimal(30)
    assert cmp.candidate(cmp.ABSOLUTE, "20", "50").note == "direction discarded"
    assert cmp.percentage_difference("12", "0") is None  # undefined at DAM = 0
    assert cmp.candidate(cmp.PERCENTAGE, "12", "0").output is None
    neg = cmp.candidate(cmp.PERCENTAGE, "-5", "-20")
    assert Decimal(neg.output) == Decimal(-75) and "backwards" in neg.note
    assert neg.units == "%"


def test_invalid_numbers():
    for bad in ("", "x", "NaN", "Infinity"):
        with pytest.raises(cmp.ComparisonInputError):
            cmp.difference_rt_first(bad, "1")
    with pytest.raises(cmp.ComparisonInputError):
        cmp.candidate("dart", "1", "1")


# --- records ----------------------------------------------------------------------------------


def test_records_are_versioned_signed_and_unapproved():
    assert (A.rt_coefficient, A.dam_coefficient) == (1, -1)
    assert (B.rt_coefficient, B.dam_coefficient) == (-1, 1)
    for r in (A, B):
        assert r.version == "1.0.0" and r.sign_problems() == []
        assert r.output_name.startswith("Analytical DAM-to-RT price difference")
        assert "DART" not in r.output_name and r.output_units == "$/MWh"
        assert r.depends_on == f"M1@1.0.0:{M1.scope_fingerprint()}"
        assert r.aggregations == tuple(
            f"{x.id}@{x.version}:{x.scope_fingerprint()}" for x in agp.RECORDS
        )
        assert "not an approval" in r.authorization
        assert not re.search(r"Synthetic|SYN-|reviewer", repr(dataclasses.asdict(r)))
        assert set(r.supporting_evidence) <= {e.id for e in al.EVIDENCE}
    assert A.scope_fingerprint() != B.scope_fingerprint()
    assert set(cmpp.NOT_APPROVABLE) == {"absolute-difference", "percentage-difference"}
    bad = dataclasses.replace(A, dam_coefficient=1)
    assert bad.sign_problems()


def test_evidence_records_no_ercot_dart_definition():
    off13 = al.evidence("OFF-13")
    assert (
        "DASPP(sink) − DASPP(source)" in off13.proposition
        and "No ERCOT definition" in off13.ambiguity
    )
    assert "ratios" in al.evidence("OFF-14").proposition


# --- approvals ----------------------------------------------------------------------------------


@pytest.fixture
def syn_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / ap.SYNTHETIC_MARKER).write_text("synthetic test environment\n", "utf-8")
    return d


def approve(data_dir, record, **kw):
    extra = {"accepted_limitations": record.limitations_fingerprint()} if record is not M1 else {}
    event = ap.new_approval(record, **{**SYN, **extra, **kw}, now=NOW, synthetic=True)
    ap.append(data_dir, event)
    return event


def test_comparison_approval_rules(syn_dir, tmp_path):
    with pytest.raises(ap.ApprovalError, match="limitations"):
        ap.new_approval(A, **SYN, now=NOW)
    e = approve(syn_dir, A)
    assert (
        ap.status(syn_dir, A).status == ap.APPROVED and ap.status(syn_dir, B).status == ap.MISSING
    )
    ap.append(syn_dir, ap.new_revocation(A, e.record_id, "synthetic", now=NOW))
    assert ap.status(syn_dir, A).status == ap.REVOKED
    assert ap.status(syn_dir, dataclasses.replace(A, status="superseded")).status == ap.SUPERSEDED
    assert ap.status(syn_dir, dataclasses.replace(A, formula_version="CA.2")).status == ap.REVOKED
    unmarked = tmp_path / "real-like"
    approve(unmarked, A)
    assert ap.status(unmarked, A).status == ap.INVALID


# --- production gating ------------------------------------------------------------------------

PRICES = {"1": "20", "2": "40", "3": "60", "4": "80"}  # summary (20+40+60+80)/4 = 50


def build(
    data_dir,
    *,
    method="CMP-A",
    agg="AGG-A",
    case=fx.ORDINARY,
    policy=al.LATEST_RETRIEVED,
    basis=aa.ASSUMPTION,
    prices=PRICES,
    dam_price="30",
    dam_identity=None,
    dam_unit="$/MWh",
    dam_revision=None,
    agg_state="current",
    agg_snap=True,
    align_state="current",
    mode=cmp.GOVERNED,
):
    dam_obs, rts = case
    m1a = ap.status(data_dir, M1)
    alignment = aa.align_with_basis(basis, dam_obs, rts, revision_policy=policy, approval=m1a)
    actx = aa.context(
        alignment.alignment_basis, alignment.dam_identity, policy, [dam_obs], rts, m1a
    )
    asnap = aa.snapshot(alignment, actx, "2026-10-13T18:00:00+00:00")
    rec = agp.record(agg)
    aggregation = ag.aggregate(
        agg,
        alignment,
        m1_approval=m1a,
        aggregation_approval=ap.status(data_dir, rec),
        alignment_snapshot=asnap,
        alignment_snapshot_state=align_state,
        price_lookup=lambda i: prices.get(i["DeliveryInterval"]),
    )
    gctx = ag.context(aggregation, align_state)
    gsnap = ag.snapshot(aggregation, gctx, "2026-10-13T18:05:00+00:00") if agg_snap else None
    dam = None
    if dam_price is not None:
        sel = alignment.dam_revision or {"revision": 1, "doc_id": "SYN-DAM-1"}
        rev = dam_revision or sel
        dam = cmp.DamInput(
            dam_identity or alignment.dam_identity,
            rev["revision"],
            rev["doc_id"],
            dam_price,
            dam_unit,
            "2026-10-12T12:46:27-05:00",
            "2026-10-12 18:00:00+00",
        )
    crec = cmpp.RECORDS[0] if method == "CMP-A" else (B if method == "CMP-B" else None)
    return cmp.compare(
        method,
        mode=mode,
        alignment=alignment,
        aggregation=aggregation,
        aggregation_snapshot=gsnap,
        aggregation_snapshot_state=agg_state if agg_snap else None,
        dam=dam,
        m1_approval=m1a,
        aggregation_approval=ap.status(data_dir, rec),
        comparison_approval=ap.status(data_dir, crec) if crec else None,
    )


@pytest.fixture
def full(syn_dir):
    for r in (M1, agp.AGG_A, agp.AGG_B, A, B):
        approve(syn_dir, r)
    return syn_dir


def test_complete_comparison_both_conventions(full):
    a, b = build(full), build(full, method="CMP-B")
    # RT summary 50, DAM 30: CMP-A = 50 − 30 = +20; CMP-B = 30 − 50 = −20
    assert a.status == b.status == cmp.APPROVED_COMPLETE, a.blockers
    assert (a.output, b.output) == ("20", "-20")
    assert a.rt_summary == "50" and a.dam_price == "30" and a.units == "$/MWh"
    assert a.dam_revision["revision"] == 1 and len(a.rt_intervals) == 4
    assert a.aggregation == "AGG-A 1.0.0" and a.aggregation_snapshot and a.alignment_snapshot
    assert a.finality_status.startswith("not determined")
    assert a.notice == cmpp.NOTICE and all(ok for _, ok, _ in a.validation)
    assert "DART" not in a.output_name


def test_negative_and_zero_cases(full):
    neg = {k: "-5" for k in "1234"}  # RT summary −5
    assert build(full, prices=neg, dam_price="-20").output == "15"  # −5 − (−20)
    assert build(full, method="CMP-B", prices=neg, dam_price="-20").output == "-15"
    assert build(full, dam_price="50").output == "0"  # 50 − 50
    assert build(full, dam_price="0").output == "50"  # zero DAM is fine for a difference
    # AGG-B gives the same 50 for four equal 15-minute intervals
    assert build(full, agg="AGG-B").output == "20"


@pytest.mark.parametrize(
    "kw,expected",
    [
        ({"mode": "off"}, cmp.INVALID_INPUT),
        ({"basis": aa.AUTHORITATIVE}, cmp.ALIGNMENT_APPROVAL_MISSING),
        ({"case": fx.MISSING_ONE}, cmp.ALIGNMENT_INCOMPLETE),
        ({"case": fx.DUPLICATE}, cmp.CONFLICTING_REVISIONS),
        ({"policy": al.FINAL}, cmp.REVISION_UNAVAILABLE),
        ({"align_state": "stale"}, cmp.STALE_ALIGNMENT_SNAPSHOT),
        ({"agg": "AGG-B", "case": fx.FALL_REPEATED_Y}, cmp.AGGREGATION_INCOMPLETE),
        ({"agg_snap": False}, cmp.STALE_AGGREGATION_SNAPSHOT),
        ({"agg_state": "stale"}, cmp.STALE_AGGREGATION_SNAPSHOT),
        ({"dam_price": None}, cmp.DAM_OBSERVATION_MISSING),
        ({"dam_price": "  "}, cmp.DAM_OBSERVATION_MISSING),
        ({"dam_unit": "$/kWh"}, cmp.INCOMPATIBLE_UNITS),
        ({"dam_revision": {"revision": 2, "doc_id": "SYN-DAM-2"}}, cmp.INCOMPATIBLE_IDENTITY),
        ({"method": "percentage-difference"}, cmp.UNSUPPORTED_METHOD),
        ({"method": "absolute-difference"}, cmp.UNSUPPORTED_METHOD),
        ({"method": "dart"}, cmp.UNSUPPORTED_METHOD),
    ],
)
def test_withheld_states(full, kw, expected):
    res = build(full, **kw)
    assert res.status == expected, res.blockers
    assert res.output is None and res.blockers


def test_blocker_details_explain_snapshots_and_missing_dam(full):
    """Browser finding: a current snapshot of a withheld summary read as fine."""
    res = build(full, case=fx.MISSING_ONE)
    snap_detail = next(b for b in res.blockers if b.startswith("aggregation snapshot"))
    assert "is current but records alignment_incomplete" in snap_detail
    blank = build(full, case=fx.MISSING_DAM_PRICE, dam_price="")
    assert any(b.startswith("DAM observation: no selected day-ahead price") for b in blank.blockers)
    ok = build(full)
    assert (
        "matches the approved summary"
        in dict((n, d) for n, _, d in ok.validation)["aggregation snapshot"]
    )


def test_mismatched_identities(full):
    ident = {**fx.dam().hour.__dict__}
    other_hour = {
        "DeliveryDate": fx.DAY, "HourEnding": "06:00", "SettlementPoint": "HB_NORTH",
        "LocationType": "hub", "DSTFlag": "N",
    }  # fmt: skip
    assert build(full, dam_identity=other_hour).status == cmp.INCOMPATIBLE_IDENTITY
    other_hub = {**other_hour, "HourEnding": "05:00", "SettlementPoint": "HB_SOUTH"}
    assert build(full, dam_identity=other_hub).status == cmp.INCOMPATIBLE_IDENTITY
    zone = {**other_hour, "HourEnding": "05:00", "LocationType": "load zone"}
    assert build(full, dam_identity=zone).status == cmp.INCOMPATIBLE_IDENTITY
    flag = {**other_hour, "HourEnding": "05:00", "DSTFlag": "Y"}
    assert build(full, dam_identity=flag).status == cmp.INCOMPATIBLE_IDENTITY
    assert ident  # the fixture hour itself is HB_NORTH hub


def test_approval_states(syn_dir):
    assert build(syn_dir).status == cmp.ALIGNMENT_APPROVAL_MISSING  # nothing approved
    approve(syn_dir, M1)
    assert build(syn_dir).status == cmp.AGGREGATION_APPROVAL_MISSING  # M1 only
    approve(syn_dir, agp.AGG_A)
    assert build(syn_dir).status == cmp.COMPARISON_APPROVAL_MISSING  # M1 + aggregation
    e = approve(syn_dir, A)
    assert build(syn_dir).status == cmp.APPROVED_COMPLETE
    assert build(syn_dir, method="CMP-B").status == cmp.COMPARISON_APPROVAL_MISSING  # no fallback
    ap.append(syn_dir, ap.new_revocation(A, e.record_id, "synthetic", now=NOW))
    res = build(syn_dir)
    assert res.status == cmp.COMPARISON_APPROVAL_MISSING and "revoked" in " ".join(res.blockers)


def test_unsupported_aggregation_and_inconsistent_sign(full, monkeypatch):
    only_b = dataclasses.replace(A, aggregations=(A.aggregations[1],))
    monkeypatch.setattr(cmp, "RECORDS", (only_b, B))
    res = build(full)  # AGG-A is not accepted by this CMP-A variant
    assert res.status == cmp.AGGREGATION_APPROVAL_MISSING and res.output is None
    broken = dataclasses.replace(A, dam_coefficient=1)
    monkeypatch.setattr(cmp, "RECORDS", (broken, B))
    assert build(full).status == cmp.INVALID_INPUT


def test_synthetic_approvals_never_activate_in_an_unmarked_dir(tmp_path):
    d = tmp_path / "real-like"
    for r in (M1, agp.AGG_A, A):
        approve(d, r)
    res = build(d)
    assert res.status == cmp.ALIGNMENT_APPROVAL_MISSING and res.output is None


def test_finality_stays_unresolved(full):
    for kw in ({}, {"dam_price": None}):
        assert build(full, **kw).finality_status == cmpp.FINALITY_STATUS
    assert "not determined" in cmpp.FINALITY_STATUS


# --- snapshots ------------------------------------------------------------------------------------


def test_comparison_snapshot_provenance_and_invalidation(full):
    res = build(full)
    ctx = cmp.context(res, "current")
    snap = cmp.snapshot(res, ctx, "2026-10-13T18:10:00+00:00")
    assert snap["output"] == "20" and snap["dam_price"] == "30" and snap["rt_summary"] == "50"
    assert snap["finality_status"].startswith("not determined")
    assert snap["prohibited_interpretations"] and snap["sign_convention"].startswith("RT minus")
    assert ctx["dam_revision"] == [1, "SYN-DAM-1"] and len(ctx["rt_intervals"]) == 4
    cmp.record_snapshot(full, snap)
    key = cmp.snapshot_key(ctx)
    [(_, state, _)] = cmp.snapshot_states(cmp.snapshots(full), {key: ctx})
    assert state == "current"
    changes = {
        "dam_revision": [2, "SYN-DAM-2"],
        "rt_intervals": [["2", "N", 2, "x"]],
        "alignment_snapshot": "aln-other",
        "aggregation_snapshot": "agg-other:current",
        "m1": "M1@1.1.0:x",
        "aggregation": "AGG-A@1.1.0:x",
        "method": "CMP-A@1.1.0:x",
        "approvals": {**ctx["approvals"], "comparison": "revoked (x)"},
        "formula_version": "CA.2",
        "validation_version": "99",
    }
    for field, value in changes.items():
        now = {**ctx, field: value}
        states = cmp.snapshot_states(cmp.snapshots(full), {key: now, cmp.snapshot_key(now): now})
        assert states[0][1] == cmp.STALE_COMPARISON_SNAPSHOT and f"{field} changed" in states[0][2]
    policy_ctx = cmp.context(build(full, policy=al.FIRST_RETRIEVED), "current")
    assert cmp.snapshot_key(policy_ctx) != key  # a policy change is a different snapshot
    cmp.record_snapshot(full, cmp.snapshot(res, ctx, "2026-10-13T19:00:00+00:00"))
    states = [s for _, s, _ in cmp.snapshot_states(cmp.snapshots(full), {key: ctx})]
    assert states == ["superseded", "current"] and len(cmp.snapshots(full)) == 2


# --- guards -------------------------------------------------------------------------------------

CMP_MODULES = ("ercot/comparison.py", "ercot/comparison_policy.py", "comparison_view.py")


def _identifiers(tree):
    out = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    out |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    out |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    out |= {
        a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments) for a in n.args + n.kwonlyargs
    }
    return out


def test_guard_no_money_trading_or_quantity_identifiers():
    banned = re.compile(
        r"dart|pnl|profit|loss|saving|settle|backtest|signal|hedge|exposure|quantit|mwh|energy|"
        r"forecast|strategy|spread",
        re.I,
    )
    for rel in CMP_MODULES:
        hits = [
            i for i in _identifiers(ast.parse((SRC / rel).read_text("utf-8"))) if banned.search(i)
        ]
        assert not hits, (rel, hits)


def _rendered_strings(tree):
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skip.add(id(first.value))
        if isinstance(node, ast.Assign) and any(
            getattr(tg, "id", "") in ("PROHIBITED_INTERPRETATIONS", "NOT_APPROVABLE")
            for tg in node.targets
        ):
            skip |= {id(n) for n in ast.walk(node.value)}
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
    ]


def test_guard_no_unnegated_market_or_money_claims():
    # word-bounded: "SettlementPoint" is a column name, not a claim
    claim = re.compile(
        r"\bDART\b|profit|P&L|savings|\bsettlement\b|exposure|forecast|backtest", re.I
    )
    negation = re.compile(r"\b(not|no|never|none|nor)\b", re.I)
    for rel in CMP_MODULES:
        for text in _rendered_strings(ast.parse((SRC / rel).read_text("utf-8"))):
            if claim.search(text):
                assert negation.search(text), (rel, text)
    assert cmpp.NOTICE == (
        "This is an analytical price comparison under review-approved assumptions. "
        "It is not an ERCOT settlement, profit-and-loss result, trading backtest, or forecast "
        "evaluation."
    )


def test_guard_multiplication_only_in_the_percentage_candidate():
    tree = ast.parse((SRC / "ercot/comparison.py").read_text("utf-8"))
    allowed = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name in ("percentage_difference", "compare"):
            allowed |= {id(n) for n in ast.walk(fn)}
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            assert id(node) in allowed, node.lineno
    compare_fn = next(
        f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == "compare"
    )
    names = _identifiers(compare_fn)
    # production never uses the percentage or absolute candidates
    assert not {"percentage_difference", "PERCENTAGE", "absolute_difference", "ABSOLUTE"} & names
    # in compare(), multiplication is only by the record's ±1 sign coefficients
    for node in ast.walk(compare_fn):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            side = ast.unparse(node.left)
            assert side in ("record.rt_coefficient", "record.dam_coefficient"), side


def test_guard_no_import_outside_the_diagnostic_and_cli():
    allowed = {"alignment_view.py", "comparison_view.py", "cli.py"}
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel in CMP_MODULES:
            continue
        tree = ast.parse(path.read_text("utf-8"))
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        uses = {"comparison", "comparison_policy", "comparison_view"} & names or any(
            m.endswith(("comparison", "comparison_policy", "comparison_view")) for m in mods
        )
        if uses:
            assert path.name in allowed, rel  # never refresh, collect, finance, or health


def test_guard_stage_22_to_24_rules_cover_the_new_modules():
    for rel in CMP_MODULES:
        tree = ast.parse((SRC / rel).read_text("utf-8"))
        consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)]
        assert 4 not in consts and 0.25 not in consts, rel
        assert not {"astimezone", "ZoneInfo", "timedelta", "UTC"} & _identifiers(tree), rel


# --- CLI ------------------------------------------------------------------------------------------


def test_cli_comparison_workflow(syn_dir, monkeypatch, capsys):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(syn_dir))
    base = ["--no-dotenv", "comparison"]
    assert cli.main(base + ["list"]) == 0
    out = capsys.readouterr().out
    assert "CMP-A" in out and "percentage-difference" in out
    args = base + [
        "approve", "CMP-A", "--version", "1.0.0", "--scope", A.scope_fingerprint(),
        "--accept-limitations", A.limitations_fingerprint(), "--m1-version", "1.0.0",
        "--aggregations", "AGG-A@1.0.0,AGG-B@1.0.0", "--location", "HB_NORTH",
        "--reviewer", "Synthetic Reviewer", "--role", "synthetic", "--evidence", "SYN-cli",
        "--approved-on", "2026-10-01",
    ]  # fmt: skip
    assert cli.main(args) == 0
    out = capsys.readouterr().out
    assert "Dry run" in out and "Synthetic Reviewer" not in out and not ap.path(syn_dir).exists()
    wrong = [("--aggregations", "AGG-A@1.0.0"), ("--location", "HB_SOUTH"), ("--m1-version", "0.9")]
    for flag, value in wrong:
        bad = list(args)
        bad[bad.index(flag) + 1] = value
        assert cli.main(bad) == 1
    assert cli.main(args + ["--execute"]) == 0
    assert ap.status(syn_dir, A).status == ap.APPROVED
    assert cli.main(base + ["status", "CMP-A"]) == 0
    assert "Synthetic Reviewer" not in capsys.readouterr().out


# --- diagnostic page ------------------------------------------------------------------------------

EXPLORE = "from mambo_explorer.pages import render_page\nrender_page('explore')\n"
D9 = date(2026, 3, 9)  # synthetic store date


@pytest.fixture
def page_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    c = ErcotClient(
        transport=FakePrices(dict([day_doc(D9, "501")])), sleep=lambda s: None, max_requests=6
    )
    px.collect(px.Selection(latest=1), c, px.store(path))
    c = ErcotClient(
        transport=FakeRt(day_docs(D9, hours=(3,))), sleep=lambda s: None, max_requests=16
    )
    rt.collect(rt.Selection(12, False), c, rt.store(path))
    return path


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return "\n".join(parts)


def _page(data_dir, **state):
    dam, _ = alignment_view.load_day(data_dir, "03/09/2026")
    at = AppTest.from_string(EXPLORE)
    at.session_state["explore_source"] = "ercot-alignment"
    at.session_state["align_hour"] = next(o.hour for o in dam if o.hour.hour_ending == "03:00")
    for k, v in state.items():
        at.session_state[k] = v
    return at.run(timeout=60)


def test_page_off_by_default_with_notice(page_dir):
    at = _page(page_dir)
    assert not at.exception and not data_elements(at)
    text = _texts(at)
    assert cmpp.NOTICE in text and "Comparison investigation" in [h.value for h in at.header]
    assert at.radio(key="cmp_mode").value == "off" and at.radio(key="cmp_method").value is None
    assert "nothing is compared" in text
    bench = next(t.value for t in at.table if "CMP-A RT − DAM ($/MWh)" in t.value.columns)
    assert list(bench["CMP-A RT − DAM ($/MWh)"])[:6] == ["10", "-30", "30", "-30", "15", "0"]
    assert not (page_dir / "comparison").exists()


def test_page_governed_complete_with_synthetic_approvals(page_dir):
    (page_dir / ap.SYNTHETIC_MARKER).write_text("synthetic\n", "utf-8")
    for r in (M1, agp.AGG_A, A):
        approve(page_dir, r)
    state = {"align_basis": aa.ASSUMPTION, "cmp_mode": cmp.GOVERNED, "cmp_method": "CMP-A"}
    at = _page(page_dir, **state)
    assert "stale_alignment_snapshot" in _texts(at)
    at.button(key="align_snapshot").click().run(timeout=60)
    assert "stale_aggregation_snapshot" in _texts(at)
    at.button(key="agg_snapshot").click().run(timeout=60)
    text = _texts(at)
    # RT summary hour 3 = (24 + 24.25 + 24.5 + 24.75) / 4 = 24.375; fixture DAM hour 3 = −2.50
    # CMP-A = 24.375 − (−2.50) = 26.875
    assert "comparison_approved_complete" in text and "26.875 \\$/MWh" in text, text[-1500:]
    assert cmpp.NOTICE in text and not data_elements(at)
    for el in list(at.success) + list(at.markdown) + list(at.warning) + list(at.info):
        assert not re.search(r"(?<!\\)\$", el.value), el.value
    at.button(key="cmp_snapshot").click().run(timeout=60)
    assert cmp.snapshots(page_dir)[0]["output"] == "26.875"
    # a revised RT interval: everything downstream goes stale and is withheld; nothing deleted
    c = ErcotClient(transport=FakeRt(dict([interval_doc(D9, 3, 2, "8888", price="99.00")])),
                    sleep=lambda s: None, max_requests=4)  # fmt: skip
    rt.collect(rt.Selection(1, False), c, rt.store(page_dir))
    at = _page(page_dir, **state)
    text = _texts(at)
    assert "comparison_approved_complete" not in text and "the comparison is withheld" in text
    states = next(t.value for t in at.table if "Result then" in t.value.columns)
    assert list(states["State now"]) == [cmp.STALE_COMPARISON_SNAPSHOT]
    assert len(cmp.snapshots(page_dir)) == 1


def test_page_real_like_dir_withholds_and_lists_blockers(page_dir):
    state = {"align_basis": aa.ASSUMPTION, "cmp_mode": cmp.GOVERNED, "cmp_method": "CMP-B"}
    at = _page(page_dir, **state)
    text = _texts(at)
    assert "alignment_approval_missing" in text and "the comparison is withheld" in text
    assert "comparison approval: missing" in text
