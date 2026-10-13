"""Views for ERCOT NP6-905-CD real-time Settlement Point Prices at HB_NORTH (Stage 20, ADR 0017).

Reads committed observations only; never collects. Every interval is labelled with ERCOT's own
DeliveryDate, DeliveryHour, DeliveryInterval, and DSTFlag on an ordinal axis in publication
order; the report states no time zone, so nothing is placed on a clock-time axis. Prices are
signed as published; a missing price or an absent interval is never filled. Nothing here joins
these prices with day-ahead prices or EIA data, or explains why a price moved.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import streamlit as st

from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.opf_lab import md_dollars
from mambo_explorer.timeview import format_utc

SETUP = """\
```powershell
# ERCOT's public report download needs no account or key.
.venvs/py314/Scripts/mambo sources --source ercot-rt-spp             # reviewed contract
.venvs/py314/Scripts/mambo collect --source ercot-rt-spp --dry-run   # scope and budget
.venvs/py314/Scripts/mambo collect --source ercot-rt-spp --latest 4  # newest 4 intervals
```"""
LIMITATIONS = [
    f"One market stage ({rt.MARKET_STAGE}) at one settlement point: {rt.LOCATION}, "
    f"{rt.LOCATION_NAME}. Each downloaded document holds every settlement point for one "
    f"15-minute interval; only {rt.LOCATION} is stored.",
    f"Units: {rt.UNIT_TEXT}",
    f"Time labels: {rt.TIME_TEXT}",
    f"Finality: {rt.FINALITY_TEXT}",
    "Prices are shown as published, including negative values. A missing price is missing; an "
    "interval that is not stored is absent. Neither is ever filled or interpolated.",
    "Nothing here explains why a price was high or low; causes are not in this data.",
    "These prices are not compared with the day-ahead price or joined with EIA-930 data; see "
    "the comparison prerequisites in docs/calculations.md.",
    f"ERCOT's public list keeps about {rt.PUBLIC_RETENTION_DAYS} days; older intervals are "
    "not available through the access method this app implements.",
]


@dataclass(frozen=True)
class RtInterval:
    label: str  # "H01 I1 N" — DeliveryHour, DeliveryInterval, DSTFlag as published
    hour: str
    interval: str
    dst_flag: str
    order: int  # publication order within the selection
    value: float | None
    value_raw: str | None
    flags: str
    revision: int
    doc_id: str
    friendly_name: str
    publish_time_raw: str
    retrieved_at: str
    downloaded_points: int


def delivery_days(target) -> list[str]:
    if not target.committed_files("observations"):
        return []
    with target.query() as con:
        rows = con.execute(
            "SELECT DISTINCT delivery_date_raw, delivery_date FROM latest ORDER BY delivery_date"
        ).fetchall()
    return [r[0] for r in rows]


def label(hour: str, interval: str, flag: str) -> str:
    return f"H{int(hour):02d} I{interval} {flag}"


def load_day(target, day: str) -> list[RtInterval]:
    with target.query() as con:
        rows = con.execute(
            "SELECT delivery_hour, delivery_interval, dst_flag, value, value_raw, "
            "quality_flags, revision, doc_id, doc_friendly_name, publish_time_raw, "
            "CAST(retrieved_at_utc AS VARCHAR), downloaded_settlement_points FROM latest "
            "WHERE delivery_date_raw = ? ORDER BY publication_time_utc, "
            "CAST(delivery_hour AS INTEGER), CAST(delivery_interval AS INTEGER), dst_flag",
            [day],
        ).fetchall()
    return [
        RtInterval(label(h, i, f), h, i, f, n, v, raw, fl or "", rev, doc, fr, pub, ret, pts)
        for n, (h, i, f, v, raw, fl, rev, doc, fr, pub, ret, pts) in enumerate(rows, start=1)
    ]


def revision_history(target, day: str) -> list[dict]:
    with target.query() as con:
        rows = con.execute(
            "SELECT delivery_hour, delivery_interval, dst_flag, revision, value_raw, doc_id, "
            "publish_time_raw FROM observations WHERE delivery_date_raw = ? AND revision > 0 "
            "ORDER BY CAST(delivery_hour AS INTEGER), CAST(delivery_interval AS INTEGER), "
            "dst_flag, revision",
            [day],
        ).fetchall()
    return [
        {
            "Interval (as published)": label(h, i, f),
            "Revision": r,
            "Price": raw or "(missing)",
            "Document": d,
            "Published by ERCOT": p,
        }
        for h, i, f, r, raw, d, p in rows
    ]


def snapshot_id(day: str, intervals: list[RtInterval]) -> str:
    payload = json.dumps(
        [rt.DATASET, rt.LOCATION, day, [(x.label, x.revision, x.value_raw) for x in intervals]],
        separators=(",", ":"),
    )
    return "rtprice-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def coverage(intervals: list[RtInterval]) -> dict:
    valid = [x for x in intervals if x.value is not None]
    hours = sorted({int(x.hour) for x in intervals})
    by_hour = {h: sum(1 for x in intervals if int(x.hour) == h) for h in hours}
    return {
        "stored": len(intervals),
        "valid": len(valid),
        "missing": sum(1 for x in intervals if x.value is None),
        "negative": sum(1 for x in valid if x.value < 0),
        "revised": sum(1 for x in intervals if x.revision > 1),
        "dst_flags": sorted({x.dst_flag for x in intervals}),
        "hours_with_fewer_than_4": [h for h, n in by_hour.items() if n < 4],
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


def render_day(target, day: str, key: str) -> list[RtInterval]:
    intervals = load_day(target, day)
    st.caption(
        md_dollars(
            f"Data label: **observed**, as published by ERCOT. Real-time Settlement Point Price "
            f"at {rt.LOCATION} ({rt.LOCATION_NAME}), in {rt.UNIT}, one point per stored "
            f"{rt.INTERVAL_MINUTES}-minute interval. The x axis shows ERCOT's labels "
            "(H = DeliveryHour, I = DeliveryInterval, then DSTFlag) in publication order, not a "
            "clock time; the tooltip, the interval viewer, and the table use the same labels."
        )
    )
    points = [
        {"label": x.label, "order": x.order, "price": x.value, "revision": x.revision}
        for x in intervals
        if x.value is not None
    ]
    if points:
        st.vega_lite_chart(
            points,
            {
                "layer": [
                    {"mark": {"type": "rule", "color": "#888888"}, "encoding": {"y": {"datum": 0}}},
                    {
                        "mark": {"type": "line", "point": True, "color": "#d95f02"},
                        "encoding": {
                            "x": {
                                "field": "label",
                                "type": "ordinal",
                                "sort": {"field": "order"},
                                "title": "DeliveryHour, DeliveryInterval, DSTFlag (as published)",
                            },
                            "y": {
                                "field": "price",
                                "type": "quantitative",
                                "title": f"Price ({rt.UNIT})",
                            },
                            "tooltip": [
                                {
                                    "field": "label",
                                    "type": "nominal",
                                    "title": "Interval (as published)",
                                },
                                {
                                    "field": "price",
                                    "type": "quantitative",
                                    "title": f"Price ({rt.UNIT})",
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

    c = coverage(intervals)
    message = (
        f"{c['stored']} {rt.INTERVAL_MINUTES}-minute intervals stored for {rt.LOCATION} on "
        f"DeliveryDate {day} (DSTFlag values: {', '.join(c['dst_flags'])}); {c['missing']} "
        f"missing prices; {c['negative']} negative; {c['revised']} revised since first stored."
    )
    if c["hours_with_fewer_than_4"]:
        message += (
            f" Hours with fewer than four stored intervals: "
            f"{', '.join(str(h) for h in c['hours_with_fewer_than_4'])}. An interval that is "
            "not stored may not be published yet, may not have been collected, or may be "
            "outside ERCOT's public list; it is never filled."
        )
    (st.warning if c["missing"] or c["hours_with_fewer_than_4"] else st.markdown)(
        md_dollars(message)
    )

    if intervals:
        st.markdown("**Interval viewer**")
        chosen = st.selectbox(
            "Choose an interval (ERCOT labels)",
            list(range(len(intervals))),
            index=len(intervals) - 1,
            format_func=lambda i: intervals[i].label,
            key=f"{key}_interval",
        )
        x = intervals[chosen]
        st.table(
            [
                {"Item": "Interval (as published)", "Value": x.label},
                {
                    "Item": "DeliveryDate / DeliveryHour / DeliveryInterval / DSTFlag",
                    "Value": f"{day} / {x.hour} / {x.interval} / {x.dst_flag}",
                },
                {"Item": f"Price ({rt.UNIT})", "Value": _fmt(x.value)},
                {"Item": "Flags", "Value": x.flags or "none"},
                {"Item": "Revision", "Value": str(x.revision)},
                {"Item": "Document (ERCOT name)", "Value": f"{x.doc_id} ({x.friendly_name})"},
                {"Item": "Published by ERCOT", "Value": x.publish_time_raw},
                {"Item": "Retrieved by this computer", "Value": format_utc(x.retrieved_at)},
                {
                    "Item": "Settlement points in the downloaded document",
                    "Value": str(x.downloaded_points),
                },
            ],
            hide_index=True,
        )
    with st.expander(f"All stored intervals for {day} ({len(intervals)} rows)"):
        st.table(
            [
                {
                    "Interval (as published)": x.label,
                    f"Price ({rt.UNIT})": _fmt(x.value),
                    "Flags": x.flags,
                    "Revision": x.revision,
                    "Published by ERCOT": x.publish_time_raw,
                }
                for x in intervals
            ],
            hide_index=True,
        )
    with st.expander("Revision provenance (every stored version of these intervals)"):
        st.table(revision_history(target, day), hide_index=True)
    st.markdown(
        md_dollars(
            f"- **Report:** ERCOT {rt.DATASET}, '{rt.REPORT_NAME}' (report type "
            f"{rt.REPORT_TYPE_ID}; [product page]({rt.PRODUCT_PAGE})).\n"
            f"- **This price:** {rt.PRICE_DEFINITION}\n"
            f"- **Finality:** {rt.FINALITY_TEXT}"
        )
    )
    return intervals


def render_rt_prices(settings) -> None:
    st.caption(
        md_dollars(
            f"ERCOT {rt.DATASET}, '{rt.REPORT_NAME}', downloaded directly from ERCOT's public "
            f"report list. Stored location: {rt.LOCATION}."
        )
    )
    target = rt.store(settings.data_dir)
    if target.last_committed_run() is None or not delivery_days(target):
        st.info(
            "No ERCOT real-time prices have been collected yet, so there is nothing to show. "
            "Collection runs from the command line, never from this page."
        )
        st.markdown(SETUP)
        _definitions()
        return
    day = day_picker(target, "explore_rt_day")
    st.header(f"Real-time price at {rt.LOCATION}, DeliveryDate {day}")
    render_day(target, day, "explore_rt")
    _definitions()


def _definitions() -> None:
    st.header("What this price is, and is not")
    st.markdown(
        md_dollars(
            f"- **This price:** {rt.PRICE_DEFINITION}\n" + "\n".join(f"- {t}" for t in rt.NOT_THIS)
        )
    )
    st.header("Limitations")
    st.markdown(md_dollars("\n".join(f"- {t}" for t in LIMITATIONS)))
