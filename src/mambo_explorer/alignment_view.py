"""Interval-alignment diagnostic (Stage 22, ADR 0019): labels only, never prices.

Reads committed day-ahead (NP4-190-CD) and real-time (NP6-905-CD) observations from their own
stores and shows how one day-ahead hour's source-native labels relate to real-time interval
labels under `ercot.alignment`. It reads only whether each price is present, never its value:
no DART spread, no hourly real-time figure, no clock time or UTC. It never collects.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer.ercot import alignment as al
from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot import assumed_alignment as aa
from mambo_explorer.ercot import prices as px
from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.m1_policy import current
from mambo_explorer.opf_lab import md_dollars

CANDIDATE = "M1"
NO_COMPARISON = (
    "**No DART spread, price difference, or hourly real-time price is calculated here.** This "
    "diagnostic compares source-native labels only; prices are not read. It is not a market "
    "comparison, and no value is called final."
)
STATUS_TEXT = {
    al.ALIGNED_COMPLETE: "Every real-time interval the mapping expects for this hour is present "
    "once, with a published price, under the chosen revision policy.",
    al.ALIGNED_INCOMPLETE: "The hour's labels align, but intervals are missing, duplicated, "
    "outside the verified set, or carry a blank price. Nothing is filled or averaged.",
    al.AMBIGUOUS_DST: "The DSTFlag cannot be matched without guessing; the hour is not aligned.",
    al.INCOMPATIBLE_IDENTITY: "The candidate intervals belong to another settlement point, "
    "type, or DeliveryDate.",
    al.MISSING_DAY_AHEAD: "No usable day-ahead observation for this hour.",
    al.MISSING_REAL_TIME: "No stored real-time interval carries this hour's labels.",
    al.UNSUPPORTED_SEMANTICS: "No alignment rule is supported by the recorded evidence, so none "
    "is asserted.",
    al.UNAVAILABLE_REVISION: "The chosen revision policy cannot be applied with the stored "
    "evidence.",
    al.INVALID_INPUT: "The labels or policies are not valid inputs.",
}


def load_day(data_dir, day: str) -> tuple[list[al.DamObservation], list[al.RtObservation]]:
    """Every stored revision of the day's labels; `price_present` only, never the value."""
    dam: list[al.DamObservation] = []
    rtl: list[al.RtObservation] = []
    dam_store, rt_store = px.store(data_dir), rt.store(data_dir)
    if dam_store.committed_files("observations"):
        with dam_store.query() as con:
            for d, h, loc, typ, f, rev, doc, pub, present in con.execute(
                "SELECT delivery_date_raw, hour_ending, location, location_type, dst_flag, "
                "revision, doc_id, publish_time_raw, value IS NOT NULL FROM observations "
                "WHERE delivery_date_raw = ? ORDER BY row_order, revision",
                [day],
            ).fetchall():
                dam.append(al.DamObservation(al.DamHour(d, h, loc, typ, f), rev, doc, pub, present))
    if rt_store.committed_files("observations"):
        with rt_store.query() as con:
            for d, h, i, loc, typ, f, rev, doc, pub, present in con.execute(
                "SELECT delivery_date_raw, delivery_hour, delivery_interval, location, "
                "settlement_point_type, dst_flag, revision, doc_id, publish_time_raw, "
                "value IS NOT NULL FROM observations WHERE delivery_date_raw = ? "
                "ORDER BY CAST(delivery_hour AS INTEGER), CAST(delivery_interval AS INTEGER), "
                "dst_flag, revision",
                [day],
            ).fetchall():
                rtl.append(
                    al.RtObservation(al.RtInterval(d, h, i, loc, typ, f), rev, doc, pub, present)
                )
    return dam, rtl


def delivery_dates(data_dir) -> list[str]:
    days: set[str] = set()
    for target in (px.store(data_dir), rt.store(data_dir)):
        if target.committed_files("observations"):
            with target.query() as con:
                days |= {
                    r[0]
                    for r in con.execute(
                        "SELECT DISTINCT delivery_date_raw FROM observations"
                    ).fetchall()
                }
    return sorted(days, key=lambda d: (d[6:], d[:5]))


def _hours(dam: list[al.DamObservation]) -> list[al.DamHour]:
    seen: list[al.DamHour] = []
    for o in dam:
        if o.hour not in seen:
            seen.append(o.hour)
    return seen


def _hour_label(h: al.DamHour) -> str:
    return f"HourEnding {h.hour_ending}, DSTFlag {h.dst_flag}"


def _rt_option(o: al.RtObservation) -> str:
    return f"{o.interval.label()} rev {o.revision}"


def render_alignment(settings) -> None:
    st.caption(
        "Diagnostic for learners and developers: how one ERCOT day-ahead hour's labels relate "
        f"to real-time interval labels ({px.DATASET} and {rt.DATASET}, {px.LOCATION}). "
        "Data label: **observed** labels from both stores; no price is shown."
    )
    st.info(NO_COMPARISON)
    days = delivery_dates(settings.data_dir)
    if not days:
        st.info(
            "No day-ahead or real-time prices have been collected yet, so there are no labels to "
            "diagnose. Collection runs from the command line, never from this page."
        )
        _evidence()
        return
    day = st.selectbox(
        "Delivery date (ERCOT DeliveryDate, as written)",
        days,
        index=len(days) - 1,
        key="align_day",
    )
    dam, rtl = load_day(settings.data_dir, day)
    hours = _hours(dam)
    if hours:
        hour = st.selectbox(
            "Day-ahead hour (source-native HourEnding and DSTFlag)",
            hours,
            format_func=_hour_label,
            key="align_hour",
        )
    else:
        st.warning(f"No day-ahead hour is stored for DeliveryDate {day}.")
        hour = None
    policy = st.radio(
        "Revision policy",
        list(al.REVISION_POLICIES),
        key="align_policy",
        help="Unavailable policies are listed so their limits stay visible.",
    )
    st.caption(al.REVISION_POLICIES[policy])
    if hour is not None:
        default = [o for o in rtl if o.interval.delivery_hour == str(int(hour.hour_ending[:2]))]
    else:
        default = []
    chosen = st.multiselect(
        "Real-time intervals offered to the diagnostic (all stored revisions for this date)",
        rtl,
        default=default,
        format_func=_rt_option,
        # one widget per (date, hour): the default is that hour's intervals, never a
        # selection left over from another hour
        key=f"align_rt_{day}_{hour.hour_ending}_{hour.dst_flag}" if hour else f"align_rt_{day}",
    )
    if hour is None:
        _evidence()
        return
    revisions = [o for o in dam if o.hour == hour]
    record = current("M1")
    approval = ap.status(settings.data_dir, record)
    basis = st.radio(
        "Alignment basis",
        list(aa.BASES),
        format_func=BASIS_LABELS.get,
        key="align_basis",  # session only: every new session starts authoritative-only
        help="M1 is used only when you choose it here and a recorded approval is active.",
    )
    if basis == aa.ASSUMPTION:
        res = aa.align_with_basis(
            aa.ASSUMPTION,
            hour,
            chosen,
            revision_policy=policy,
            approval=approval,
            dam_revisions=revisions,
        )
        if res.banner:
            st.info(f"**{res.banner}**")
        render_assumed(res)
        render_approval(record, approval)
        render_snapshots(settings.data_dir, res, dam, rtl, hour, approval)
        _aggregation(settings.data_dir, res, dam, rtl, hour, approval)
        _evidence()
        return
    res = al.align(hour, chosen, revision_policy=policy, dam_revisions=revisions)
    render_result(res)
    render_approval(record, approval)
    st.header("Candidate check (not an accepted alignment)")
    st.warning(
        f"Candidate **{CANDIDATE}** is {al.candidate(CANDIDATE).status}, not accepted. The check "
        "below shows how the labels would relate under that unverified rule, so missing, "
        "duplicate, DST, and revision cases stay visible. It asserts nothing."
    )
    st.caption(al.candidate(CANDIDATE).rule)
    if st.toggle(f"Show the {CANDIDATE} candidate check", key="align_candidate"):
        render_result(
            al.check_candidate(
                CANDIDATE, hour, chosen, revision_policy=policy, dam_revisions=revisions
            ),
            heading="Candidate status",
        )
    _aggregation(
        settings.data_dir,
        aa.align_with_basis(
            aa.AUTHORITATIVE, hour, chosen, revision_policy=policy, dam_revisions=revisions
        ),
        dam,
        rtl,
        hour,
        approval,
    )
    _evidence()


def _aggregation(data_dir, res, dam, rtl, hour, approval) -> None:
    """Stage 24 aggregation investigation (labels in, governed summary or withheld out)."""
    from mambo_explorer import aggregation_view as agv

    stored_dam, stored_rt = aa.hour_inputs(dam, rtl, hour)
    ctx = aa.context(
        res.alignment_basis, res.dam_identity, res.revision_policy, stored_dam, stored_rt, approval
    )
    agv.render_investigation(data_dir, approval)
    agv.render_actual(data_dir, res, ctx, approval)


BASIS_LABELS = {
    aa.AUTHORITATIVE: "Authoritative definitions only (default)",
    aa.ASSUMPTION: "Use review-approved assumption M1",
}
ASSUMED_TEXT = {
    aa.COMPLETE_UNDER: "All four intervals that M1 expects are present once, each with a "
    "published price, under the chosen revision policy.",
    aa.INCOMPLETE_UNDER: "Intervals that M1 expects are missing, outside the expected set, or "
    "carry a blank price. Nothing is filled or averaged.",
    aa.CONFLICTING_REVISIONS: "Two observations of one interval share a revision number; the "
    "revision policy cannot choose between them, so the hour is not complete.",
    aa.APPROVAL_MISSING: "No approval of M1 is recorded, so M1 is not used.",
    aa.APPROVAL_REVOKED: "The recorded approval of M1 was revoked, so M1 is not used.",
    aa.APPROVAL_SUPERSEDED: "The M1 record was superseded, so M1 is not used.",
    aa.APPROVAL_INCOMPATIBLE: "The recorded approval is for another version, scope, or schema; "
    "re-review is required before M1 is used.",
    aa.APPROVAL_INVALID: "The approval record is incomplete or unreadable, so M1 is not used.",
    aa.UNSUPPORTED_SCOPE: "This settlement point is outside M1's approved scope.",
}


def render_assumed(res: aa.AssumedResult) -> None:
    st.subheader("Alignment under the selected basis")
    text = ASSUMED_TEXT.get(res.alignment_status) or STATUS_TEXT.get(res.alignment_status, "")
    show = st.success if res.completeness_status == aa.COMPLETE else st.warning
    show(f"**{res.alignment_status}** — {text}")
    if res.reasons:
        st.markdown("\n".join(f"- {r}" for r in res.reasons))
    st.table(
        [
            {"Item": "Alignment basis", "Value": BASIS_LABELS[res.alignment_basis]},
            {
                "Item": "Assumption",
                "Value": f"{res.assumption_id} {res.assumption_version}"
                if res.assumption_id
                else "none",
            },
            {
                "Item": "Approval",
                "Value": f"{res.approval_status} ({res.approval_reference or '—'})",
            },
            {"Item": "Official label semantics", "Value": res.authoritative_semantics_status},
            {"Item": "Completeness", "Value": res.completeness_status},
            {"Item": "Revision policy", "Value": res.revision_policy},
            {
                "Item": "Expected intervals (part of M1)",
                "Value": ", ".join(res.expected_intervals) or "not evaluated",
            },
            {"Item": "Observed intervals", "Value": ", ".join(res.observed_intervals) or "none"},
            {"Item": "Missing intervals", "Value": ", ".join(res.missing_intervals) or "none"},
            {"Item": "Duplicate intervals", "Value": "; ".join(res.duplicate_intervals) or "none"},
            {"Item": "DST flags", "Value": _dst_text(res.dst)},
        ],
        hide_index=True,
    )
    st.subheader("Day-ahead identity")
    rev = res.dam_revision or {}
    st.table(
        [{"Item": k, "Value": str(v)} for k, v in res.dam_identity.items()]
        + [
            {"Item": "Revision", "Value": str(rev.get("revision", "—"))},
            {"Item": "Document", "Value": str(rev.get("doc_id", "—"))},
            {"Item": "Published by ERCOT", "Value": str(rev.get("published", "—"))},
        ],
        hide_index=True,
    )
    if res.expected_intervals:
        st.subheader("Interval viewer")
        by_label = {m["DeliveryInterval"]: m for m in res.matched}
        st.table(
            [
                {
                    "Interval": i,
                    "Found": "yes" if i in by_label else "no",
                    "Revision": str(by_label[i]["revision"]) if i in by_label else "—",
                    "Document": by_label[i]["doc_id"] if i in by_label else "—",
                }
                for i in res.expected_intervals
            ],
            hide_index=True,
        )
        if res.matched:
            pick = st.selectbox(
                "Show one matched real-time interval",
                [m["DeliveryInterval"] for m in res.matched],
                format_func=lambda i: f"DeliveryInterval {i}",
                key="align_interval_view",
            )
            st.table(
                [{"Item": k, "Value": str(v)} for k, v in by_label[pick].items()],
                hide_index=True,
            )
    if res.revision_conflicts:
        st.subheader("Revisions chosen by the policy")
        st.table(
            [
                {
                    "Interval": c["interval"],
                    "Stored revisions": ", ".join(map(str, c["revisions"])),
                    "Selected": c["selected"],
                }
                for c in res.revision_conflicts
            ],
            hide_index=True,
        )
    if res.excluded:
        st.subheader("Candidates not matched")
        st.table(
            [
                {
                    "Interval": f"H{x['DeliveryHour']} I{x['DeliveryInterval']} {x['DSTFlag']}",
                    "Point": f"{x['SettlementPointName']}/{x['SettlementPointType']}",
                    "Reason": x["reason"],
                }
                for x in res.excluded
            ],
            hide_index=True,
        )
    st.subheader("Limitations")
    st.markdown("\n".join(f"- {t}" for t in res.limitations))


def render_approval(record, approval: ap.Approval) -> None:
    st.header(f"Assumption {record.id} {record.version} and its approval")
    st.markdown(f"**Mapping rule (an assumption, not an ERCOT definition):** {record.rule}")
    st.table(
        [
            {"Item": "Approval status", "Value": approval.status},
            {"Item": "Approval record", "Value": approval.reference or "none"},
            {"Item": "Detail", "Value": approval.detail},
            {"Item": "Official label semantics", "Value": record.official_status},
            {
                "Item": "Scope",
                "Value": "; ".join(
                    f"{s.day_ahead_point} ({s.day_ahead_location_type}) ↔ {s.real_time_point}/"
                    f"{s.real_time_type}"
                    for s in record.locations
                )
                + f" in {' and '.join(record.datasets)}",
            },
            {"Item": "Scope fingerprint", "Value": record.scope_fingerprint()},
            {"Item": "Schema fingerprint", "Value": record.schema_fingerprint()},
        ],
        hide_index=True,
    )
    st.markdown(
        "**What has and has not happened:**\n"
        f"- *Authorization to implement:* {record.authorization}\n"
        f"- *Reported reviewer acceptance:* {record.reported_acceptance}\n"
        "- *Recorded, attributable approval:* "
        + (
            "recorded (see the table)."
            if approval.status == ap.APPROVED
            else "none active; M1 cannot be used until one is recorded."
        )
        + "\n- *Official ERCOT verification:* none; the label definitions remain unresolved."
    )
    st.markdown(
        "**Unresolved official definitions:**\n"
        + "\n".join(f"- {u}" for u in record.unresolved_definitions)
    )
    st.markdown("**Scope evidence:** " + " ".join(s.evidence for s in record.locations))
    st.markdown(
        "**Re-review triggers:**\n" + "\n".join(f"- {u}" for u in record.re_review_triggers)
    )
    st.caption(
        "Approvals are recorded locally with `mambo assumption approve --reviewer … --role … "
        "--evidence … --approved-on YYYY-MM-DD --execute` (a dry run without --execute) and "
        "revoked with `mambo assumption revoke --record … --reason … --execute`. They live in "
        "the data directory, are never committed, and are never filled in automatically."
    )


def render_snapshots(data_dir, res, dam, rtl, hour, approval) -> None:
    st.header("Diagnostic snapshots")
    stored_dam, stored_rt = aa.hour_inputs(dam, rtl, hour)
    ctx = aa.context(
        res.alignment_basis, res.dam_identity, res.revision_policy, stored_dam, stored_rt, approval
    )
    if st.button("Record a snapshot of this result", key="align_snapshot"):
        aa.record_snapshot(data_dir, aa.snapshot(res, ctx, ap.recorded_now()))
    snaps = [s for s in aa.snapshots(data_dir) if s["context"]["dam_identity"] == res.dam_identity]
    if not snaps:
        st.markdown("No snapshot is recorded for this hour.")
        return
    states = aa.snapshot_states(snaps, {aa.snapshot_key(ctx): ctx})
    st.table(
        [
            {
                "Snapshot": s["snapshot_id"],
                "Recorded (UTC)": s["recorded_at_utc"],
                "Basis / policy": f"{s['context']['basis']} / {s['context']['revision_policy']}",
                "Status then": s["alignment_status"],
                "State now": state,
                "Why": "; ".join(why) or "—",
            }
            for s, state, why in states
        ],
        hide_index=True,
    )
    st.caption(
        "Snapshots are never deleted. A snapshot is stale when its inputs, revision policy, "
        "assumption version or scope, approval, or validation version no longer match, and "
        "superseded when a later snapshot exists for the same hour, basis, and policy."
    )


def render_result(res: al.AlignmentResult, heading: str = "Alignment status") -> None:
    st.subheader(heading)
    show = st.success if res.status == al.ALIGNED_COMPLETE and res.asserted else st.warning
    prefix = "" if res.asserted else "Not asserted — "
    show(f"{prefix}**{res.status}** — {STATUS_TEXT[res.status]}")
    if res.reasons:
        st.markdown("\n".join(f"- {r}" for r in res.reasons))
    st.table(
        [
            {
                "Item": "Mapping",
                "Value": f"{res.mapping} ({res.mapping_status})"
                if res.mapping
                else "(none accepted)",
            },
            {"Item": "Asserted", "Value": "yes" if res.asserted else "no"},
            {"Item": "Revision policy", "Value": res.revision_policy},
            {"Item": "Completeness policy", "Value": res.completeness_policy},
            {
                "Item": "Expected real-time intervals",
                "Value": _expected_text(res),
            },
            {"Item": "Observed real-time intervals", "Value": str(res.observed_interval_count)},
            {"Item": "Missing intervals", "Value": ", ".join(res.missing_intervals) or "none"},
            {"Item": "Duplicate intervals", "Value": "; ".join(res.duplicate_intervals) or "none"},
            {"Item": "DST flags", "Value": _dst_text(res.dst)},
        ],
        hide_index=True,
    )
    st.subheader("Day-ahead identity")
    rev = res.dam_revision or {}
    st.table(
        [
            {
                **res.dam_identity,
                "Revision": rev.get("revision", "—"),
                "Document": rev.get("doc_id", "—"),
                "Published by ERCOT": rev.get("published", "—"),
            }
        ],
        hide_index=True,
    )
    st.subheader("Matched real-time identities")
    if res.matched:
        st.table([_rt_row(m) for m in res.matched], hide_index=True)
    else:
        st.markdown("None.")
    if res.revision_conflicts:
        st.subheader("Revision conflicts resolved by the policy")
        st.table(
            [
                {
                    "Interval": c["interval"],
                    "Stored revisions": ", ".join(map(str, c["revisions"])),
                    "Selected": c["selected"],
                    "Policy": c["policy"],
                }
                for c in res.revision_conflicts
            ],
            hide_index=True,
        )
    if res.excluded:
        st.subheader("Candidates not matched")
        st.table([{**_rt_row(x), "Reason": x["reason"]} for x in res.excluded], hide_index=True)
    st.subheader("Limitations")
    st.markdown("\n".join(f"- {t}" for t in res.limitations))


def _expected_text(res: al.AlignmentResult) -> str:
    if res.expected_interval_count is not None:
        return str(res.expected_interval_count)
    if res.candidate_expected_count is not None:
        return f"not verified ({res.candidate_expected_count} under the unaccepted candidate)"
    return "not verified"


def _dst_text(dst: dict) -> str:
    if not dst:
        return "not evaluated"
    other = dst.get("real_time_other_flag") or []
    return (
        f"day-ahead {dst.get('day_ahead')}; real-time intervals with the same flag: "
        f"{dst.get('real_time_same_flag', 0)}; other flags offered: {', '.join(other) or 'none'}"
    )


def _rt_row(m: dict) -> dict:
    return {
        "DeliveryDate": m["DeliveryDate"],
        "DeliveryHour": m["DeliveryHour"],
        "DeliveryInterval": m["DeliveryInterval"],
        "SettlementPoint": f"{m['SettlementPointName']} / {m['SettlementPointType']}",
        "DSTFlag": m["DSTFlag"],
        "Revision": m["revision"],
        "Document": m["doc_id"],
        "Price published": "yes" if m["price_present"] else "no (blank)",
    }


KINDS = (
    ("official", "Official ERCOT materials"),
    ("actual-file", "Actual-file observations (supporting only)"),
    ("inaccessible", "Inaccessible sources (recorded, not bypassed)"),
)


def _evidence() -> None:
    st.header("Evidence for the mapping")
    cand = al.accepted()
    rows = []
    for c in al.CANDIDATES:
        rows.append(
            {
                "Candidate": c.id,
                "Rule": c.rule,
                "Status": c.status,
                "Confidence": c.confidence,
                "Review": c.review,
            }
        )
    if rows:
        st.table(rows, hide_index=True)
    for kind, title in KINDS:
        items = [e for e in al.EVIDENCE if e.kind == kind]
        st.subheader(title)
        st.markdown(
            md_dollars(
                "\n".join(
                    f"- **{e.id}**: [{e.title}]({e.location}), {e.section}; {e.version}; "
                    f"retrieved {e.retrieved}. {e.proposition} *Remaining ambiguity:* "
                    f"{e.ambiguity}"
                    for e in items
                )
            )
        )
    st.markdown(
        "Accepted mapping: **none**." if cand is None else f"Accepted mapping: **{cand.id}**."
    )
    st.caption(
        "Actual-file consistency supports, but does not replace, ERCOT's definitions. Synthetic "
        "test fixtures are never evidence of ERCOT behavior. Full record: "
        "docs/interval-alignment.md."
    )
