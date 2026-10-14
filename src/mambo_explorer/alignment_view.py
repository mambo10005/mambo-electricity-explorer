"""Interval-alignment diagnostic (Stage 22, ADR 0019): labels only, never prices.

Reads committed day-ahead (NP4-190-CD) and real-time (NP6-905-CD) observations from their own
stores and shows how one day-ahead hour's source-native labels relate to real-time interval
labels under `ercot.alignment`. It reads only whether each price is present, never its value:
no DART spread, no hourly real-time figure, no clock time or UTC. It never collects.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer.ercot import alignment as al
from mambo_explorer.ercot import prices as px
from mambo_explorer.ercot import rt_prices as rt

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
    res = al.align(hour, chosen, revision_policy=policy, dam_revisions=revisions)
    render_result(res)
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
    _evidence()


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
            "\n".join(
                f"- **{e.id}**: [{e.title}]({e.location}), {e.section}; {e.version}; "
                f"retrieved {e.retrieved}. {e.proposition} *Remaining ambiguity:* {e.ambiguity}"
                for e in items
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
