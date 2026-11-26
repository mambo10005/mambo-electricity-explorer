"""Governance section of System Health (Stage 26, ADR 0023). Read-only.

Shows the five governed records, their states and activation, dependencies, governed settings,
evidence state (never a reviewer's name), limitation acknowledgments, stale downstream snapshots,
re-review triggers, and each review package. Viewing, expanding, or navigating here writes
nothing: decisions are recorded only through `mambo governance … --execute`.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer.ercot import governance as gv
from mambo_explorer.opf_lab import md_dollars

STATE_TEXT = {
    gv.MISSING: "no decision recorded",
    gv.UNDER_REVIEW: "under review (an explicit no-decision was recorded)",
    gv.APPROVED_INACTIVE: "approved, not operationally active",
    gv.ACTIVE: "approved and operationally active",
    gv.REJECTED: "rejected",
    gv.REVISION_REQUESTED: "revision requested",
    gv.REVOKED: "approval revoked",
    gv.SUPERSEDED: "superseded",
    gv.INCOMPATIBLE: "approval incompatible with the current record",
    gv.EVIDENCE_UNAVAILABLE: "evidence currently unavailable",
    gv.RE_REVIEW_REQUIRED: "re-review required",
}


def render_governance(data_dir) -> None:
    st.header("Governance of the price-comparison assumptions")
    st.info(
        "**Read-only.** Nothing on this page approves, rejects, revokes, or changes a setting. "
        "Decisions are recorded locally with `mambo governance … --execute`, stay outside Git, "
        "and name the reviewer in the local file only."
    )
    settings = gv.current_settings(data_dir)
    states = gv.states(data_dir, settings)
    st.subheader("Records")
    st.table(
        [
            {
                "Record": f"{s.id} {s.version}",
                "State": s.state,
                "Activation": s.activation,
                "Depends on": ", ".join(s.dependencies) or "—",
                "Selected": "—" if s.selected is None else ("yes" if s.selected else "no"),
                "Acknowledgment": s.acknowledgment,
                "Evidence": s.evidence_state,
            }
            for s in states.values()
        ],
        hide_index=True,
    )
    st.caption(
        "States: " + "; ".join(f"{k} = {v}" for k, v in STATE_TEXT.items()) + ". "
        "'Acknowledgment: fingerprint-only' marks approvals recorded before itemized "
        "acknowledgment existed; they accepted the same limitation text by fingerprint."
    )
    st.subheader("Governed settings")
    st.table(
        [
            {
                "Setting": "Active comparison convention",
                "Value": settings["active_comparison_convention"] or "none set",
                "Record": settings["references"].get("active_comparison_convention", "—"),
            },
            {
                "Setting": "Active aggregation method",
                "Value": settings["active_aggregation_method"] or "none set",
                "Record": settings["references"].get("active_aggregation_method", "—"),
            },
            {
                "Setting": "Revision policy",
                "Value": settings["revision_policy"] or "none set",
                "Record": settings["references"].get("revision_policy", "—"),
            },
        ],
        hide_index=True,
    )
    st.markdown(
        "An unset setting withholds the corresponding output. At most one comparison "
        "convention and one aggregation method are active for HB_NORTH; changing either, or "
        "the revision policy, marks downstream snapshots stale (they are kept)."
    )
    st.subheader("Blockers and stale downstream outputs")
    rows = [{"Record": s.id, "Blocker": b} for s in states.values() for b in s.blockers] or [
        {"Record": "—", "Blocker": "none"}
    ]
    st.table(rows, hide_index=True)
    stale = gv.stale_downstream(data_dir, settings)
    st.table(
        [
            {"Snapshots": k, "Recorded": v["total"], "Stale under current governance": v["stale"]}
            for k, v in stale.items()
        ],
        hide_index=True,
    )
    st.subheader("Evidence references")
    st.table(
        [
            {
                "Record": s.id,
                "Approval": s.approval_reference or "—",
                "Evidence state": s.evidence_state,
                "Reference": (
                    "(local file; path withheld)"
                    if s.evidence_state in ("available", gv.EVIDENCE_UNAVAILABLE)
                    else (s.evidence_reference or "—")
                ),
            }
            for s in states.values()
        ],
        hide_index=True,
    )
    st.subheader("Review packages")
    for rid in gv.RECORDS:
        pkg = gv.review_package(data_dir, rid, settings)
        with st.expander(f"{rid} {pkg['version']}: {pkg['state']} ({pkg['activation']})"):
            st.markdown(
                md_dollars(
                    "**Facts a reviewer must see:**\n" + "\n".join(f"- {f}" for f in pkg["facts"])
                )
            )
            st.markdown(md_dollars(f"**Rule or formula:** {pkg['rule_or_formula']}"))
            if pkg["sign_convention"]:
                st.markdown(f"**Sign convention:** {pkg['sign_convention']}")
            st.markdown(f"**Scope:** {pkg['scope']} (fingerprint {pkg['scope_fingerprint']})")
            st.table(pkg["limitations"], hide_index=True)
            st.caption(
                f"Limitations version {pkg['limitations_version']}; every id must be acknowledged."
            )
            st.markdown(
                md_dollars(
                    "**Authoritative evidence:**\n"
                    + ("\n".join(f"- {e}" for e in pkg["authoritative_evidence"]) or "- none")
                    + "\n\n**Empirical evidence:**\n"
                    + ("\n".join(f"- {e}" for e in pkg["empirical_evidence"]) or "- none")
                    + "\n\n**Unresolved semantics:**\n"
                    + "\n".join(f"- {u}" for u in pkg["unresolved_semantics"])
                    + "\n\n**Allowed uses:**\n"
                    + "\n".join(f"- {u}" for u in pkg["allowed_uses"])
                    + "\n\n**Prohibited uses:**\n"
                    + "\n".join(f"- {u}" for u in pkg["prohibited_uses"])
                    + "\n\n**Known failure modes:**\n"
                    + "\n".join(f"- {u}" for u in pkg["known_failure_modes"])
                    + "\n\n**Re-review triggers:**\n"
                    + "\n".join(f"- {u}" for u in pkg["re_review_triggers"])
                    + f"\n\n**Validation evidence:** {pkg['validation_evidence']}"
                    + f"\n\n**Downstream records:** {', '.join(pkg['downstream']) or 'none'}"
                )
            )
            st.code(
                f"mambo governance review {rid}   # prints the exact approve command with every "
                "fingerprint and limitation id",
                language="powershell",
            )
