"""Stage 26: local governance of M1, AGG-A/B, CMP-A/B (offline, credential-free, SYNTHETIC).

Every reviewer here is "Synthetic Reviewer"; every data directory is temporary and marked
synthetic unless a test checks the unmarked case. Nothing touches the real data directory.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from guards import data_elements
from streamlit.testing.v1 import AppTest

from mambo_explorer import cli, routes, system_health
from mambo_explorer.ercot import aggregation as ag
from mambo_explorer.ercot import aggregation_policy as agp
from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot import comparison as cmp
from mambo_explorer.ercot import comparison_policy as cmpp
from mambo_explorer.ercot import governance as gv
from mambo_explorer.ercot.m1_policy import M1

SRC = Path(__file__).resolve().parents[1] / "src" / "mambo_explorer"
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
WHO = {"reviewer": "Synthetic Reviewer", "role": "synthetic test role"}
HEALTH = "from mambo_explorer.pages import render_page\nrender_page('system-health')\n"


@pytest.fixture
def syn_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / ap.SYNTHETIC_MARKER).write_text("synthetic\n", "utf-8")
    return d


def approve(data_dir, rid, *, evidence="SYN-note", itemized=True, verified=None, restores=None):
    rec = gv.record(rid)
    fp = getattr(rec, "limitations_fingerprint", None)
    event = ap.new_approval(
        rec,
        **WHO,
        evidence=evidence,
        approved_on="2026-10-01",
        accepted_limitations=fp() if fp else None,
        rationale="synthetic rationale",
        acknowledged_limitations=list(gv.limitation_ids(rid)) if itemized else None,
        approved_scope="HB_NORTH",
        re_review_triggers=list(rec.re_review_triggers),
        evidence_verification_note=verified,
        restores=restores,
        now=NOW,
        synthetic=True,
    )
    if itemized:
        event = ap.Event(**{**ap.asdict(event), "limitations_version": gv.limitations_version(rid)})
    ap.append(data_dir, event)
    return event


def setting(data_dir, kind, value, now=NOW):
    ev = gv.new_setting(
        kind,
        value,
        operator="Synthetic Operator",
        role="synthetic operator",
        decided_on="2026-10-01",
        rationale="synthetic",
        now=now,
    )
    gv.append_setting(data_dir, ev)
    return ev


def decide(data_dir, rid, kind, **kw):
    ev = ap.new_decision(
        gv.record(rid),
        kind,
        **WHO,
        decided_on="2026-10-02",
        rationale="synthetic rationale",
        now=NOW,
        synthetic=True,
        **kw,
    )
    ap.append(data_dir, ev)
    return ev


# --- review packages --------------------------------------------------------------------------


@pytest.mark.parametrize("rid", list(gv.RECORDS))
def test_review_package_is_complete_and_names_no_reviewer(syn_dir, rid):
    pkg = gv.review_package(syn_dir, rid)
    for key in (
        "id",
        "version",
        "rule_or_formula",
        "scope",
        "dependencies",
        "facts",
        "authoritative_evidence",
        "empirical_evidence",
        "project_assumptions",
        "unresolved_semantics",
        "allowed_uses",
        "prohibited_uses",
        "limitations",
        "validation_evidence",
        "known_failure_modes",
        "re_review_triggers",
        "approval_status",
        "state",
        "activation",
    ):
        assert key in pkg, key
    assert pkg["state"] == gv.MISSING and pkg["activation"] == "inactive"
    assert "Synthetic" not in json.dumps(pkg)
    assert all(x["id"].startswith(rid) for x in pkg["limitations"])


def test_packages_state_the_required_facts():
    m1 = " ".join(gv.FACTS["M1"])
    for phrase in (
        "HB_NORTH only",
        "NP4-190-CD",
        "NP6-905-CD",
        "same numeric hour",
        "verbatim DSTFlag",
        "1 through 4",
        "Hour 24",
        "repeated fall hour",
        "not officially defined",
        "HU",
    ):
        assert phrase in m1, phrase
    a = " ".join(gv.FACTS["AGG-A"])
    assert "(P1 + P2 + P3 + P4) / 4" in a and "credit-risk" in a and "equal weight" in a
    b = " ".join(gv.FACTS["AGG-B"])
    assert "equals AGG-A" in b and "duration evidence" in b and "not an energy-weighted" in b
    ca = " ".join(gv.FACTS["CMP-A"])
    assert "RT analytical summary minus DAM SPP" in ca and "not DART" in ca
    cb = " ".join(gv.FACTS["CMP-B"])
    assert "exact sign reversal" in cb and "not be simultaneously active" in cb


def test_limitations_are_itemized_versioned_and_specific():
    assert [x.id for x in gv.LIMITATIONS["M1"]] == ["M1-L1", "M1-L2", "M1-L3", "M1-L4"]
    assert gv.limitations_version("M1") != gv.limitations_version("CMP-A")
    assert len(gv.limitations_version("AGG-B")) == 16
    texts = " ".join(x.text for x in gv.LIMITATIONS["CMP-B"])
    assert "exact reversal" in texts and "not be operationally active together" in texts


# --- acknowledgment ---------------------------------------------------------------------------


def test_acknowledgment_must_name_every_limitation():
    assert gv.check_acknowledgment("M1", ["M1-L1", "M1-L2", "M1-L3", "M1-L4"]) == gv.limitation_ids(
        "M1"
    )
    with pytest.raises(gv.GovernanceError, match="missing"):
        gv.check_acknowledgment("M1", ["M1-L1"])
    with pytest.raises(gv.GovernanceError, match="unknown"):
        gv.check_acknowledgment("M1", list(gv.limitation_ids("M1")) + ["AGG-A-L1"])
    with pytest.raises(gv.GovernanceError, match="generic"):
        gv.check_acknowledgment("M1", ["all"])
    with pytest.raises(gv.GovernanceError):
        gv.check_acknowledgment("M1", [])


def test_changed_limitations_force_re_review(syn_dir, monkeypatch):
    approve(syn_dir, "M1")
    assert gv.states(syn_dir)["M1"].state == gv.ACTIVE
    changed = gv.LIMITATIONS["M1"] + (gv.Limitation("M1-L5", "a new material limitation"),)
    monkeypatch.setitem(gv.LIMITATIONS, "M1", changed)
    st = gv.states(syn_dir)["M1"]
    assert st.state == gv.RE_REVIEW_REQUIRED and st.activation == "inactive"
    assert any("not the current version" in b for b in st.blockers)


def test_fingerprint_only_approvals_stay_valid_but_are_labelled(syn_dir):
    approve(syn_dir, "AGG-A", itemized=False)
    st = gv.states(syn_dir)["AGG-A"]
    assert st.approval_status == ap.APPROVED and st.acknowledgment == "fingerprint-only"


# --- decisions --------------------------------------------------------------------------------


def test_decision_fields_are_required_and_never_invented():
    with pytest.raises(ap.ApprovalError, match="issue"):
        ap.new_decision(
            M1, ap.KIND_REJECTION, **WHO, decided_on="2026-10-02", rationale="x", now=NOW
        )
    with pytest.raises(ap.ApprovalError, match="rationale"):
        ap.new_decision(
            M1, ap.KIND_REJECTION, **WHO, decided_on="2026-10-02", rationale="", issue="i", now=NOW
        )
    with pytest.raises(ap.ApprovalError, match="replacement"):
        ap.new_decision(
            M1, ap.KIND_SUPERSESSION, **WHO, decided_on="2026-10-02", rationale="r", now=NOW
        )
    with pytest.raises(ap.ApprovalError, match="future"):
        ap.new_decision(
            M1, ap.KIND_NO_DECISION, **WHO, decided_on="2027-01-01", rationale="r", now=NOW
        )
    with pytest.raises(ap.ApprovalError, match="effective_on"):
        ap.new_revocation(M1, "APR-x", "why", now=NOW, effective_on="soon")
    with pytest.raises(ap.ApprovalError, match="credential"):
        ap.new_decision(
            M1,
            ap.KIND_REJECTION,
            **WHO,
            decided_on="2026-10-02",
            rationale="token=abc",
            issue="i",
            now=NOW,
        )


def test_reject_request_revision_no_decision_supersede_states(syn_dir):
    decide(syn_dir, "AGG-A", ap.KIND_NO_DECISION)
    assert gv.states(syn_dir)["AGG-A"].state == gv.UNDER_REVIEW
    decide(syn_dir, "AGG-A", ap.KIND_REVISION_REQUEST, issue="formula wording unclear")
    assert gv.states(syn_dir)["AGG-A"].state == gv.REVISION_REQUESTED
    decide(syn_dir, "AGG-A", ap.KIND_REJECTION, issue="not wanted")
    st = gv.states(syn_dir)["AGG-A"]
    assert st.state == gv.REJECTED and "not wanted" in st.detail
    approve(syn_dir, "AGG-A")  # a later approval replaces the rejection (events kept)
    assert gv.states(syn_dir)["AGG-A"].approval_status == ap.APPROVED
    decide(
        syn_dir,
        "AGG-A",
        ap.KIND_SUPERSESSION,
        replacement_id="AGG-A",
        replacement_version="1.1.0",
        migration="re-approve under 1.1.0; snapshots stale",
    )
    st = gv.states(syn_dir)["AGG-A"]
    assert st.state == gv.SUPERSEDED and "1.1.0" in st.detail
    assert len(ap.events(syn_dir)) == 5  # append-only


def test_revocation_requires_attribution_and_effective_date_via_cli(syn_dir, monkeypatch, capsys):
    e = approve(syn_dir, "M1")
    monkeypatch.setenv("MAMBO_DATA_DIR", str(syn_dir))
    base = [
        "--no-dotenv",
        "governance",
        "revoke",
        "M1",
        "--record",
        e.record_id,
        "--reviewer",
        "Synthetic Reviewer",
        "--role",
        "synthetic",
        "--date",
        "2026-10-03",
        "--rationale",
        "synthetic revocation",
    ]
    assert cli.main(base) == 1 and "effective-on" in capsys.readouterr().err
    assert cli.main(base + ["--effective-on", "2026-10-03"]) == 0
    assert "Preview" in capsys.readouterr().out and gv.states(syn_dir)["M1"].state == gv.ACTIVE
    assert cli.main(base + ["--effective-on", "2026-10-03", "--execute"]) == 0
    assert gv.states(syn_dir)["M1"].state == gv.REVOKED
    rev = ap.events(syn_dir)[-1]
    assert (
        rev.kind == ap.KIND_REVOCATION
        and rev.effective_on == "2026-10-03"
        and rev.role == "synthetic"
    )


# --- evidence ---------------------------------------------------------------------------------


def test_evidence_metadata_path_vs_reference_and_availability(syn_dir, tmp_path):
    doc = tmp_path / "review-note.md"
    doc.write_text("synthetic review note\n", "utf-8")
    e = approve(syn_dir, "M1", evidence=str(doc))
    assert e.evidence_kind == ap.EVIDENCE_PATH and e.evidence_available_locally
    assert len(e.evidence_checksum) == 16 and e.evidence_verified is None
    assert gv.states(syn_dir)["M1"].evidence_state == "available"
    doc.unlink()
    st = gv.states(syn_dir)["M1"]
    assert st.evidence_state == gv.EVIDENCE_UNAVAILABLE and st.state == gv.ACTIVE  # preserved
    r = approve(syn_dir, "AGG-A", evidence="meeting notes 2026-10-01, item 3")
    assert r.evidence_kind == ap.EVIDENCE_REFERENCE and r.evidence_available_locally is False
    assert gv.states(syn_dir)["AGG-A"].evidence_state == "reference-only"
    v = approve(syn_dir, "AGG-B", evidence="ticket-42", verified="opened the ticket and read it")
    assert v.evidence_verified is True


# --- dependency graph, activation, single convention ------------------------------------------


def test_dependency_graph():
    assert gv.DEPENDENCIES["CMP-A"] == ("M1", ("AGG-A", "AGG-B")) == gv.DEPENDENCIES["CMP-B"]
    assert gv.DEPENDENCIES["AGG-A"] == gv.DEPENDENCIES["AGG-B"] == ("M1",)
    assert gv.downstream("M1") == ("AGG-A", "AGG-B", "CMP-A", "CMP-B")
    assert gv.downstream("AGG-A") == ("CMP-A", "CMP-B") and gv.downstream("CMP-A") == ()


def test_approved_before_dependencies_is_labelled_not_activated(syn_dir):
    approve(syn_dir, "CMP-A")
    st = gv.states(syn_dir)["CMP-A"]
    assert st.approval_status == ap.APPROVED and st.activation == gv.INACTIVE_DEPS
    assert st.state == gv.APPROVED_INACTIVE
    approve(syn_dir, "M1")
    approve(syn_dir, "AGG-A")
    assert gv.states(syn_dir)["CMP-A"].activation == gv.INACTIVE_DEPS  # still: no settings
    setting(syn_dir, gv.SET_AGGREGATION, "AGG-A")
    assert gv.states(syn_dir)["AGG-A"].state == gv.ACTIVE
    st = gv.states(syn_dir)["CMP-A"]
    assert st.activation == "inactive" and "not the selected" in " ".join(st.blockers)
    setting(syn_dir, gv.SET_CONVENTION, "CMP-A")
    st = gv.states(syn_dir)["CMP-A"]
    assert "no governed revision policy" in " ".join(st.blockers)
    setting(syn_dir, gv.SET_REVISION_POLICY, "latest-retrieved")
    assert gv.states(syn_dir)["CMP-A"].state == gv.ACTIVE
    active = gv.active_set(syn_dir)
    assert (active["m1"], active["aggregation"], active["convention"]) == ("M1", "AGG-A", "CMP-A")


def test_single_active_convention_and_single_method(syn_dir):
    for rid in ("M1", "AGG-A", "AGG-B", "CMP-A", "CMP-B"):
        approve(syn_dir, rid)
    setting(syn_dir, gv.SET_AGGREGATION, "AGG-A")
    setting(syn_dir, gv.SET_CONVENTION, "CMP-A")
    setting(syn_dir, gv.SET_REVISION_POLICY, "latest-retrieved")
    st = gv.states(syn_dir)
    assert st["CMP-A"].state == gv.ACTIVE and st["CMP-B"].state == gv.APPROVED_INACTIVE
    assert st["AGG-A"].state == gv.ACTIVE and st["AGG-B"].state == gv.APPROVED_INACTIVE
    setting(syn_dir, gv.SET_CONVENTION, "CMP-B", now=NOW.replace(hour=10))
    st = gv.states(syn_dir)
    assert st["CMP-B"].state == gv.ACTIVE and st["CMP-A"].state == gv.APPROVED_INACTIVE
    assert len(gv.setting_events(syn_dir)) == 4  # the earlier setting is kept


def test_settings_require_attribution_rationale_and_valid_values():
    with pytest.raises(gv.GovernanceError, match="must be one of"):
        gv.new_setting(
            gv.SET_CONVENTION,
            "DART",
            operator="o",
            role="r",
            decided_on="2026-10-01",
            rationale="x",
            now=NOW,
        )
    with pytest.raises(gv.GovernanceError, match="rationale"):
        gv.new_setting(
            gv.SET_CONVENTION,
            "CMP-A",
            operator="o",
            role="r",
            decided_on="2026-10-01",
            rationale="",
            now=NOW,
        )
    with pytest.raises(gv.GovernanceError, match="operator"):
        gv.new_setting(
            gv.SET_REVISION_POLICY,
            "latest-retrieved",
            operator="",
            role="r",
            decided_on="2026-10-01",
            rationale="x",
            now=NOW,
        )
    with pytest.raises(gv.GovernanceError, match="one of"):
        gv.new_setting(
            gv.SET_REVISION_POLICY,
            "final",
            operator="o",
            role="r",
            decided_on="2026-10-01",
            rationale="x",
            now=NOW,
        )


def test_no_default_convention_method_or_policy(syn_dir):
    s = gv.current_settings(syn_dir)
    assert s["active_comparison_convention"] is None and s["active_aggregation_method"] is None
    assert s["revision_policy"] is None
    assert not gv.settings_path(syn_dir).exists()


# --- production gating and staleness ----------------------------------------------------------

PRICES = {"1": "20", "2": "40", "3": "60", "4": "80"}


def _hour(syn_dir, policy="latest-retrieved"):
    import alignment_fixtures as fx

    from mambo_explorer.ercot import assumed_alignment as aa

    dam, rts = fx.ORDINARY
    m1a = ap.status(syn_dir, M1)
    alignment = aa.align_with_basis(aa.ASSUMPTION, dam, rts, revision_policy=policy, approval=m1a)
    ctx = aa.context(
        aa.ASSUMPTION,
        alignment.dam_identity,
        policy,
        [dam],
        rts,
        m1a,
        governance=gv.current_settings(syn_dir),
    )
    return alignment, aa.snapshot(alignment, ctx, "2026-10-14T09:00:00+00:00"), m1a


def test_changing_governance_withholds_and_marks_snapshots_stale(syn_dir):
    for rid in ("M1", "AGG-A", "AGG-B", "CMP-A"):
        approve(syn_dir, rid)
    setting(syn_dir, gv.SET_AGGREGATION, "AGG-A")
    setting(syn_dir, gv.SET_CONVENTION, "CMP-A")
    setting(syn_dir, gv.SET_REVISION_POLICY, "latest-retrieved")
    gov = gv.current_settings(syn_dir)
    alignment, asnap, m1a = _hour(syn_dir)
    agg = ag.aggregate(
        "AGG-A",
        alignment,
        m1_approval=m1a,
        aggregation_approval=ap.status(syn_dir, agp.AGG_A),
        alignment_snapshot=asnap,
        alignment_snapshot_state="current",
        price_lookup=lambda i: PRICES[i["DeliveryInterval"]],
        governance=gov,
    )
    assert agg.status == ag.APPROVED_COMPLETE and agg.output == "50"
    actx = ag.context(agg, "current", governance=gov)
    ag.record_snapshot(syn_dir, ag.snapshot(agg, actx, "2026-10-14T09:01:00+00:00"))
    assert gv.stale_downstream(syn_dir)["aggregation"] == {"total": 1, "stale": 0}
    # switching the active method: AGG-A withheld (no fallback), AGG-B's turn only if complete
    setting(syn_dir, gv.SET_AGGREGATION, "AGG-B", now=NOW.replace(hour=10))
    gov2 = gv.current_settings(syn_dir)
    again = ag.aggregate(
        "AGG-A",
        alignment,
        m1_approval=m1a,
        aggregation_approval=ap.status(syn_dir, agp.AGG_A),
        alignment_snapshot=asnap,
        alignment_snapshot_state="current",
        price_lookup=lambda i: PRICES[i["DeliveryInterval"]],
        governance=gov2,
    )
    assert again.status == ag.APPROVAL_MISSING and again.output is None
    assert gv.stale_downstream(syn_dir)["aggregation"] == {"total": 1, "stale": 1}
    assert len(ag.snapshots(syn_dir)) == 1  # never deleted
    # changing the revision policy marks alignment snapshots stale too
    from mambo_explorer.ercot import assumed_alignment as aa

    aa.record_snapshot(syn_dir, asnap)
    assert gv.stale_downstream(syn_dir)["alignment"]["stale"] == 0
    setting(syn_dir, gv.SET_REVISION_POLICY, "first-retrieved", now=NOW.replace(hour=11))
    assert gv.stale_downstream(syn_dir)["alignment"]["stale"] == 1


def test_comparison_withheld_under_other_convention_signs_never_reversed(syn_dir):
    for rid in ("M1", "AGG-A", "CMP-A", "CMP-B"):
        approve(syn_dir, rid)
    setting(syn_dir, gv.SET_AGGREGATION, "AGG-A")
    setting(syn_dir, gv.SET_CONVENTION, "CMP-B")
    setting(syn_dir, gv.SET_REVISION_POLICY, "latest-retrieved")
    gov = gv.current_settings(syn_dir)
    alignment, asnap, m1a = _hour(syn_dir)
    agg = ag.aggregate(
        "AGG-A",
        alignment,
        m1_approval=m1a,
        aggregation_approval=ap.status(syn_dir, agp.AGG_A),
        alignment_snapshot=asnap,
        alignment_snapshot_state="current",
        price_lookup=lambda i: PRICES[i["DeliveryInterval"]],
        governance=gov,
    )
    gsnap = ag.snapshot(
        agg, ag.context(agg, "current", governance=gov), "2026-10-14T09:02:00+00:00"
    )
    dam = cmp.DamInput(alignment.dam_identity, 1, "SYN-DAM-1", "30", "$/MWh", "p", "r")
    common = dict(
        mode=cmp.GOVERNED,
        alignment=alignment,
        aggregation=agg,
        aggregation_snapshot=gsnap,
        aggregation_snapshot_state="current",
        dam=dam,
        m1_approval=m1a,
        aggregation_approval=ap.status(syn_dir, agp.AGG_A),
        governance=gov,
    )
    a = cmp.compare("CMP-A", comparison_approval=ap.status(syn_dir, cmpp.CMP_A), **common)
    b = cmp.compare("CMP-B", comparison_approval=ap.status(syn_dir, cmpp.CMP_B), **common)
    assert a.status == cmp.COMPARISON_APPROVAL_MISSING and a.output is None
    assert b.status == cmp.APPROVED_COMPLETE and b.output == "-20"  # 30 − 50, never flipped
    assert "governed setting is CMP-B" in " ".join(a.blockers)


# --- audit log and atomic writes --------------------------------------------------------------


def test_audit_log_is_append_only_and_names_no_reviewer(syn_dir, monkeypatch, capsys):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(syn_dir))
    base = ["--no-dotenv", "governance"]
    args = base + [
        "approve",
        "M1",
        "--version",
        "1.0.0",
        "--scope",
        M1.scope_fingerprint(),
        "--accept-limitations",
        gv.limitations_version("M1"),
        "--acknowledge",
        ",".join(gv.limitation_ids("M1")),
        "--approved-scope",
        "HB_NORTH",
        "--triggers",
        "record",
        "--reviewer",
        "Synthetic Reviewer",
        "--role",
        "synthetic",
        "--evidence",
        "SYN-cli",
        "--date",
        "2026-10-01",
        "--rationale",
        "synthetic test",
    ]
    assert cli.main(args) == 0  # preview: no audit entry
    assert not gv.audit_path(syn_dir).exists()
    assert cli.main(args + ["--execute"]) == 0
    assert (
        cli.main(
            base
            + [
                "set-revision-policy",
                "--value",
                "latest-retrieved",
                "--reviewer",
                "Synthetic Operator",
                "--role",
                "operator",
                "--date",
                "2026-10-01",
                "--rationale",
                "synthetic",
                "--execute",
            ]
        )
        == 0
    )
    entries = gv.audit_entries(syn_dir)
    assert [e["action"] for e in entries] == ["approve", "set-revision-policy"]
    assert all("Synthetic Reviewer" not in json.dumps(e) for e in entries)
    assert entries[0]["event_id"].startswith("APR-M1-") and entries[0]["actor_role"] == "synthetic"
    assert cli.main(base + ["audit"]) == 0
    out = capsys.readouterr().out
    assert "Synthetic Reviewer" not in out and "APR-M1-" in out


def test_append_line_is_atomic_and_preserves_earlier_lines(tmp_path):
    p = tmp_path / "x.jsonl"
    ap.append_line(p, '{"a": 1}')
    ap.append_line(p, '{"b": 2}')
    assert p.read_text("utf-8") == '{"a": 1}\n{"b": 2}\n'
    assert not list(tmp_path.glob("*.tmp"))


def test_cli_decisions_preview_by_default_and_validate(syn_dir, monkeypatch, capsys):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(syn_dir))
    base = ["--no-dotenv", "governance"]
    assert cli.main(base + ["list"]) == 0 and "CMP-B" in capsys.readouterr().out
    assert cli.main(base + ["review", "AGG-B"]) == 0
    out = capsys.readouterr().out
    assert "AGG-B-L1" in out and "mambo governance approve AGG-B" in out
    assert cli.main(base + ["show", "M1"]) == 0 and "HB_NORTH only" in capsys.readouterr().out
    rej = base + [
        "reject",
        "AGG-B",
        "--reviewer",
        "Synthetic Reviewer",
        "--role",
        "synthetic",
        "--date",
        "2026-10-02",
        "--rationale",
        "r",
        "--issue",
        "collapses to AGG-A",
    ]
    assert cli.main(rej) == 0 and not ap.path(syn_dir).exists()
    assert cli.main(rej + ["--execute"]) == 0
    assert gv.states(syn_dir)["AGG-B"].state == gv.REJECTED
    sup = base + [
        "supersede",
        "AGG-B",
        "--reviewer",
        "Synthetic Reviewer",
        "--role",
        "synthetic",
        "--date",
        "2026-10-02",
        "--rationale",
        "r",
        "--replacement-id",
        "AGG-B",
        "--replacement-version",
        "1.1.0",
        "--migration",
        "re-review",
        "--execute",
    ]
    assert cli.main(sup) == 0 and gv.states(syn_dir)["AGG-B"].state == gv.SUPERSEDED
    bad = base + [
        "approve",
        "M1",
        "--version",
        "1.0.0",
        "--scope",
        M1.scope_fingerprint(),
        "--accept-limitations",
        gv.limitations_version("M1"),
        "--acknowledge",
        "all",
        "--approved-scope",
        "HB_NORTH",
        "--triggers",
        "record",
        "--reviewer",
        "S",
        "--role",
        "r",
        "--evidence",
        "e",
        "--date",
        "2026-10-01",
        "--rationale",
        "x",
    ]
    assert cli.main(bad) == 1 and "generic" in capsys.readouterr().err
    assert cli.main(base + ["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["active_set"]["convention"] is None and "AGG-B" in status["records"]
    assert cli.main(base + ["approve"]) == 1  # no record id


def test_synthetic_approvals_do_not_count_in_an_unmarked_dir(tmp_path):
    d = tmp_path / "real-like"
    approve(d, "M1")
    assert gv.states(d)["M1"].state == gv.INCOMPATIBLE  # invalid approval → never active


# --- System Health governance section ---------------------------------------------------------


@pytest.fixture
def page_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(data))
    monkeypatch.setattr(routes, "PAGES", {})
    monkeypatch.setattr(system_health, "NOW", lambda: NOW)
    return data


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return "\n".join(parts)


def test_governance_section_renders_without_writing(page_env):
    at = AppTest.from_string(HEALTH).run(timeout=40)
    assert not at.exception and not data_elements(at)
    text = _texts(at)
    assert "Read-only" in text
    assert any(h.value.startswith("Governance of the price-comparison") for h in at.header)
    records = next(t.value for t in at.table if "Activation" in t.value.columns)
    assert list(records["State"]) == ["missing"] * 5
    assert not (page_env / "assumptions").exists()


def test_governance_section_shows_states_settings_and_withholds_names(page_env):
    page_env.mkdir()
    (page_env / ap.SYNTHETIC_MARKER).write_text("synthetic\n", "utf-8")
    for rid in ("M1", "AGG-A", "CMP-A"):
        approve(page_env, rid)
    setting(page_env, gv.SET_AGGREGATION, "AGG-A")
    at = AppTest.from_string(HEALTH).run(timeout=40)
    assert not at.exception
    text = _texts(at) + json.dumps([t.value.to_dict() for t in at.table], default=str)
    assert "Synthetic Reviewer" not in text
    records = next(t.value for t in at.table if "Activation" in t.value.columns)
    by_id = dict(zip(records["Record"], records["State"], strict=True))
    assert by_id["M1 1.0.0"] == "active" and by_id["AGG-A 1.0.0"] == "active"
    assert by_id["CMP-A 1.0.0"] == "approved_inactive"
    settings_tbl = next(t.value for t in at.table if "Setting" in t.value.columns)
    assert list(settings_tbl["Value"]) == ["none set", "AGG-A", "none set"]
    assert "not the selected" in text or "no governed revision policy" in text
    assert len(ap.events(page_env)) == 3  # viewing wrote nothing


# --- guards -----------------------------------------------------------------------------------


def test_guard_no_automatic_approval_or_reviewer_inference():
    for rel in (
        "ercot/governance.py",
        "governance_cli.py",
        "governance_view.py",
        "ercot/approvals.py",
    ):
        text = (SRC / rel).read_text("utf-8")
        assert not re.search(r"getuser|getlogin|USERNAME|gh api user|git config user", text), rel
        assert "write_text" not in (SRC / "governance_view.py").read_text("utf-8")
    view = (SRC / "governance_view.py").read_text("utf-8")
    assert "ap.append" not in view and "append_setting" not in view and "st.button" not in view


def test_guard_default_settings_are_none_not_first_listed():
    assert gv.CONVENTIONS[0] == "CMP-A"  # listed first, yet never a default
    assert gv.current_settings(Path("Z:/nonexistent"))["active_comparison_convention"] is None
    source = (SRC / "ercot/governance.py").read_text("utf-8")
    assert not re.search(
        r"(astimezone|ZoneInfo|timedelta)", source.replace("now.astimezone(UTC)", "")
    )
    assert "0.25" not in source.replace("0.25 h is never", "")
