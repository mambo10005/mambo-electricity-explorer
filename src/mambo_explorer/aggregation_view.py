"""Aggregation investigation panel (Stage 24, ADR 0021) inside the interval-alignment diagnostic.

Shows the researched candidate formulas, their dimensional meaning, synthetic benchmarks, the
approval state of M1 and of each aggregation record, and, for stored observations, either the
approved analytical summary or a withheld state with every blocker. It never shows a day-ahead
comparison, a spread, a settlement amount, or a final price, and it never collects.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer.ercot import aggregation as ag
from mambo_explorer.ercot import aggregation_policy as agp
from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot import assumed_alignment as aa
from mambo_explorer.opf_lab import md_dollars

# Hand-worked SYNTHETIC examples (docs/aggregation-evidence.md §6); not ERCOT data.
SYNTHETIC_EXAMPLES = (
    ("Equal 15-minute intervals", ag.ARITHMETIC, ["20", "40", "60", "80"], None, None),
    ("Equal 15-minute intervals", ag.DURATION_WEIGHTED, ["20", "40", "60", "80"],
     ["0.25", "0.25", "0.25", "0.25"], None),
    ("Unequal durations", ag.ARITHMETIC, ["20", "80"], None, None),
    ("Unequal durations", ag.DURATION_WEIGHTED, ["20", "80"], ["0.25", "0.75"], None),
    ("Energy weighting", ag.ENERGY_WEIGHTED, ["20", "80"], None, ["75", "25"]),
    ("Settlement amount", ag.SETTLEMENT_AMOUNT, ["20", "80"], None, ["75", "25"]),
    ("Negative prices", ag.ARITHMETIC, ["-10", "-30", "20", "0"], None, None),
    ("Zero total energy", ag.ENERGY_WEIGHTED, ["20", "80"], None, ["10", "-10"]),
)  # fmt: skip

CLASSIFICATION = (
    {
        "Candidate": "A. Arithmetic mean (AGG-A)",
        "Mathematically valid": "yes",
        "Source-supported": "form used in ERCOT's credit formula HRSAP (§16.11.4.3.3); no "
        "ERCOT hourly real-time SPP",
        "Review-approved": "see approval status",
        "Production-active": "only with both approvals and complete inputs",
        "Prohibited for": "never for settlement, a final price, a spread, a backtest, or Finance",
    },
    {
        "Candidate": "B. Duration-weighted mean (AGG-B)",
        "Mathematically valid": "yes",
        "Source-supported": "15-minute Settlement Interval (§4.1(3), §6.6.1.1) for DSTFlag N",
        "Review-approved": "see approval status",
        "Production-active": "only with both approvals, complete inputs, and duration evidence",
        "Prohibited for": "the same uses; it is not energy-weighted",
    },
    {
        "Candidate": "C. Energy-weighted price",
        "Mathematically valid": "yes (undefined when total energy is 0)",
        "Source-supported": "no compatible quantities in this application",
        "Review-approved": "not approvable",
        "Production-active": "never",
        "Prohibited for": "every production use; EIA demand must not stand in",
    },
    {
        "Candidate": "D. Settlement amount",
        "Mathematically valid": "yes (an amount in $, not a price)",
        "Source-supported": "Protocols §6.6.3 uses participant quantities × ¼",
        "Review-approved": "not approvable",
        "Production-active": "never",
        "Prohibited for": "every production use",
    },
)


def render_investigation(data_dir, m1_approval: ap.Approval) -> None:
    st.header("Aggregation investigation")
    st.info(f"**{agp.LIMITATION_BANNER}**")
    st.markdown(
        "Four ways to summarize an hour's four real-time 15-minute prices were researched. "
        "ERCOT publishes no hourly real-time Settlement Point Price in the reviewed materials, "
        "so none of them is an ERCOT price. Each 15-minute price is itself already a "
        "time-weighted average of SCED prices within its interval (Protocols §6.6.1.1)."
    )
    st.subheader("Candidate formulas and dimensions")
    st.table(list(ag.DIMENSIONS), hide_index=True)
    st.markdown(
        md_dollars(
            "A mean of four prices stays a price summary in $/MWh. When all four durations are "
            "verified and equal, the duration-weighted mean equals the arithmetic mean, and "
            "neither becomes energy-weighted: no quantity of energy enters either formula."
        )
    )
    st.subheader("Classification")
    st.table(list(CLASSIFICATION), hide_index=True)
    st.subheader("Synthetic benchmarks (not ERCOT data)")
    rows = []
    for label, method, prices, durations, energies in SYNTHETIC_EXAMPLES:
        res = ag.candidate(method, prices, durations, energies)
        rows.append(
            {
                "Example": label,
                "Method": method,
                "Prices ($/MWh)": ", ".join(prices),
                "Durations (h)": ", ".join(durations) if durations else "—",
                "Energy (MWh)": ", ".join(energies) if energies else "—",
                "Result": f"{res.output} {res.units}" if res.output is not None else res.note,
                "Status": res.status,
            }
        )
    st.table(rows, hide_index=True)
    st.subheader("Approval status")
    st.table(
        [{"Record": "M1 1.0.0 (alignment)", "Approval": f"{m1_approval.status}"}]
        + [
            {
                "Record": f"{r.id} {r.version} ({r.method})",
                "Approval": ap.status(data_dir, r).status,
            }
            for r in agp.RECORDS
        ],
        hide_index=True,
    )
    st.caption(
        "Approvals are recorded locally with `mambo aggregation approve <id> --version … --scope "
        "… --accept-limitations … --reviewer … --role … --evidence … --approved-on YYYY-MM-DD "
        "--execute` (values from `mambo aggregation show <id>`; a dry run without --execute). "
        "Building this stage is not an approval of any method."
    )


def _alignment_snapshot(
    data_dir, res: aa.AssumedResult, ctx: dict
) -> tuple[dict | None, str | None]:
    key = aa.snapshot_key(ctx)
    snaps = [s for s in aa.snapshots(data_dir) if aa.snapshot_key(s["context"]) == key]
    if not snaps:
        return None, None
    states = aa.snapshot_states(snaps, {key: ctx})
    snap, state, _ = states[-1]
    return snap, state


def render_actual(data_dir, res: aa.AssumedResult, ctx: dict, m1_approval: ap.Approval) -> None:
    st.subheader("Stored observations: hourly analytical summary")
    st.info(f"**{agp.LIMITATION_BANNER}**")
    method_id = st.radio(
        "Aggregation record",
        [r.id for r in agp.RECORDS],
        format_func=lambda i: f"{i}: {agp.record(i).output_name}",
        key="agg_method",
        help="Only the record chosen here is used; there is no fallback to another method.",
    )
    record = agp.record(method_id)
    snap, state = _alignment_snapshot(data_dir, res, ctx)
    result = ag.aggregate(
        method_id,
        res,
        m1_approval=m1_approval,
        aggregation_approval=ap.status(data_dir, record),
        alignment_snapshot=snap,
        alignment_snapshot_state=state,
        price_lookup=ag.store_price_lookup(data_dir),
    )
    if result.status == ag.APPROVED_COMPLETE:
        st.success(
            md_dollars(
                f"**{result.status}** — {result.output_name}: **{result.output} {result.units}** "
                f"({record.formula})"
            )
        )
    else:
        st.warning(f"**{result.status}** — the summary is withheld.")
        st.markdown(md_dollars("**Blockers:**\n" + "\n".join(f"- {b}" for b in result.blockers)))
    st.table(
        [
            {"Item": "Record", "Value": f"{record.id} {record.version} ({record.method})"},
            {"Item": "Formula", "Value": f"{record.formula} [{record.formula_version}]"},
            {
                "Item": "Output",
                "Value": f"{result.output} {result.units}" if result.output else "withheld",
            },
            {"Item": "M1", "Value": f"{result.m1}; approval {result.m1_approval}"},
            {"Item": "Aggregation approval", "Value": result.aggregation_approval},
            {"Item": "Alignment", "Value": f"{result.alignment_basis}: {result.alignment_status}"},
            {
                "Item": "Alignment snapshot",
                "Value": f"{result.alignment_snapshot or 'none'} ({state or '—'})",
            },
            {"Item": "Revision policy", "Value": result.revision_policy},
            {
                "Item": "Duration evidence",
                "Value": (
                    f"{result.duration_evidence['id']}: {result.duration_evidence['minutes']} "
                    f"minutes for DSTFlag {', '.join(result.duration_evidence['flags'])}"
                )
                if result.duration_evidence
                else "not used by this method",
            },
        ],
        hide_index=True,
    )
    prices = dict(
        zip([i["DeliveryInterval"] for i in result.intervals], result.input_prices, strict=False)
    )
    if result.intervals:
        st.table(
            [
                {
                    "Interval": i["DeliveryInterval"],
                    "DSTFlag": i["DSTFlag"],
                    "Revision": str(i["revision"]),
                    "Document": i["doc_id"],
                    "Price ($/MWh, as published)": prices.get(i["DeliveryInterval"], "—"),
                }
                for i in result.intervals
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
    st.markdown(
        md_dollars(
            "**Never read this as:**\n"
            + "\n".join(f"- {p}" for p in result.prohibited_interpretations)
        )
    )
    st.markdown(md_dollars("**Limitations:**\n" + "\n".join(f"- {t}" for t in result.limitations)))
    render_snapshots(data_dir, result, state)


def render_snapshots(data_dir, result: ag.AggregationResult, alignment_state: str | None) -> None:
    ctx = ag.context(result, alignment_state)
    if st.button("Record an aggregation snapshot", key="agg_snapshot"):
        ag.record_snapshot(data_dir, ag.snapshot(result, ctx, ap.recorded_now()))
    snaps = [
        s for s in ag.snapshots(data_dir) if s["context"]["dam_identity"] == result.dam_identity
    ]
    if not snaps:
        st.markdown("No aggregation snapshot is recorded for this hour.")
        return
    states = ag.snapshot_states(snaps, {ag.snapshot_key(ctx): ctx})
    st.table(
        [
            {
                "Snapshot": s["snapshot_id"],
                "Recorded (UTC)": s["recorded_at_utc"],
                "Status then": s["status"],
                "Output then": f"{s['output']} {s['units']}" if s["output"] else "withheld",
                "State now": st_,
                "Why": "; ".join(why) or "—",
            }
            for s, st_, why in states
        ],
        hide_index=True,
    )
    st.caption(
        "Aggregation snapshots are never deleted or overwritten; a stale one must be recomputed."
    )
