"""Comparison investigation panel (Stage 25, ADR 0022) inside the interval-alignment diagnostic.

One governed hour at a time: the researched candidate formulas and their signs, synthetic
benchmarks, the approval state of M1, the aggregation record, and the comparison record, and for
stored observations either the approved analytical difference or a withheld state with every
blocker. No chart, no time series, no quantity, no amount of money, no Finance import; it never
collects and never runs during a refresh.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer.ercot import aggregation as ag
from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot import assumed_alignment as aa
from mambo_explorer.ercot import comparison as cmp
from mambo_explorer.ercot import comparison_policy as cmpp
from mambo_explorer.ercot.aggregation_policy import record as agg_record
from mambo_explorer.opf_lab import md_dollars

MODE_OFF = "off"
MODES = {
    MODE_OFF: "Off (default): no comparison is computed",
    cmp.GOVERNED: "Governed comparison under review-approved assumptions",
}
# Hand-worked SYNTHETIC examples (docs/comparison-evidence.md §6); not ERCOT data.
SYNTHETIC_EXAMPLES = (
    ("RT higher", "40", "30"),
    ("RT lower", "20", "50"),
    ("Negative DAM", "20", "-10"),
    ("Negative RT summary", "-10", "20"),
    ("Both negative", "-5", "-20"),
    ("Equal prices", "42.5", "42.5"),
    ("DAM price zero", "12", "0"),
)


def render_comparison(
    data_dir,
    alignment: aa.AssumedResult,
    aggregation: ag.AggregationResult,
    alignment_state: str | None,
    m1_approval: ap.Approval,
) -> None:
    st.header("Comparison investigation")
    st.info(f"**{cmpp.NOTICE}**")
    st.markdown(
        md_dollars(
            "ERCOT defines no day-ahead/real-time price difference in the reviewed materials; "
            "the letters DART appear in the Protocols only as a variable prefix for a "
            "day-ahead difference between two locations, so the term is not used for this "
            "comparison. A difference of two prices in $/MWh is in $/MWh: it is not an amount "
            "of money, because no quantity is involved."
        )
    )
    st.subheader("Candidate formulas and signs")
    st.table(list(cmp.DIMENSIONS), hide_index=True)
    st.subheader("Synthetic benchmarks (not ERCOT data)")
    rows = []
    for label, rt_summary, dam in SYNTHETIC_EXAMPLES:
        a = cmp.candidate(cmp.RT_FIRST, rt_summary, dam)
        b = cmp.candidate(cmp.DAM_FIRST, rt_summary, dam)
        pct = cmp.candidate(cmp.PERCENTAGE, rt_summary, dam)
        rows.append(
            {
                "Example": label,
                "RT summary ($/MWh)": rt_summary,
                "DAM ($/MWh)": dam,
                "CMP-A RT − DAM ($/MWh)": a.output,
                "CMP-B DAM − RT ($/MWh)": b.output,
                "Percentage candidate (not approvable)": f"{pct.output} %"
                if pct.output is not None
                else pct.note,
            }
        )
    st.table(rows, hide_index=True)
    st.caption(
        "The percentage column shows why it is not approvable: it is undefined when the DAM "
        "price is 0 and reads backwards when the DAM price is negative."
    )
    render_governed(data_dir, alignment, aggregation, alignment_state, m1_approval)


def _aggregation_snapshot(data_dir, aggregation: ag.AggregationResult, alignment_state):
    ctx = ag.context(aggregation, alignment_state)
    key = ag.snapshot_key(ctx)
    snaps = [s for s in ag.snapshots(data_dir) if ag.snapshot_key(s["context"]) == key]
    if not snaps:
        return None, None
    snap, state, _ = ag.snapshot_states(snaps, {key: ctx})[-1]
    return snap, state


def render_governed(data_dir, alignment, aggregation, alignment_state, m1_approval) -> None:
    st.subheader("Stored observations: one governed hour")
    st.info(f"**{cmpp.NOTICE}**")
    mode = st.radio(
        "Comparison mode",
        list(MODES),
        format_func=MODES.get,
        key="cmp_mode",  # session only: every session starts with comparison off
    )
    method_id = st.radio(
        "Comparison record (sign convention)",
        [r.id for r in cmpp.RECORDS],
        format_func=lambda i: f"{i}: {cmpp.record(i).sign_convention}",
        index=None,  # never chosen silently
        key="cmp_method",
    )
    approvals = [
        {"Decision": "M1 1.0.0 (alignment)", "Approval": m1_approval.status},
        {
            "Decision": f"{aggregation.method_id} {aggregation.method_version} (aggregation)"
            if aggregation.method_id
            else "aggregation record",
            "Approval": ap.status(data_dir, agg_record(aggregation.method_id)).status
            if aggregation.method_id
            else "—",
        },
    ] + [
        {"Decision": f"{r.id} {r.version} (comparison)", "Approval": ap.status(data_dir, r).status}
        for r in cmpp.RECORDS
    ]
    st.table(approvals, hide_index=True)
    if mode != cmp.GOVERNED or method_id is None:
        st.markdown(
            "Comparison mode is off or no sign convention is chosen, so nothing is compared. "
            "Choose both above; the value is still withheld unless every approval and input is "
            "in place."
        )
        _limits()
        return
    record = cmpp.record(method_id)
    agg_snap, agg_state = _aggregation_snapshot(data_dir, aggregation, alignment_state)
    dam = cmp.store_dam_lookup(data_dir)(alignment.dam_identity, alignment.dam_revision)
    result = cmp.compare(
        method_id,
        mode=mode,
        alignment=alignment,
        aggregation=aggregation,
        aggregation_snapshot=agg_snap,
        aggregation_snapshot_state=agg_state,
        dam=dam,
        m1_approval=m1_approval,
        aggregation_approval=ap.status(data_dir, agg_record(aggregation.method_id))
        if aggregation.method_id
        else None,
        comparison_approval=ap.status(data_dir, record),
    )
    if result.status == cmp.APPROVED_COMPLETE:
        st.success(
            md_dollars(
                f"**{result.status}** — {result.output_name}: **{result.output} {result.units}**"
                f" ({record.sign_convention})"
            )
        )
    else:
        st.warning(md_dollars(f"**{result.status}** — the comparison is withheld."))
        st.markdown(md_dollars("**Blockers:**\n" + "\n".join(f"- {b}" for b in result.blockers)))
    rev = result.dam_revision or {}
    st.table(
        [
            {"Item": "Comparison record", "Value": f"{record.id} {record.version}"},
            {"Item": "Formula", "Value": f"{record.formula} [{record.formula_version}]"},
            {"Item": "Sign", "Value": record.sign_convention},
            {"Item": "Location", "Value": record.location},
            {
                "Item": "DAM identity",
                "Value": ", ".join(f"{k} {v}" for k, v in result.dam_identity.items()),
            },
            {
                "Item": "DAM revision",
                "Value": f"{rev.get('revision', '—')} (document {rev.get('doc_id', '—')}, "
                f"published {rev.get('published', '—')})",
            },
            {
                "Item": "DAM price",
                "Value": f"{result.dam_price} $/MWh" if result.dam_price else "—",
            },
            {
                "Item": "RT aggregation",
                "Value": f"{result.aggregation or '—'}; snapshot "
                f"{result.aggregation_snapshot or 'none'} ({agg_state or '—'})",
            },
            {
                "Item": "RT summary",
                "Value": f"{result.rt_summary} $/MWh" if result.rt_summary else "withheld",
            },
            {
                "Item": "Alignment snapshot",
                "Value": f"{result.alignment_snapshot or 'none'} ({alignment_state or '—'})",
            },
            {"Item": "Revision policy", "Value": result.revision_policy},
            {
                "Item": "Result",
                "Value": f"{result.output} {result.units}" if result.output else "withheld",
            },
            {"Item": "Finality", "Value": result.finality_status},
        ],
        hide_index=True,
    )
    if result.rt_intervals:
        st.table(
            [
                {
                    "RT interval": i["DeliveryInterval"],
                    "DSTFlag": i["DSTFlag"],
                    "Revision": str(i["revision"]),
                    "Document": i["doc_id"],
                }
                for i in result.rt_intervals
            ],
            hide_index=True,
        )
    st.table(
        [
            {"Check": n, "Passed": "yes" if ok else "no", "Detail": d}
            for n, ok, d in result.validation
        ],
        hide_index=True,
    )
    _limits(result)
    _snapshots(data_dir, result, agg_state)


def _limits(result: cmp.ComparisonResult | None = None) -> None:
    st.markdown(
        md_dollars(
            "**Never read this as:**\n"
            + "\n".join(f"- {p}" for p in cmpp.PROHIBITED_INTERPRETATIONS)
        )
    )
    limits = result.limitations if result and result.limitations else cmpp.CMP_A.limitations
    st.markdown(md_dollars("**Limitations:**\n" + "\n".join(f"- {t}" for t in limits)))


def _snapshots(data_dir, result: cmp.ComparisonResult, agg_state) -> None:
    ctx = cmp.context(result, agg_state)
    if st.button("Record a comparison snapshot", key="cmp_snapshot"):
        cmp.record_snapshot(data_dir, cmp.snapshot(result, ctx, ap.recorded_now()))
    snaps = [
        s for s in cmp.snapshots(data_dir) if s["context"]["dam_identity"] == result.dam_identity
    ]
    if not snaps:
        st.markdown("No comparison snapshot is recorded for this hour.")
        return
    states = cmp.snapshot_states(snaps, {cmp.snapshot_key(ctx): ctx})
    st.table(
        [
            {
                "Snapshot": s["snapshot_id"],
                "Recorded (UTC)": s["recorded_at_utc"],
                "Status then": s["status"],
                "Result then": f"{s['output']} {s['units']}" if s["output"] else "withheld",
                "State now": state,
                "Why": "; ".join(why) or "—",
            }
            for s, state, why in states
        ],
        hide_index=True,
    )
    st.caption(
        "Comparison snapshots are never deleted or overwritten; a stale one must be recomputed."
    )
