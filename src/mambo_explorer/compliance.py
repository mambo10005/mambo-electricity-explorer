"""Compliance page: the regulatory responsibility explorer (COMP-02, ADR 0012).

Educational only. Records come from content/responsibilities.yaml (local content; nothing is
fetched). Each entry is a "relevant source to investigate", never an applicability
conclusion. There is no applicability engine, filing, certification, deadline tracking, or
evidence storage.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer import responsibilities, routes
from mambo_explorer.catalog import features
from mambo_explorer.navigation import section_by_key
from mambo_explorer.opf_lab import md_dollars

INVESTIGATE = "Relevant source to investigate"
NOT_A_CONCLUSION = (
    "Every entry below is a **relevant source to investigate**. None of them says that a "
    "rule applies to you or to any organization. That depends on facts this app does not "
    "ask for, on the precise and current text, and on review by a qualified person. A job "
    "title, a market label, or a location is never enough to decide it."
)
LESSONS = (
    ("who-sets-the-rules", "Who sets the rules?"),
    ("requirement-to-evidence", "From a requirement to evidence"),
)


def _date_lines(record: dict) -> list[str]:
    published = record["published_date"] or "not stated in the source"
    if record["status"] == "proposed-change":
        effective = "none: this is a proposal, not an effective requirement"
    elif record["effective_date"] is None:
        effective = "not stated in the source"
    else:
        effective = f"{record['effective_date']} ({record['effective_date_basis']})"
    return [
        f"Published: {published}",
        f"Effective: {effective}",
        f"Retrieved by this project: {record['retrieved_at']} (a retrieval date, not an "
        "effective date)",
    ]


def render_record(cat: responsibilities.Catalog, record: dict) -> None:
    authority = cat.authorities[record["authority_id"]]
    source = cat.sources[record["source_reference"]]
    with st.container(border=True):
        st.markdown(f"#### {INVESTIGATE}: {authority['name']}")
        st.caption(
            f"{cat.organization_types[record['organization_type']]} · "
            f"{cat.statuses[record['status']]} · review: {record['human_review_status']} "
            "(agent-authored, not reviewed by a person)"
        )
        if record["status"] == "proposed-change":
            st.warning("Proposed change: not an effective requirement.")
        st.markdown(
            md_dollars(
                f"**What the source supports (paraphrased):** "
                f"{record['supported_responsibility']}\n\n"
                f"**Scope:** {record['jurisdiction_scope']}\n\n"
                "**Limitations:**\n"
                + "\n".join(f"- {x}" for x in record["explicit_limitations"])
                + f"\n\n**Source:** [{source['title']}]({source['url']}) "
                f"({source['publisher']}). Section: {record['source_section']}. "
                f"Version: {record['source_version']}.\n\n"
                + "\n".join(f"- {line}" for line in _date_lines(record))
            )
        )
        related = record.get("related", [])
        if related:
            st.caption(
                "Related records: "
                + "; ".join(
                    f"{cat.authorities[cat.record(r)['authority_id']]['name']} "
                    f"({cat.statuses[cat.record(r)['status']].split(' (')[0].lower()}, `{r}`)"
                    for r in related
                )
            )


def render_compliance() -> None:
    section = section_by_key("compliance")
    st.title(section.title)
    st.markdown(
        "An **educational explorer** of which official sources describe which "
        "responsibilities in the U.S. electricity sector. It is not legal advice, an "
        "applicability check, a filing or certification tool, or a deadline tracker. Entries "
        "were drafted by an AI agent from the cited sources and have **not been reviewed by a "
        "person**."
    )
    cat = responsibilities.load()
    st.info(NOT_A_CONCLUSION)

    activity = st.radio(
        "Activity",
        list(cat.activities),
        format_func=lambda a: cat.activities[a]["title"],
        key="compliance_activity",
    )
    st.markdown(
        f"**{cat.activities[activity]['title']}:** {cat.activities[activity]['description']}"
    )
    records = cat.for_activity(activity)
    orgs = {r["authority_id"] for r in records}
    if len(orgs) > 1:
        st.markdown(
            f"{len(orgs)} organizations have sources here. More than one can be relevant at "
            "the same time, for different parts of the same activity. The order is not a "
            "ranking."
        )
    for record in records:
        render_record(cat, record)

    questions = [q for q in cat.open_questions if activity in q["activities"]]
    if questions:
        st.subheader("Unresolved questions")
        for q in questions:
            st.warning(md_dollars(q["text"]))

    with st.expander("What the source labels mean"):
        st.markdown("\n".join(f"- **{label}**" for label in cat.statuses.values()))
        st.markdown(
            "A proposed change is never shown as effective. Dates are recorded only when the "
            "source states them; otherwise they read *not stated*."
        )

    st.header("Lessons")
    for lesson_id, title in LESSONS:
        if st.button(f"Open the lesson: {title}", key=f"compliance_lesson_{lesson_id}"):
            st.session_state[routes.HANDOFF_LESSON] = lesson_id
            routes.go("learn", "Learn")

    st.header("Claim-to-source map")
    st.caption(
        f"Record set v{cat.set_version}, sources retrieved {cat.retrieved_at}. One row per "
        "paraphrased claim."
    )
    st.table(
        [
            {
                "Record": r["id"],
                "Organization": cat.authorities[r["authority_id"]]["name"],
                "Activity": cat.activities[r["activity"]]["title"],
                "Source label": cat.statuses[r["status"]].split(" (")[0],
                "Source": cat.sources[r["source_reference"]]["title"],
                "Section": r["source_section"],
            }
            for r in cat.records
        ],
        hide_index=True,
    )
    st.header("Sources that could not be read")
    st.markdown(
        "Human-verification pages were not bypassed. Where an official source could not be "
        "read, the content was narrowed instead."
    )
    st.table(
        [{"Source": g["source"], "What happened": g["outcome"]} for g in cat.source_gaps],
        hide_index=True,
    )
    st.header("Status of Compliance features")
    st.table(
        [
            {"ID": f["id"], "Feature": f["name"], "Status": f["status"]}
            for f in features()
            if f["section"] == "compliance"
        ],
        hide_index=True,
    )
