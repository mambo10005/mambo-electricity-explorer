"""Stage 23: assumption-governed alignment under M1 (offline, credential-free, SYNTHETIC).

Every approval below names a synthetic reviewer ("Synthetic Reviewer", evidence "SYN-…"); no
real approval is created. Label fixtures come from tests/alignment_fixtures.py (synthetic).
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import alignment_fixtures as fx
import pytest
from guards import data_elements
from price_fixtures import FakePrices, day_doc
from rt_price_fixtures import FakeRt, day_docs, interval_doc
from streamlit.testing.v1 import AppTest

from mambo_explorer import alignment_view, cli, routes
from mambo_explorer.ercot import alignment as al
from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot import assumed_alignment as aa
from mambo_explorer.ercot import m1_policy
from mambo_explorer.ercot import prices as px
from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.client import ErcotClient
from mambo_explorer.ercot.m1_policy import BANNER, M1

SRC = Path(__file__).resolve().parents[1] / "src" / "mambo_explorer"
LATEST, FIRST = al.LATEST_RETRIEVED, al.FIRST_RETRIEVED
NOW = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)
SYN = {
    "reviewer": "Synthetic Reviewer",
    "role": "synthetic test role",
    "evidence": "SYN-approval-note-1",
    "approved_on": "2026-10-01",
}


@pytest.fixture
def store_dir(tmp_path):
    return tmp_path / "data"


def approve(data_dir, record=M1, **kw):
    event = ap.new_approval(record, **{**SYN, **kw}, now=NOW)
    ap.append(data_dir, event)
    return event


def under(case, approval, policy=LATEST, **kw):
    dam, rts = case
    return aa.align_with_basis(
        aa.ASSUMPTION, dam, rts, revision_policy=policy, approval=approval, **kw
    )


# --- the assumption record ------------------------------------------------------------------


def test_m1_record_is_versioned_scoped_and_unresolved():
    assert (M1.id, M1.version, M1.official_status, M1.status) == (
        "M1",
        "1.0.0",
        "unresolved",
        "current",
    )
    assert M1.datasets == ("NP4-190-CD", "NP6-905-CD")
    (scope,) = M1.locations
    assert (scope.day_ahead_point, scope.day_ahead_location_type) == ("HB_NORTH", "hub")
    assert (scope.real_time_point, scope.real_time_type) == ("HB_NORTH", "HU")
    assert "not defined" in scope.evidence  # the HU association is observed, not official
    assert M1.flags == ("N", "Y") and M1.expected_intervals == ("1", "2", "3", "4")
    assert len(M1.unresolved_definitions) == 5 and M1.re_review_triggers
    assert {al.evidence(e).kind for e in M1.supporting_evidence} == {"official", "actual-file"}
    assert "not a reviewer approval" in M1.authorization
    assert "not attributable" in M1.reported_acceptance
    assert len(M1.scope_fingerprint()) == 16 and len(M1.schema_fingerprint()) == 16


def test_record_contains_no_reviewer_identity_or_date():
    text = json.dumps(dataclasses.asdict(M1), default=list)
    assert 'reviewer"' not in text and "approved_on" not in text
    assert not re.search(r"Synthetic|SYN-", text)


def test_stage22_authoritative_status_is_unchanged():
    assert al.accepted() is None
    assert al.candidate("M1").status == "partially-supported"


# --- approvals --------------------------------------------------------------------------------


def test_missing_approval_and_no_file_created(store_dir):
    state = ap.status(store_dir, M1)
    assert state.status == ap.MISSING and not state.active
    assert not store_dir.exists()


def test_approval_needs_every_attributable_field(store_dir):
    for field in ("reviewer", "role", "evidence"):
        with pytest.raises(ap.ApprovalError):
            ap.new_approval(M1, **{**SYN, field: None}, now=NOW)
    with pytest.raises(ap.ApprovalError, match="actual approval date"):
        ap.new_approval(M1, **{**SYN, "approved_on": None}, now=NOW)
    with pytest.raises(ap.ApprovalError, match="future"):
        ap.new_approval(M1, **{**SYN, "approved_on": "2026-12-01"}, now=NOW)
    with pytest.raises(ap.ApprovalError, match="credential"):
        ap.new_approval(M1, **{**SYN, "evidence": "token=abcdef"}, now=NOW)
    with pytest.raises(ap.ApprovalError, match="credential"):
        ap.new_approval(M1, **{**SYN, "evidence": "x" * 40}, now=NOW)


def test_valid_synthetic_approval_is_active(store_dir):
    event = approve(store_dir)
    state = ap.status(store_dir, M1)
    assert state.status == ap.APPROVED and state.reference == event.record_id
    assert "Synthetic Reviewer" in state.detail


def test_revoked_approval_blocks_and_nothing_is_deleted(store_dir):
    event = approve(store_dir)
    ap.append(store_dir, ap.new_revocation(M1, event.record_id, "synthetic revocation", now=NOW))
    assert ap.status(store_dir, M1).status == ap.REVOKED
    assert len(ap.events(store_dir)) == 2  # append-only
    with pytest.raises(ap.ApprovalError, match="no recorded approval"):
        ap.append(store_dir, ap.new_revocation(M1, "APR-M1-nothere", "x", now=NOW))


def test_later_approval_supersedes_earlier(store_dir):
    first = approve(store_dir)
    second = approve(store_dir, evidence="SYN-approval-note-2")
    assert ap.status(store_dir, M1).reference == second.record_id
    assert ap.superseded_records(store_dir, M1) == [first.record_id]


def test_version_scope_and_schema_mismatch_make_approval_incompatible(store_dir):
    approve(store_dir)
    v2 = dataclasses.replace(M1, version="1.1.0")
    assert ap.status(store_dir, v2).status == ap.INCOMPATIBLE
    wider = dataclasses.replace(
        M1,
        locations=M1.locations
        + (dataclasses.replace(M1.locations[0], day_ahead_point="HB_SOUTH"),),
    )
    assert ap.status(store_dir, wider).status == ap.INCOMPATIBLE
    schema = dataclasses.replace(M1, schema={**M1.schema, "real_time": {"header": ("changed",)}})
    assert schema.scope_fingerprint() != M1.scope_fingerprint()
    assert ap.status(store_dir, schema).status == ap.INCOMPATIBLE


def test_superseded_record_cannot_be_used(store_dir):
    approve(store_dir)
    old = dataclasses.replace(M1, status="superseded")
    assert ap.status(store_dir, old).status == ap.SUPERSEDED


def test_unreadable_record_file_is_invalid(store_dir):
    ap.path(store_dir).parent.mkdir(parents=True)
    ap.path(store_dir).write_text("{not json\n", "utf-8")
    assert ap.status(store_dir, M1).status == ap.INVALID


# --- activation gates -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "setup,expected",
    [
        ("missing", aa.APPROVAL_MISSING),
        ("revoked", aa.APPROVAL_REVOKED),
        ("superseded", aa.APPROVAL_SUPERSEDED),
        ("incompatible", aa.APPROVAL_INCOMPATIBLE),
    ],
)
def test_inactive_approval_prevents_assumption_alignment(store_dir, setup, expected):
    record = M1
    if setup != "missing":
        event = approve(store_dir)
    if setup == "revoked":
        ap.append(store_dir, ap.new_revocation(M1, event.record_id, "synthetic", now=NOW))
    if setup == "superseded":
        record = dataclasses.replace(M1, status="superseded")
    if setup == "incompatible":
        record = dataclasses.replace(M1, version="2.0.0")
    res = under(fx.ORDINARY, ap.status(store_dir, record), assumption=record)
    assert res.alignment_status == expected
    assert res.completeness_status == aa.NOT_EVALUATED and res.matched == () and res.banner is None


def test_no_approval_object_is_missing_not_guessed():
    res = under(fx.ORDINARY, None)
    assert res.alignment_status == aa.APPROVAL_MISSING


def test_unsupported_revision_policies_block_before_approval(store_dir):
    approve(store_dir)
    a = ap.status(store_dir, M1)
    for policy in (al.FINAL, al.LATEST_KNOWN_BEFORE):
        assert under(fx.ORDINARY, a, policy).alignment_status == al.UNAVAILABLE_REVISION
    assert under(fx.ORDINARY, a, "newest").alignment_status == al.INVALID_INPUT


def test_authoritative_mode_still_unsupported_even_with_an_approval(store_dir):
    approve(store_dir)
    res = aa.align_with_basis(
        aa.AUTHORITATIVE, *fx.ORDINARY, revision_policy=LATEST, approval=ap.status(store_dir, M1)
    )
    assert res.alignment_status == al.UNSUPPORTED_SEMANTICS
    assert res.assumption_id is None and res.banner is None and res.matched == ()


def test_unknown_basis_is_invalid():
    res = aa.align_with_basis("guess", *fx.ORDINARY, revision_policy=LATEST)
    assert res.alignment_status == al.INVALID_INPUT


# --- outcomes under M1 ------------------------------------------------------------------------


@pytest.fixture
def active(store_dir):
    approve(store_dir)
    return ap.status(store_dir, M1)


OUTCOMES = {
    "ORDINARY": (aa.COMPLETE_UNDER, aa.COMPLETE),
    "HOUR_24": (aa.COMPLETE_UNDER, aa.COMPLETE),
    "FALL_REPEATED_N": (aa.COMPLETE_UNDER, aa.COMPLETE),
    "FALL_REPEATED_Y": (aa.COMPLETE_UNDER, aa.COMPLETE),
    "CONFLICTING_REVISIONS": (aa.COMPLETE_UNDER, aa.COMPLETE),
    "MISSING_ONE": (aa.INCOMPLETE_UNDER, aa.INCOMPLETE),
    "BLANK_RT_PRICE": (aa.INCOMPLETE_UNDER, aa.INCOMPLETE),
    "DUPLICATE": (aa.CONFLICTING_REVISIONS, aa.INCOMPLETE),
    "MISSING_ALL_RT": (al.MISSING_REAL_TIME, aa.INCOMPLETE),
    "MISSING_DAM_PRICE": (al.MISSING_DAY_AHEAD, aa.INCOMPLETE),
    "DIFFERENT_FLAGS": (al.AMBIGUOUS_DST, aa.NOT_EVALUATED),
    "UNKNOWN_FLAG": (al.AMBIGUOUS_DST, aa.NOT_EVALUATED),
    "UNKNOWN_RT_FLAG": (al.AMBIGUOUS_DST, aa.NOT_EVALUATED),
    "MISMATCHED_DATE": (al.INCOMPATIBLE_IDENTITY, aa.NOT_EVALUATED),
    "MISMATCHED_POINT": (al.INCOMPATIBLE_IDENTITY, aa.NOT_EVALUATED),
    "MISMATCHED_TYPE": (al.INCOMPATIBLE_IDENTITY, aa.NOT_EVALUATED),
}


@pytest.mark.parametrize("name", sorted(OUTCOMES))
def test_outcomes_under_m1_expose_their_basis(active, name):
    res = under(getattr(fx, name), active)
    assert (res.alignment_status, res.completeness_status) == OUTCOMES[name], res.reasons
    assert res.alignment_basis == aa.ASSUMPTION
    assert (res.assumption_id, res.assumption_version) == ("M1", "1.0.0")
    assert res.approval_status == ap.APPROVED and res.approval_reference.startswith("APR-M1-")
    assert res.authoritative_semantics_status == "unresolved"
    assert res.banner == BANNER
    assert res.expected_intervals == ("1", "2", "3", "4")
    assert res.alignment_status != al.ALIGNED_COMPLETE  # never the bare Stage 22 status


def test_banner_text_is_exact():
    assert BANNER == (
        "Aligned under review-approved assumption M1. "
        "ERCOT report-label definitions remain unverified."
    )


def test_out_of_scope_point_is_rejected(active):
    res = under((fx.dam(point="HB_SOUTH"), fx.hour_of(point="HB_SOUTH")), active)
    assert res.alignment_status == aa.UNSUPPORTED_SCOPE and res.matched == ()
    res = under((fx.dam(typ="load zone"), fx.hour_of()), active)
    assert res.alignment_status == aa.UNSUPPORTED_SCOPE


def test_identities_keep_original_labels(active):
    res = under(fx.HOUR_24, active)
    assert res.dam_identity["HourEnding"] == "24:00" and res.dam_identity["DeliveryDate"] == fx.DAY
    assert {m["DeliveryHour"] for m in res.matched} == {"24"}
    assert {m["DeliveryDate"] for m in res.matched} == {fx.DAY}
    assert res.observed_intervals == ("1", "2", "3", "4")


def test_repeated_hour_flags_never_merge(active):
    n, y = under(fx.FALL_REPEATED_N, active), under(fx.FALL_REPEATED_Y, active)
    assert {m["DSTFlag"] for m in n.matched} == {"N"} and {m["DSTFlag"] for m in y.matched} == {"Y"}
    assert len(n.matched) == len(y.matched) == 4 and len(n.excluded) == 4


def test_revision_policies_apply_to_both_products(active):
    dam1, dam2 = fx.dam(rev=1), fx.dam(rev=2)
    rts = fx.hour_of() + [fx.rt("5", "2", rev=2)]
    latest = aa.align_with_basis(
        aa.ASSUMPTION, dam1, rts, revision_policy=LATEST, approval=active, dam_revisions=[dam2]
    )
    first = aa.align_with_basis(
        aa.ASSUMPTION, dam1, rts, revision_policy=FIRST, approval=active, dam_revisions=[dam2]
    )
    assert latest.dam_revision["revision"] == 2 and first.dam_revision["revision"] == 1
    pick = {
        r.revision_policy: {m["DeliveryInterval"]: m["revision"] for m in r.matched}
        for r in (latest, first)
    }
    assert pick[LATEST]["2"] == 2 and pick[FIRST]["2"] == 1


def test_equal_revision_numbers_are_a_conflict_not_a_choice(active):
    res = under(fx.DUPLICATE, active)
    assert res.alignment_status == aa.CONFLICTING_REVISIONS and res.duplicate_intervals
    assert "3" not in res.observed_intervals


# --- snapshots --------------------------------------------------------------------------------


def _ctx(res, stored_dam, stored_rt, approval, record=M1):
    return aa.context(
        res.alignment_basis,
        res.dam_identity,
        res.revision_policy,
        stored_dam,
        stored_rt,
        approval,
        record,
    )


def test_snapshot_records_revisions_and_goes_stale_on_every_input(store_dir, active):
    dam, rts = fx.ORDINARY
    res = under(fx.ORDINARY, active)
    ctx = _ctx(res, [dam], rts, active)
    snap = aa.snapshot(res, ctx, "2026-10-13T18:00:00+00:00")
    assert [s["revision"] for s in snap["selected_real_time"]] == [1, 1, 1, 1]
    assert snap["dam_revision"]["revision"] == 1 and snap["approval_reference"] == active.reference
    aa.record_snapshot(store_dir, snap)
    key = aa.snapshot_key(ctx)
    [(_, state, why)] = aa.snapshot_states(aa.snapshots(store_dir), {key: ctx})
    assert state == "current" and why == []

    changes = {
        "inputs": _ctx(res, [dam], rts + [fx.rt("5", "2", rev=2)], active),
        "approval": _ctx(
            res, [dam], rts, ap.Approval(ap.REVOKED, "M1", "1.0.0", active.record, "x")
        ),
        "assumption": _ctx(res, [dam], rts, active, dataclasses.replace(M1, version="1.1.0")),
    }
    for field, now in changes.items():
        [(_, state, why)] = aa.snapshot_states(aa.snapshots(store_dir), {key: now})
        assert state == "stale" and f"{field} changed" in why
    bumped = {**ctx, "validation_version": "99"}
    [(_, state, why)] = aa.snapshot_states(aa.snapshots(store_dir), {key: bumped})
    assert state == "stale" and "validation_version changed" in why


def test_policy_change_is_a_different_snapshot_key(active):
    dam, rts = fx.ORDINARY
    a = _ctx(under(fx.ORDINARY, active), [dam], rts, active)
    b = _ctx(under(fx.ORDINARY, active, FIRST), [dam], rts, active)
    assert aa.snapshot_key(a) != aa.snapshot_key(b)


def test_old_snapshots_are_superseded_never_deleted(store_dir, active):
    dam, rts = fx.ORDINARY
    res = under(fx.ORDINARY, active)
    ctx = _ctx(res, [dam], rts, active)
    for stamp in ("2026-10-13T18:00:00+00:00", "2026-10-13T19:00:00+00:00"):
        aa.record_snapshot(store_dir, aa.snapshot(res, ctx, stamp))
    states = [
        s for _, s, _ in aa.snapshot_states(aa.snapshots(store_dir), {aa.snapshot_key(ctx): ctx})
    ]
    assert states == ["superseded", "current"] and len(aa.snapshots(store_dir)) == 2


# --- no aggregation, spread, UTC, or Finance import -----------------------------------------


def test_results_carry_no_price_values(active):
    res = under(fx.CONFLICTING_REVISIONS, active)

    def walk(x):
        assert not isinstance(x, float), x
        if isinstance(x, dict):
            for k, v in x.items():
                assert not re.search(r"spread|dart|avg|mean|utc|value", str(k), re.I), k
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    walk(aa.as_dict(res))


def test_guard_no_finance_import_of_alignment_or_actual_prices():
    finance = [
        "finance.py", "settlement.py", "settlement_ui.py", "basis.py", "basis_ui.py", "shape.py",
        "shape_ui.py",
    ]  # fmt: skip
    for rel in finance:
        tree = ast.parse((SRC / rel).read_text("utf-8"))
        mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
        }
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert not {"alignment", "assumed_alignment", "m1_policy", "approvals"} & names, rel
        assert not any("alignment" in m or "rt_prices" in m for m in mods), rel


def test_guard_approvals_module_converts_no_labels():
    tree = ast.parse((SRC / "ercot/approvals.py").read_text("utf-8"))
    calls = {
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "astimezone" in calls  # only for its own recording time
    assert not {"strptime", "tz_convert", "localize"} & calls


# --- CLI workflow -------------------------------------------------------------------------------


def test_cli_approve_is_dry_run_unless_execute(store_dir, monkeypatch, capsys):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(store_dir))
    args = ["--no-dotenv", "assumption", "approve", "--reviewer", "Synthetic Reviewer", "--role",
            "synthetic", "--evidence", "SYN-cli", "--approved-on", "2026-10-01"]  # fmt: skip
    assert cli.main(args) == 0
    assert "Dry run" in capsys.readouterr().out and not ap.path(store_dir).exists()
    assert cli.main(args + ["--execute"]) == 0
    assert ap.status(store_dir, M1).status == ap.APPROVED
    rid = ap.status(store_dir, M1).reference
    assert (
        cli.main(
            ["--no-dotenv", "assumption", "revoke", "--record", rid, "--reason", "syn", "--execute"]
        )
        == 0
    )
    assert ap.status(store_dir, M1).status == ap.REVOKED
    assert cli.main(["--no-dotenv", "assumption", "approve", "--reviewer", "X"]) == 1


def test_cli_status_and_show(store_dir, monkeypatch, capsys):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(store_dir))
    assert cli.main(["--no-dotenv", "assumption", "status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["approval_status"] == "missing" and out["official_semantics"] == "unresolved"
    assert cli.main(["--no-dotenv", "assumption", "show"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["scope_fingerprint"] == M1.scope_fingerprint() and shown["version"] == "1.0.0"
    assert not store_dir.exists()


# --- diagnostic page ------------------------------------------------------------------------------

EXPLORE = "from mambo_explorer.pages import render_page\nrender_page('explore')\n"
D9 = date(2026, 3, 9)  # synthetic store date (fixtures, not ERCOT data)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    return path


def _fill(data_dir, rt_docs):
    c = ErcotClient(
        transport=FakePrices(dict([day_doc(D9, "501")])), sleep=lambda s: None, max_requests=6
    )
    px.collect(px.Selection(latest=1), c, px.store(data_dir))
    c = ErcotClient(transport=FakeRt(rt_docs), sleep=lambda s: None, max_requests=16)
    rt.collect(rt.Selection(12, False), c, rt.store(data_dir))


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return "\n".join(parts)


def _page(data_dir, hour_ending="03:00", **state):
    dam, _ = alignment_view.load_day(data_dir, "03/09/2026")
    at = AppTest.from_string(EXPLORE)
    at.session_state["explore_source"] = "ercot-alignment"
    at.session_state["align_hour"] = next(o.hour for o in dam if o.hour.hour_ending == hour_ending)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run(timeout=30)


def test_page_defaults_to_authoritative_and_shows_pending_approval(data_dir):
    _fill(data_dir, day_docs(D9, hours=(3,)))
    at = _page(data_dir)
    assert not at.exception and not data_elements(at)
    assert at.radio(key="align_basis").value == aa.AUTHORITATIVE
    text = _texts(at)
    assert "unsupported_semantics" in text and BANNER not in text
    assert "Approval status" in str([t.value for t in at.table]) and "missing" in text
    assert "Unresolved official definitions" in text and "not a reviewer approval" in text


def test_selecting_m1_without_approval_does_not_align(data_dir):
    _fill(data_dir, day_docs(D9, hours=(3,)))
    at = _page(data_dir, align_basis=aa.ASSUMPTION)
    text = _texts(at)
    assert "approval_missing" in text and BANNER not in text


def test_selecting_m1_with_synthetic_approval_aligns_with_banner(data_dir):
    _fill(data_dir, day_docs(D9, hours=(3,)))
    approve(data_dir)
    at = _page(data_dir, align_basis=aa.ASSUMPTION)
    assert not at.exception and not data_elements(at)
    text = _texts(at)
    assert BANNER in text and aa.COMPLETE_UNDER in text
    assert "complete_under_assumption" in text and "unresolved" in text
    viewer = next(
        t.value
        for t in at.table
        if list(t.value.columns) == ["Interval", "Found", "Revision", "Document"]
    )
    assert list(viewer["Found"]) == ["yes"] * 4
    # incomplete hour
    at = _page(data_dir, "04:00", align_basis=aa.ASSUMPTION)
    assert "missing_real_time" in _texts(at) and BANNER in _texts(at)


def test_revoked_approval_on_the_page(data_dir):
    _fill(data_dir, day_docs(D9, hours=(3,)))
    event = approve(data_dir)
    ap.append(data_dir, ap.new_revocation(M1, event.record_id, "synthetic", now=NOW))
    at = _page(data_dir, align_basis=aa.ASSUMPTION)
    assert "approval_revoked" in _texts(at) and BANNER not in _texts(at)


def test_snapshot_button_records_and_reports_state(data_dir):
    docs = day_docs(D9, hours=(3,))
    _fill(data_dir, docs)
    approve(data_dir)
    at = _page(data_dir, align_basis=aa.ASSUMPTION)
    at.button(key="align_snapshot").click().run(timeout=30)
    assert len(aa.snapshots(data_dir)) == 1
    states = next(t.value for t in at.table if "State now" in t.value.columns)
    assert list(states["State now"]) == ["current"]
    # a revised interval makes the recorded snapshot stale (kept, not deleted)
    c = ErcotClient(
        transport=FakeRt(dict([interval_doc(D9, 3, 2, "8888", price="99.00")])),
        sleep=lambda s: None,
        max_requests=4,
    )
    rt.collect(rt.Selection(1, False), c, rt.store(data_dir))
    at = _page(data_dir, align_basis=aa.ASSUMPTION)
    states = next(t.value for t in at.table if "State now" in t.value.columns)
    assert list(states["State now"]) == ["stale"] and "inputs changed" in states["Why"][0]


def test_m1_policy_has_no_clock_or_utc_code():
    tree = ast.parse((SRC / "ercot/m1_policy.py").read_text("utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"datetime", "UTC", "timedelta", "ZoneInfo"}
    assert m1_policy.RECORDS == (M1,)
