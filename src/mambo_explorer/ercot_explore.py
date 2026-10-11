"""Explore view for direct ERCOT NP6-345-CD actual load by weather zone.

Reads committed ERCOT observations only. It never collects and never joins with EIA data.
Labels are shown exactly as ERCOT writes them (OperDay, HourEnding, DSTFlag), and no UTC
conversion is made because the file does not state a time zone.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import streamlit as st

from mambo_explorer.ercot import collect as ercot
from mambo_explorer.ercot import dataset as ds

STALE_AFTER = timedelta(hours=36)
ENTITIES = (ds.TOTAL, *ds.ZONES)
# Each color has >= 3:1 contrast on both theme backgrounds (tests/test_accessibility.py).
PALETTE = (
    "#1f77b4",
    "#d95f02",
    "#7570b3",
    "#e7298a",
    "#a6761d",
    "#1b9e77",
    "#8c564b",
    "#c51b7d",
    "#238b45",
)
COLORS = dict(zip(ENTITIES, PALETTE, strict=True))

SETUP = """\
```powershell
# ERCOT's public report download needs no account or key.
.venvs/py314/Scripts/mambo sources --source ercot --remote     # list what ERCOT currently publishes
.venvs/py314/Scripts/mambo collect --source ercot --dry-run    # scope and request budget
.venvs/py314/Scripts/mambo collect --source ercot --latest 3   # the 3 most recent daily files
```"""

LIMITATIONS = [
    f"Units: {ds.UNIT_TEXT}",
    "Time labels are ERCOT's own (OperDay, HourEnding, DSTFlag). The file does not state a "
    "time zone, so nothing is converted to UTC, and hours are not placed on a common "
    "timeline with EIA data.",
    "How this report shows the daylight-saving repeated hour (fall) and missing hour "
    "(spring) has not been observed yet. Every row ERCOT sends is kept, labeled with its "
    "DSTFlag, and nothing is merged or invented.",
    "TOTAL is ERCOT's own column. ERCOT does not document it as the sum of the zones; the "
    "difference is shown only as a check.",
    f"ERCOT's public list keeps about {ds.PUBLIC_RETENTION_DAYS} days. Older days are not "
    "available without the registered API.",
    "This is not the same series as EIA-930 'demand' for ERCO. The definitions, timestamp "
    "conventions, and revision timing differ or are unverified, so the two are never joined "
    "or compared here.",
]


def _limitations() -> None:
    st.header("Limitations")
    st.markdown("\n".join(f"- {item}" for item in LIMITATIONS))


def render_ercot(settings) -> None:
    st.caption(
        f"ERCOT {ds.DATASET}, '{ds.REPORT_NAME}', downloaded directly from ERCOT's public "
        f"report list ([product page]({ds.PRODUCT_PAGE}))."
    )
    target = ercot.store(settings.data_dir)
    last = target.last_committed_run()
    if last is None:
        st.info(
            "No ERCOT observations have been collected yet, so there is nothing to show. "
            "Collection runs from the command line, never from this page."
        )
        st.markdown(SETUP)
        _limitations()
        return

    with target.query() as con:
        days = con.execute(
            "SELECT DISTINCT oper_day, oper_date FROM latest ORDER BY oper_date"
        ).fetchall()
    labels = [d[0] for d in days]
    day = st.selectbox(
        "Operating day (ERCOT OperDay, as written)", labels, index=len(labels) - 1, key="ercot_day"
    )
    chosen = st.multiselect(
        "Series",
        list(ENTITIES),
        default=[ds.TOTAL],
        format_func=lambda e: f"{e} — {ds.ZONE_NAMES[e]}",
        key="ercot_zones",
    )

    with target.query() as con:
        rows = con.execute(
            "SELECT row_order, hour_ending, dst_flag, entity, value_raw, value, quality_flags, "
            "zone_sum_minus_total, doc_id, publish_time_raw, "
            "CAST(publication_time_utc AS VARCHAR), CAST(retrieved_at_utc AS VARCHAR), revision "
            "FROM latest WHERE oper_day = ? ORDER BY row_order, entity",
            [day],
        ).fetchall()

    finished = datetime.fromisoformat(last["finished_at"]).astimezone(UTC)
    if datetime.now(UTC) - finished > STALE_AFTER:
        st.warning(
            f"ERCOT data may be stale: the last successful collection finished "
            f"{finished:%Y-%m-%d %H:%M} UTC."
        )

    hours: dict[int, dict] = {}
    for order, hour, flag, entity, raw, _value, _flags, diff, *_ in rows:
        record = hours.setdefault(order, {"HourEnding": hour, "DSTFlag": flag})
        record[entity] = raw if raw is not None else "(missing)"
        if entity == ds.TOTAL:
            record["Zones − TOTAL (check)"] = "—" if diff is None else f"{diff:,.2f}"
    table = [hours[k] for k in sorted(hours)]

    st.header(f"Actual load, OperDay {day}")
    st.caption(
        "Data label: **observed**, as published by ERCOT. The x-axis shows ERCOT's "
        "HourEnding labels in file order, not a converted clock time. The full table is "
        "below the chart."
    )
    if chosen:
        points = [
            {"label": f"{hour} {flag}", "order": order, "series": entity, "value": value}
            for order, hour, flag, entity, raw, value, *_ in rows
            if entity in chosen and value is not None
        ]
        st.vega_lite_chart(
            points,
            {
                "mark": {"type": "line", "point": True},
                "encoding": {
                    "x": {
                        "field": "label",
                        "type": "ordinal",
                        "sort": {"field": "order"},
                        "title": "HourEnding and DSTFlag (as published)",
                    },
                    "y": {"field": "value", "type": "quantitative", "title": f"Load ({ds.UNIT})"},
                    "color": {
                        "field": "series",
                        "type": "nominal",
                        "scale": {"domain": list(chosen), "range": [COLORS[e] for e in chosen]},
                    },
                },
            },
            width="stretch",
            alt=(
                f"Line chart of ERCOT actual load for OperDay {day} ({', '.join(chosen)}) "
                "by HourEnding label. Every value is listed in the table below."
            ),
        )
    else:
        st.info("Select at least one series to chart.")

    present = len(table)
    missing = sum(1 for r in rows if r[4] is None)
    non_numeric = sum(1 for r in rows if "non_numeric" in (r[6] or ""))
    flags = sorted({r["DSTFlag"] for r in table})
    st.header("Coverage")
    message = (
        f"{present} hourly rows for this OperDay (DSTFlag values: {', '.join(flags)}); "
        f"{missing} values missing; {non_numeric} non-numeric."
    )
    if present != 24:
        message += (
            " A typical day has 24 rows. 23 or 25 can occur on daylight-saving days, "
            "but how this report represents them has not been verified."
        )
    (st.warning if present != 24 or missing or non_numeric else st.markdown)(message)
    diffs = [abs(r[7]) for r in rows if r[3] == ds.TOTAL and r[7] is not None]
    if diffs:
        st.markdown(
            f"Largest |zone sum − TOTAL| this day: {max(diffs):,.2f}. A check only; "
            "values are never adjusted."
        )

    st.header("Source and definitions")
    doc_ids = sorted({r[8] for r in rows})
    publish = sorted({(r[9], r[10]) for r in rows})
    retrieved = sorted({r[11] for r in rows})
    revised = sum(1 for r in rows if r[12] > 1)
    st.markdown(
        "\n".join(
            [
                f"- **Report:** ERCOT {ds.DATASET} ({ds.REPORT_NAME}), "
                f"report type {ds.REPORT_TYPE_ID}; "
                f"document(s) {', '.join(doc_ids)}.",
                f"- **Units:** {ds.UNIT_TEXT}",
                f"- **Time labels:** {ds.TIME_TEXT}",
                "- **Published by ERCOT:** "
                + "; ".join(f"{raw} (= {utc[:16]} UTC)" for raw, utc in publish),
                f"- **Retrieved by this computer:** {retrieved[-1][:16]} UTC.",
                f"- **Revisions shown:** {revised} value(s) differ from an earlier stored version.",
            ]
        )
    )

    with st.expander(f"All hours and zones for {day} ({present} rows, as published)"):
        st.table(table, hide_index=True)
    _limitations()
