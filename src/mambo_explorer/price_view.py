"""Views for ERCOT NP4-190-CD DAM Settlement Point Prices at HB_NORTH (Stage 19, ADR 0016).

Reads committed observations only; never collects. Labels stay ERCOT's own (DeliveryDate,
HourEnding, DSTFlag) on an ordinal axis in file order, because the report states no time zone.
Prices are signed as published; a missing price is shown as missing. Nothing here joins these
prices with EIA demand or generation, explains why a price moved, or calls a price final.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import streamlit as st

from mambo_explorer.ercot import prices as px
from mambo_explorer.opf_lab import md_dollars
from mambo_explorer.timeview import format_utc

SETUP = """\
```powershell
# ERCOT's public report download needs no account or key.
.venvs/py314/Scripts/mambo sources --source ercot-dam-spp             # reviewed contract
.venvs/py314/Scripts/mambo collect --source ercot-dam-spp --dry-run   # scope and budget
.venvs/py314/Scripts/mambo collect --source ercot-dam-spp --latest 2  # 2 latest DAM runs
```"""
LIMITATIONS = [
    f"One market stage ({px.MARKET_STAGE}) at one settlement point: {px.LOCATION}, "
    f"{px.LOCATION_NAME}. Each downloaded document holds every settlement point; only "
    f"{px.LOCATION} is stored.",
    f"Units: {px.UNIT_TEXT}",
    f"Time labels: {px.TIME_TEXT}",
    f"Finality: {px.FINALITY_TEXT}",
    "Prices are shown as published, including negative values. A missing price is missing, "
    "never zero.",
    "Nothing here explains why a price was high or low; causes are not in this data.",
    "These prices are never joined with EIA-930 demand or generation: the two sources' hour "
    "labels have not been shown to describe the same intervals.",
    f"ERCOT's public list keeps about {px.PUBLIC_RETENTION_DAYS} days; older DeliveryDates "
    "are not available through the access method this app implements.",
]


@dataclass(frozen=True)
class PriceHour:
    label: str  # "HH:00 F" — HourEnding and DSTFlag as published
    hour_ending: str
    dst_flag: str
    row_order: int
    value: float | None
    value_raw: str | None
    flags: str
    revision: int
    doc_id: str
    publish_time_raw: str
    retrieved_at: str
    run_id: str


def delivery_days(target) -> list[str]:
    if not target.committed_files("observations"):
        return []
    with target.query() as con:
        rows = con.execute(
            "SELECT DISTINCT delivery_date_raw, delivery_date FROM latest ORDER BY delivery_date"
        ).fetchall()
    return [r[0] for r in rows]


def load_day(target, day: str) -> list[PriceHour]:
    with target.query() as con:
        rows = con.execute(
            "SELECT hour_ending, dst_flag, row_order, value, value_raw, quality_flags, revision, "
            "doc_id, publish_time_raw, CAST(retrieved_at_utc AS VARCHAR), run_id FROM latest "
            "WHERE delivery_date_raw = ? ORDER BY row_order",
            [day],
        ).fetchall()
    return [
        PriceHour(f"{h} {f}", h, f, o, v, raw, fl or "", rev, doc, pub, ret, run)
        for h, f, o, v, raw, fl, rev, doc, pub, ret, run in rows
    ]


def revision_history(target, day: str) -> list[dict]:
    """Every stored revision for the day's hours (oldest first): the provenance trail."""
    with target.query() as con:
        rows = con.execute(
            "SELECT hour_ending, dst_flag, revision, value_raw, doc_id, publish_time_raw "
            "FROM observations WHERE delivery_date_raw = ? AND revision > 0 "
            "ORDER BY row_order, revision",
            [day],
        ).fetchall()
    return [
        {
            "HourEnding": h,
            "DSTFlag": f,
            "Revision": r,
            "Price": raw or "(missing)",
            "Document": d,
            "Published by ERCOT": p,
        }
        for h, f, r, raw, d, p in rows
    ]


def snapshot_id(day: str, hours: list[PriceHour]) -> str:
    """Stable fingerprint of one DeliveryDate's stored prices; any revision changes it."""
    payload = json.dumps(
        [px.DATASET, px.LOCATION, day, [(h.label, h.revision, h.value_raw) for h in hours]],
        separators=(",", ":"),
    )
    return "price-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def coverage(hours: list[PriceHour]) -> dict:
    valid = [h for h in hours if h.value is not None]
    return {
        "rows": len(hours),
        "valid": len(valid),
        "missing": sum(1 for h in hours if h.value is None),
        "negative": sum(1 for h in valid if h.value < 0),
        "dst_flags": sorted({h.dst_flag for h in hours}),
        "revised": sum(1 for h in hours if h.revision > 1),
    }


def _fmt(value: float | None) -> str:
    return "(missing)" if value is None else f"{value:,.2f}"


def day_picker(target, key: str) -> str | None:
    days = delivery_days(target)
    if not days:
        return None
    return st.selectbox(
        "Delivery date (ERCOT DeliveryDate, as written)", days, index=len(days) - 1, key=key
    )


def render_day(target, day: str, key: str) -> list[PriceHour]:
    """Chart, accessible table, coverage, provenance for one DeliveryDate."""
    hours = load_day(target, day)
    st.caption(
        md_dollars(
            f"Data label: **observed**, as published by ERCOT. "
            f"{px.MARKET_STAGE.capitalize()} Settlement Point Price at {px.LOCATION} "
            f"({px.LOCATION_NAME}), in {px.UNIT}. The x axis shows ERCOT's HourEnding and "
            "DSTFlag labels in file order, not a converted clock time; the tooltip and the "
            "table below use the same labels."
        )
    )
    points = [
        {"label": h.label, "order": h.row_order, "price": h.value, "revision": h.revision}
        for h in hours
        if h.value is not None
    ]
    if points:
        st.vega_lite_chart(
            points,
            {
                "layer": [
                    {"mark": {"type": "rule", "color": "#888888"}, "encoding": {"y": {"datum": 0}}},
                    {
                        "mark": {"type": "line", "point": True, "color": "#1f77b4"},
                        "encoding": {
                            "x": {
                                "field": "label",
                                "type": "ordinal",
                                "sort": {"field": "order"},
                                "title": "HourEnding and DSTFlag (as published)",
                            },
                            "y": {
                                "field": "price",
                                "type": "quantitative",
                                "title": f"Price ({px.UNIT})",
                            },
                            "tooltip": [
                                {
                                    "field": "label",
                                    "type": "nominal",
                                    "title": "HourEnding DSTFlag (as published)",
                                },
                                {
                                    "field": "price",
                                    "type": "quantitative",
                                    "title": f"Price ({px.UNIT})",
                                    "format": ",.2f",
                                },
                                {"field": "revision", "type": "quantitative", "title": "Revision"},
                            ],
                        },
                    },
                ]
            },
            width="stretch",
            key=f"{key}_chart",
        )
    else:
        st.info("No valid prices for this DeliveryDate.")
    c = coverage(hours)
    message = (
        f"{c['rows']} hourly rows for {px.LOCATION} on DeliveryDate {day} (DSTFlag values: "
        f"{', '.join(c['dst_flags'])}); {c['missing']} missing; {c['negative']} negative; "
        f"{c['revised']} revised since first stored."
    )
    if c["rows"] != 24:
        message += (
            " A typical day has 24 rows. 23 or 25 can occur on daylight-saving days, but how "
            "this report represents them has not been observed."
        )
    (st.warning if c["rows"] != 24 or c["missing"] else st.markdown)(md_dollars(message))
    st.table(
        [
            {
                "HourEnding": h.hour_ending,
                "DSTFlag": h.dst_flag,
                f"Price ({px.UNIT})": _fmt(h.value),
                "Flags": h.flags,
                "Revision": h.revision,
            }
            for h in hours
        ],
        hide_index=True,
    )
    docs = sorted({(h.doc_id, h.publish_time_raw) for h in hours})
    retrieved = max((h.retrieved_at for h in hours), default=None)
    st.markdown(
        md_dollars(
            "\n".join(
                [
                    f"- **Report:** ERCOT {px.DATASET}, '{px.REPORT_NAME}' (report type "
                    f"{px.REPORT_TYPE_ID}; [product page]({px.PRODUCT_PAGE})).",
                    "- **Published by ERCOT (listing PublishDate):** "
                    + "; ".join(f"document {d} at {p}" for d, p in docs),
                    f"- **Retrieved by this computer:** {format_utc(retrieved)}.",
                    f"- **Finality:** {px.FINALITY_TEXT}",
                ]
            )
        )
    )
    with st.expander("Revision provenance (every stored version of these hours)"):
        st.table(revision_history(target, day), hide_index=True)
    return hours


def render_prices(settings) -> None:
    st.caption(
        md_dollars(
            f"ERCOT {px.DATASET}, '{px.REPORT_NAME}', downloaded directly from ERCOT's public "
            f"report list. Stored location: {px.LOCATION}."
        )
    )
    target = px.store(settings.data_dir)
    if target.last_committed_run() is None or not delivery_days(target):
        st.info(
            "No ERCOT day-ahead prices have been collected yet, so there is nothing to show. "
            "Collection runs from the command line, never from this page."
        )
        st.markdown(SETUP)
        _definitions()
        return
    day = day_picker(target, "explore_price_day")
    st.header(f"Day-ahead price at {px.LOCATION}, DeliveryDate {day}")
    render_day(target, day, "explore_price")
    _definitions()


def _definitions() -> None:
    st.header("What this price is, and is not")
    st.markdown(
        md_dollars(
            f"- **This price:** {px.DEFINITION_TEXT}\n" + "\n".join(f"- {t}" for t in px.NOT_THIS)
        )
    )
    st.header("Limitations")
    st.markdown(md_dollars("\n".join(f"- {t}" for t in LIMITATIONS)))
