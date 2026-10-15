"""Stage 24: governed hourly real-time aggregation (offline, credential-free, SYNTHETIC).

Expected values are worked by hand in the comments, independently of the implementation.
Approvals name a synthetic reviewer and are marked synthetic; they count only in a temporary
data directory marked with approvals.SYNTHETIC_MARKER.
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
A, B = agp.AGG_A, agp.AGG_B

# --- independent benchmarks ------------------------------------------------------------------


def test_arithmetic_equal_duration_benchmark():
    # (20 + 40 + 60 + 80) / 4 = 200 / 4 = 50 $/MWh
    assert ag.arithmetic_mean(["20", "40", "60", "80"]) == Decimal(50)
    # (20*0.25 + 40*0.25 + 60*0.25 + 80*0.25) / (4*0.25) = 50 / 1 = 50 $/MWh
    assert ag.duration_weighted_mean(["20", "40", "60", "80"], ["0.25"] * 4) == Decimal(50)


def test_unequal_duration_benchmark_differs():
    # arithmetic: (20 + 80) / 2 = 50; duration: (20*0.25 + 80*0.75) / 1 = 5 + 60 = 65
    assert ag.arithmetic_mean(["20", "80"]) == Decimal(50)
    assert ag.duration_weighted_mean(["20", "80"], ["0.25", "0.75"]) == Decimal(65)


def test_energy_weighting_and_settlement_amount_differ_from_price_summaries():
    # (20*75 + 80*25) / (75 + 25) = (1500 + 2000) / 100 = 35 $/MWh
    assert ag.energy_weighted_price(["20", "80"], ["75", "25"]) == Decimal(35)
    # 20*75 + 80*25 = 3500 $ (an amount, not a price)
    assert ag.settlement_amount(["20", "80"], ["75", "25"]) == Decimal(3500)
    # the same prices summarized without quantities: 50, not 35
    assert ag.arithmetic_mean(["20", "80"]) != ag.energy_weighted_price(["20", "80"], ["75", "25"])


def test_equal_durations_do_not_make_a_summary_energy_weighted():
    # four equal 0.25 h intervals: duration mean 50; energy-weighted with E = [10, 10, 10, 70]:
    # (200 + 400 + 600 + 5600) / 100 = 68
    p = ["20", "40", "60", "80"]
    assert ag.duration_weighted_mean(p, ["0.25"] * 4) == Decimal(50)
    assert ag.energy_weighted_price(p, ["10", "10", "10", "70"]) == Decimal(68)


def test_negative_equal_and_zero_prices():
    # (-10 - 30 + 20 + 0) / 4 = -20 / 4 = -5
    assert ag.arithmetic_mean(["-10", "-30", "20", "0"]) == Decimal(-5)
    assert ag.arithmetic_mean(["42.17"] * 4) == Decimal("42.17")
    assert ag.arithmetic_mean(["0", "0", "0", "0"]) == 0
    assert ag.candidate(ag.ARITHMETIC, ["0", "0"]).output == "0"
    # exact decimal arithmetic on published text: (24 + 24.25 + 24.5 + 24.75) / 4 = 24.375
    assert ag.candidate(ag.ARITHMETIC, ["24.00", "24.25", "24.50", "24.75"]).output == "24.375"


def test_zero_total_energy_is_undefined_not_zero():
    assert ag.energy_weighted_price(["20", "80"], ["10", "-10"]) is None
    res = ag.candidate(ag.ENERGY_WEIGHTED, ["20", "80"], energies=["10", "-10"])
    assert res.output is None and "zero" in res.note


def test_invalid_numeric_inputs():
    for bad in ([], ["abc"], ["NaN"], ["Infinity"]):
        with pytest.raises(ag.AggregationInputError):
            ag.arithmetic_mean(bad)
    with pytest.raises(ag.AggregationInputError):
        ag.duration_weighted_mean(["1", "2"], ["0.25"])
    with pytest.raises(ag.AggregationInputError):
        ag.duration_weighted_mean(["1"], ["0"])
    with pytest.raises(ag.AggregationInputError):
        ag.candidate("hourly-anything", ["1"])


def test_candidate_results_are_candidate_only():
    for method in ag.CANDIDATES:
        res = ag.candidate(method, ["1", "3"], ["0.5", "0.5"], ["1", "1"])
        assert res.status == ag.CANDIDATE_ONLY
    assert ag.candidate(ag.SETTLEMENT_AMOUNT, ["1"], energies=["1"]).units == "$"


def test_dimensional_metadata():
    outputs = {d["Candidate"][0]: d["Output"] for d in ag.DIMENSIONS}
    assert outputs["A"].startswith("$/MWh") and outputs["B"].startswith("$/MWh")
    assert outputs["C"].startswith("$/MWh") and outputs["D"].startswith("$:")
    assert "hours" in next(
        d["Denominator"] for d in ag.DIMENSIONS if d["Candidate"].startswith("B")
    )
    assert A.output_units == B.output_units == "$/MWh"


# --- records ---------------------------------------------------------------------------------


def test_records_are_versioned_scoped_and_unapproved():
    for r in (A, B):
        assert r.version == "1.0.0" and r.status == "current"
        assert r.depends_on == f"M1@1.0.0:{M1.scope_fingerprint()}"
        assert r.output_name.startswith("Hourly analytical RT SPP summary")
        assert "not an approval" in r.authorization
        assert len(r.scope_fingerprint()) == len(r.limitations_fingerprint()) == 16
        assert set(r.revision_policies) == {"latest-retrieved", "first-retrieved"}
        assert any("spread" in u for u in r.prohibited_uses)
        assert not re.search(r"Synthetic|SYN-|reviewer", repr(dataclasses.asdict(r)))
    assert A.duration_evidence is None and B.duration_evidence.flags == ("N",)
    assert B.duration_evidence.minutes == rt.INTERVAL_MINUTES
    assert set(agp.NOT_APPROVABLE) == {"energy-weighted-price", "settlement-amount"}


def test_evidence_references_exist():
    ids = {e.id for e in al.EVIDENCE}
    for r in (A, B):
        assert set(r.supporting_evidence) <= ids
    assert set(agp.DUR_15.sources) <= ids
    hrsap = al.evidence("OFF-12")
    assert "16.11.4.3.3" in hrsap.section and "credit" in hrsap.ambiguity


# --- approvals ---------------------------------------------------------------------------------


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


def test_aggregation_approval_needs_accepted_limitations(syn_dir):
    with pytest.raises(ap.ApprovalError, match="limitations"):
        ap.new_approval(A, **SYN, now=NOW)
    with pytest.raises(ap.ApprovalError, match="limitations"):
        ap.new_approval(A, **SYN, now=NOW, accepted_limitations="0" * 16)
    approve(syn_dir, A)
    assert ap.status(syn_dir, A).status == ap.APPROVED
    assert ap.status(syn_dir, B).status == ap.MISSING  # an approval is per record


def test_synthetic_approval_does_not_count_in_an_unmarked_directory(tmp_path):
    d = tmp_path / "real-like"
    approve(d, M1)
    approve(d, A)
    assert ap.status(d, M1).status == ap.INVALID and ap.status(d, A).status == ap.INVALID
    assert "synthetic" in ap.status(d, A).detail


def test_revoke_and_restore(syn_dir):
    first = approve(syn_dir, A)
    ap.append(syn_dir, ap.new_revocation(A, first.record_id, "synthetic", now=NOW))
    assert ap.status(syn_dir, A).status == ap.REVOKED
    with pytest.raises(ap.ApprovalError, match="not a revoked approval"):
        approve(syn_dir, A, restores="APR-AGG-A-nothere")
    restored = approve(syn_dir, A, restores=first.record_id, evidence="SYN-restoration")
    state = ap.status(syn_dir, A)
    assert state.status == ap.APPROVED and state.reference == restored.record_id
    assert len(ap.events(syn_dir)) == 3  # nothing deleted


def test_record_changes_make_the_approval_incompatible(syn_dir):
    approve(syn_dir, A)
    assert ap.status(syn_dir, dataclasses.replace(A, version="1.1.0")).status == ap.INCOMPATIBLE
    assert (
        ap.status(syn_dir, dataclasses.replace(A, formula_version="A.2")).status == ap.INCOMPATIBLE
    )
    changed = dataclasses.replace(A, limitations=A.limitations + ("new limit",))
    assert ap.status(syn_dir, changed).status == ap.INCOMPATIBLE
    assert ap.status(syn_dir, dataclasses.replace(A, status="superseded")).status == ap.SUPERSEDED


# --- production gating -------------------------------------------------------------------------

PRICES = {"1": "20", "2": "40", "3": "60", "4": "80"}


def lookup(i):
    return PRICES.get(i["DeliveryInterval"])


def aligned(data_dir, case=fx.ORDINARY, policy=al.LATEST_RETRIEVED, basis=aa.ASSUMPTION):
    dam, rts = case
    approval = ap.status(data_dir, M1)
    res = aa.align_with_basis(basis, dam, rts, revision_policy=policy, approval=approval)
    ctx = aa.context(res.alignment_basis, res.dam_identity, policy, [dam], rts, approval)
    snap = aa.snapshot(res, ctx, "2026-10-13T18:00:00+00:00")
    return res, snap, approval


def run(data_dir, method="AGG-A", case=fx.ORDINARY, policy=al.LATEST_RETRIEVED, *, state="current",
        snap=True, basis=aa.ASSUMPTION, price_lookup=lookup):  # fmt: skip
    res, s, m1a = aligned(data_dir, case, policy, basis)
    rec = agp.RECORDS[0] if method == "AGG-A" else (B if method == "AGG-B" else None)
    return ag.aggregate(
        method,
        res,
        m1_approval=m1a,
        aggregation_approval=ap.status(data_dir, rec) if rec else None,
        alignment_snapshot=s if snap else None,
        alignment_snapshot_state=state if snap else None,
        price_lookup=price_lookup,
    )


@pytest.fixture
def both(syn_dir):
    approve(syn_dir, M1)
    approve(syn_dir, A)
    approve(syn_dir, B)
    return syn_dir


def test_complete_with_both_approvals(both):
    for method in ("AGG-A", "AGG-B"):
        res = run(both, method)
        assert res.status == ag.APPROVED_COMPLETE, res.blockers
        assert res.output == "50" and res.units == "$/MWh"  # (20+40+60+80)/4 by hand
        assert res.input_prices == ("20", "40", "60", "80") and res.blockers == ()
        assert res.banner == agp.LIMITATION_BANNER
        assert all(ok for _, ok, _ in res.validation)
    assert run(both, "AGG-B").duration_evidence["id"] == "DUR-15"


@pytest.mark.parametrize(
    "setup,expected",
    [
        ("no-approvals", ag.ALIGNMENT_APPROVAL_MISSING),
        ("m1-only", ag.APPROVAL_MISSING),
        ("aggregation-only", ag.ALIGNMENT_APPROVAL_MISSING),
        ("aggregation-revoked", ag.APPROVAL_MISSING),
        ("m1-revoked", ag.ALIGNMENT_APPROVAL_MISSING),
    ],
)
def test_approval_blockers(syn_dir, setup, expected):
    if setup in ("m1-only", "aggregation-revoked", "m1-revoked"):
        m1e = approve(syn_dir, M1)
    if setup in ("aggregation-only", "aggregation-revoked", "m1-revoked"):
        ae = approve(syn_dir, A)
    if setup == "aggregation-revoked":
        ap.append(syn_dir, ap.new_revocation(A, ae.record_id, "synthetic", now=NOW))
    if setup == "m1-revoked":
        ap.append(syn_dir, ap.new_revocation(M1, m1e.record_id, "synthetic", now=NOW))
    res = run(syn_dir)
    assert res.status == expected and res.output is None
    assert res.blockers and res.intervals == () or res.output is None


def test_authoritative_basis_never_aggregates(both):
    res = run(both, basis=aa.AUTHORITATIVE)
    assert res.status == ag.ALIGNMENT_APPROVAL_MISSING and res.output is None
    assert any("authoritative-only" in b for b in res.blockers)


def test_mismatched_approvals(both):
    res, s, m1a = aligned(both)
    other_m1 = ap.Approval(ap.APPROVED, "M1", "0.9.0", m1a.record, "older")
    out = ag.aggregate(
        "AGG-A",
        res,
        m1_approval=other_m1,
        aggregation_approval=ap.status(both, A),
        alignment_snapshot=s,
        alignment_snapshot_state="current",
        price_lookup=lookup,
    )
    assert out.status == ag.ALIGNMENT_APPROVAL_MISSING
    out = ag.aggregate(
        "AGG-B",
        res,
        m1_approval=m1a,
        aggregation_approval=ap.status(both, A),
        alignment_snapshot=s,
        alignment_snapshot_state="current",
        price_lookup=lookup,
    )
    assert out.status == ag.APPROVAL_MISSING  # AGG-A's approval never authorizes AGG-B


def test_incomplete_conflicting_and_unavailable_revisions(both):
    assert run(both, case=fx.MISSING_ONE).status == ag.ALIGNMENT_INCOMPLETE
    assert run(both, case=fx.BLANK_RT_PRICE).status == ag.ALIGNMENT_INCOMPLETE
    assert run(both, case=fx.DUPLICATE).status == ag.CONFLICTING_REVISIONS
    assert run(both, policy=al.FINAL).status == ag.REVISION_UNAVAILABLE
    missing_price = run(both, price_lookup=lambda i: None if i["DeliveryInterval"] == "3" else "1")
    assert missing_price.status == ag.ALIGNMENT_INCOMPLETE and missing_price.output is None


def test_stale_or_missing_alignment_snapshot(both):
    assert run(both, snap=False).status == ag.STALE_SNAPSHOT
    assert run(both, state="stale").status == ag.STALE_SNAPSHOT
    res, s, m1a = aligned(both)
    s = {**s, "selected_real_time": [{**x, "revision": 9} for x in s["selected_real_time"]]}
    out = ag.aggregate(
        "AGG-A",
        res,
        m1_approval=m1a,
        aggregation_approval=ap.status(both, A),
        alignment_snapshot=s,
        alignment_snapshot_state="current",
        price_lookup=lookup,
    )
    assert out.status == ag.STALE_SNAPSHOT and "differ" in " ".join(out.blockers)


def test_duration_unsupported_for_flag_y_without_fallback(both):
    res_b = run(both, "AGG-B", case=fx.FALL_REPEATED_Y)
    assert res_b.status == ag.DURATION_UNSUPPORTED and res_b.output is None
    assert not res_b.input_prices or res_b.output is None  # no 0.25 substituted, no mean shown
    res_a = run(both, "AGG-A", case=fx.FALL_REPEATED_Y)  # A needs no duration evidence
    assert res_a.status == ag.APPROVED_COMPLETE and res_a.output == "50"


def test_unsupported_methods(both):
    for method in ("energy-weighted-price", "settlement-amount", "hourly-anything"):
        res = run(both, method)
        assert res.status == ag.UNSUPPORTED_METHOD and res.output is None


def test_no_actual_output_with_synthetic_approvals_in_a_real_like_dir(tmp_path):
    d = tmp_path / "real-like"
    approve(d, M1)
    approve(d, A)
    res = run(d)
    assert res.status == ag.ALIGNMENT_APPROVAL_MISSING and res.output is None


# --- aggregation snapshots ---------------------------------------------------------------------


def test_aggregation_snapshot_invalidation(both):
    res = run(both)
    ctx = ag.context(res, "current")
    ag.record_snapshot(both, ag.snapshot(res, ctx, "2026-10-13T18:00:00+00:00"))
    key = ag.snapshot_key(ctx)
    [(snap, state, why)] = ag.snapshot_states(ag.snapshots(both), {key: ctx})
    assert (
        state == "current"
        and snap["output"] == "50"
        and snap["input_prices"] == ["20", "40", "60", "80"]
    )
    changes = {
        "alignment_snapshot": {**ctx, "alignment_snapshot": "aln-x:stale"},
        "intervals": {**ctx, "intervals": [["2", "N", 2, "SYN-RT-5-2-N-2"]]},
        "m1": {**ctx, "m1": "M1@1.1.0:x"},
        "m1_approval": {**ctx, "m1_approval": "revoked (APR-M1-x)"},
        "aggregation_approval": {**ctx, "aggregation_approval": "revoked (APR-AGG-A-x)"},
        "method": {**ctx, "method": "AGG-A@1.1.0:x"},
        "duration_evidence": {**ctx, "duration_evidence": "changed"},
        "formula_version": {**ctx, "formula_version": "A.2"},
        "validation_version": {**ctx, "validation_version": "99"},
    }
    for field, now in changes.items():
        now_key = ag.snapshot_key(now)
        states = ag.snapshot_states(ag.snapshots(both), {now_key: now, key: now})
        (_, state, why) = states[0]
        assert state == "stale" and f"{field} changed" in why, field
    ag.record_snapshot(both, ag.snapshot(res, ctx, "2026-10-13T19:00:00+00:00"))
    states = [s for _, s, _ in ag.snapshot_states(ag.snapshots(both), {key: ctx})]
    assert states == ["superseded", "current"] and len(ag.snapshots(both)) == 2


# --- guards --------------------------------------------------------------------------------------

AGG_MODULES = ("ercot/aggregation.py", "ercot/aggregation_policy.py", "aggregation_view.py")


def _identifiers(tree):
    out = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    out |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    out |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    out |= {
        a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments) for a in n.args + n.kwonlyargs
    }
    return out


def test_guard_no_spread_dart_settlement_or_trading_identifiers():
    banned = re.compile(
        r"spread|dart|pnl|profit|backtest|sharpe|trading_signal|da_minus|rt_minus", re.I
    )
    for path in SRC.rglob("*.py"):
        hits = [i for i in _identifiers(ast.parse(path.read_text("utf-8"))) if banned.search(i)]
        assert not hits, (path, hits)


def test_guard_aggregation_never_reads_day_ahead_prices():
    for rel in AGG_MODULES:
        tree = ast.parse((SRC / rel).read_text("utf-8"))
        imported = {
            a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names
        }
        assert "prices" not in imported, rel  # ercot.prices is the day-ahead module
        assert not re.search(
            r"np4-190|hour_ending\s*-|DASPP\s*-", (SRC / rel).read_text("utf-8"), re.I
        )


def test_guard_no_implicit_aggregation_or_finance_import():
    allowed = {"aggregation_view.py", "alignment_view.py", "cli.py"}
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel in AGG_MODULES:
            continue
        tree = ast.parse(path.read_text("utf-8"))
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        uses = {"aggregation", "aggregation_policy", "aggregation_view"} & names or any(
            m.endswith(("aggregation", "aggregation_policy", "aggregation_view")) for m in mods
        )
        if uses:
            assert path.name in allowed, rel


def _rendered_strings(tree):
    """String literals that can reach the page or a result: not docstrings, and not the
    prohibited-interpretations list (a list of readings that are ruled out)."""
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skip.add(id(first.value))
        if isinstance(node, ast.Assign) and any(
            getattr(tg, "id", "") == "PROHIBITED_INTERPRETATIONS" for tg in node.targets
        ):
            skip |= {id(n) for n in ast.walk(node.value)}
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
    ]


def test_guard_no_claim_that_the_summary_is_ercot_defined():
    claim = re.compile(r"ERCOT-defined|settlement price|final price|ERCOT price", re.I)
    negation = re.compile(r"\b(not|no|never|none|nor)\b", re.I)
    for rel in AGG_MODULES:
        for text in _rendered_strings(ast.parse((SRC / rel).read_text("utf-8"))):
            if claim.search(text):
                assert negation.search(text), (rel, text)
    assert "not an ERCOT-defined hourly settlement price" in agp.LIMITATION_BANNER
    for r in agp.RECORDS:
        assert not claim.search(r.output_name)


def test_guard_four_interval_and_clock_rules_cover_the_new_modules():
    for rel in AGG_MODULES:
        tree = ast.parse((SRC / rel).read_text("utf-8"))
        consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)]
        assert 4 not in consts and 0.25 not in consts, rel  # no hard-coded interval rule
        assert not {"astimezone", "ZoneInfo", "timedelta", "UTC"} & _identifiers(tree), rel


# --- CLI ----------------------------------------------------------------------------------------


def test_cli_aggregation_workflow(syn_dir, monkeypatch, capsys):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(syn_dir))
    base = ["--no-dotenv", "aggregation"]
    assert cli.main(base + ["list"]) == 0
    assert "approvable" in capsys.readouterr().out
    approve_args = base + [
        "approve", "AGG-A", "--version", "1.0.0", "--scope", A.scope_fingerprint(),
        "--accept-limitations", A.limitations_fingerprint(), "--reviewer", "Synthetic Reviewer",
        "--role", "synthetic", "--evidence", "SYN-cli", "--approved-on", "2026-10-01",
    ]  # fmt: skip
    assert cli.main(approve_args) == 0
    out = capsys.readouterr().out
    assert "Dry run" in out and "Synthetic Reviewer" not in out and not ap.path(syn_dir).exists()
    assert cli.main(approve_args + ["--execute"]) == 0
    assert ap.status(syn_dir, A).status == ap.APPROVED
    assert cli.main(base + ["status", "AGG-A"]) == 0
    assert "Synthetic Reviewer" not in capsys.readouterr().out  # identity not printed
    wrong = list(approve_args)
    wrong[wrong.index("--scope") + 1] = "0" * 16
    assert cli.main(wrong) == 1
    assert cli.main(base + ["show", "NOPE"]) == 1


# --- diagnostic page ---------------------------------------------------------------------------

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
    return at.run(timeout=40)


def test_page_shows_investigation_and_withholds_without_approvals(page_dir):
    at = _page(page_dir)
    assert not at.exception and not data_elements(at)
    text = _texts(at)
    assert agp.LIMITATION_BANNER in text and "Aggregation investigation" in [
        h.value for h in at.header
    ]
    assert "alignment_approval_missing" in text and "withheld" in text
    bench = next(t.value for t in at.table if "Example" in t.value.columns)
    assert "50 $/MWh" in list(bench["Result"]) and "65 $/MWh" in list(bench["Result"])
    assert "3500 $" in list(bench["Result"]) and "35 $/MWh" in list(bench["Result"])
    assert not (page_dir / "aggregation").exists()


def test_page_complete_under_synthetic_approvals(page_dir):
    (page_dir / ap.SYNTHETIC_MARKER).write_text("synthetic\n", "utf-8")
    approve(page_dir, M1)
    approve(page_dir, A)
    at = _page(page_dir, align_basis=aa.ASSUMPTION)
    assert "stale_snapshot" in _texts(at)  # no alignment snapshot yet
    at.button(key="align_snapshot").click().run(timeout=40)
    text = _texts(at)
    # fixture prices hour 3: 24.00, 24.25, 24.50, 24.75 -> 97.5 / 4 = 24.375
    assert "aggregation_approved_complete" in text and "24.375 \\$/MWh" in text
    # every "$" in rendered markdown is escaped, so nothing turns into LaTeX (browser finding)
    for el in list(at.success) + list(at.markdown) + list(at.warning) + list(at.info):
        assert not re.search(r"(?<!\\)\$", el.value), el.value
    assert agp.LIMITATION_BANNER in text and not data_elements(at)
    at.button(key="agg_snapshot").click().run(timeout=40)
    assert ag.snapshots(page_dir)[0]["output"] == "24.375"
    # a revised interval: alignment snapshot and aggregation snapshot both go stale, kept
    c = ErcotClient(transport=FakeRt(dict([interval_doc(D9, 3, 2, "8888", price="99.00")])),
                    sleep=lambda s: None, max_requests=4)  # fmt: skip
    rt.collect(rt.Selection(1, False), c, rt.store(page_dir))
    at = _page(page_dir, align_basis=aa.ASSUMPTION)
    text = _texts(at)
    # the alignment snapshot is stale, so the summary is withheld until recomputed
    assert "**stale_snapshot** — the summary is withheld." in text
    assert "aggregation_approved_complete" not in text
    states = next(t.value for t in at.table if "Output then" in t.value.columns)
    assert list(states["State now"]) == ["stale"] and len(ag.snapshots(page_dir)) == 1


def test_page_with_synthetic_approvals_in_unmarked_dir_withholds(page_dir):
    approve(page_dir, M1)
    approve(page_dir, A)
    at = _page(page_dir, align_basis=aa.ASSUMPTION)
    at.button(key="align_snapshot").click().run(timeout=40)
    text = _texts(at)
    assert "aggregation_approved_complete" not in text and "withheld" in text
