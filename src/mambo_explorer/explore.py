"""Explore page: EIA-930 actual demand vs. source-published day-ahead forecast.

Reads committed observations only. It never triggers collection, so opening or
re-running the page sends no requests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import streamlit as st

from mambo_explorer.config import ConfigError, load_settings
from mambo_explorer.eia import dataset as ds
from mambo_explorer.navigation import section_by_key
from mambo_explorer.storage import Store
from mambo_explorer.timeview import format_utc, utc_label_chart

STALE_AFTER = timedelta(hours=36)
SOURCES = {
    "eia": "EIA-930 via EIA API (ERCO demand and day-ahead forecast)",
    "ercot": "ERCOT direct: NP6-345-CD actual load by weather zone",
    "eia-generation": "EIA-930 via EIA API (ERCO net generation by energy source)",
    "ercot-dam-spp": "ERCOT direct: NP4-190-CD day-ahead settlement point price (HB_NORTH)",
}

SETUP_INSTRUCTIONS = """\
```powershell
# 1. Put your free EIA key in .env (gitignored) or the environment: EIA_API_KEY=...
# 2. Preview scope and request budget (no key needed, nothing sent):
.venvs/py314/Scripts/mambo collect --dry-run
# 3. Collect the last 7 completed UTC days:
.venvs/py314/Scripts/mambo collect
```"""

LIMITATIONS = [
    "One balancing authority (ERCOT, EIA code ERCO) and two series only.",
    "The forecast is the day-ahead demand forecast that the balancing authority "
    "reports to EIA. This application does not produce forecasts.",
    "Only the forecast values EIA currently publishes are stored. Earlier versions "
    "of a forecast, and when each value was issued, are not reconstructed.",
    "EIA does not provide a publication time or a preliminary/final flag per value. "
    "'Retrieved' is when this computer downloaded the data, not when EIA published it.",
    "EIA-930 values can be revised after release. Revisions are detected only for "
    "days that are re-collected.",
    "Missing values are shown as gaps, never filled in.",
]


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def render_explore() -> None:
    section = section_by_key("explore")
    st.title(section.title)
    st.markdown(section.summary)

    try:
        settings = load_settings()
    except ConfigError as exc:
        st.error(f"Unsafe data directory configuration: {exc}")
        return
    source = st.radio(
        "Source",
        list(SOURCES),
        format_func=SOURCES.get,
        key="explore_source",
        help="The sources are shown separately and are never joined or compared.",
    )
    if source == "ercot":
        from mambo_explorer.ercot_explore import render_ercot

        render_ercot(settings)
        return
    if source == "eia-generation":
        from mambo_explorer.generation_explore import render_generation

        render_generation(settings)
        return
    if source == "ercot-dam-spp":
        from mambo_explorer.price_view import render_prices

        render_prices(settings)
        return
    _render_eia(settings)


def _render_eia(settings) -> None:
    """EIA-930 view (Stage 3), unchanged apart from being selectable."""
    store = Store(settings.data_dir)
    last = store.last_committed_run()

    if last is None:
        st.info(
            "No observations have been collected yet, so there is nothing to chart. "
            "Collection runs from the command line, never from this page."
        )
        st.markdown(SETUP_INSTRUCTIONS)
        _limitations()
        return

    with store.query() as con:
        entities = con.execute(
            "SELECT entity, any_value(entity_name) FROM latest GROUP BY entity ORDER BY entity"
        ).fetchall()
        first, last_period = con.execute("SELECT min(period), max(period) FROM latest").fetchone()

    names = dict(entities)
    entity = st.selectbox(
        "Balancing authority",
        list(names),
        format_func=lambda e: f"{e} — {names[e] or ds.ENTITY_NAMES.get(e, '')}",
    )
    first_day = ds.parse_period(first).date()
    last_day = ds.parse_period(last_period).date()
    picked = st.date_input(
        "UTC days (by the source's period label)",
        value=(max(first_day, last_day - timedelta(days=6)), last_day),
        min_value=first_day,
        max_value=last_day,
    )
    if not isinstance(picked, tuple) or len(picked) != 2:
        st.info("Select a start and an end day.")
        return
    start_day, end_day = picked
    start_p, end_p = f"{start_day.isoformat()}T00", f"{end_day.isoformat()}T23"

    with store.query() as con:
        chart = con.execute(
            "SELECT period, metric, value FROM latest WHERE entity = ? AND period BETWEEN ? "
            "AND ? AND value IS NOT NULL ORDER BY period, metric",
            [entity, start_p, end_p],
        ).fetchall()
        table = con.execute(
            """
            SELECT period, metric, value_raw, value, unit, quality_flags, revision,
                   interval_start_utc, interval_end_utc, retrieved_at_utc, run_id
            FROM latest WHERE entity = ? AND period BETWEEN ? AND ?
            ORDER BY period, metric
            """,
            [entity, start_p, end_p],
        ).to_arrow_table()
        stats = [
            tuple(row.values())
            for row in con.execute(
                """
                SELECT metric, count(*) AS rows, count(*) FILTER (WHERE value IS NULL) AS missing,
                       min(retrieved_at_utc), max(retrieved_at_utc), string_agg(DISTINCT unit, ', ')
                FROM latest WHERE entity = ? AND period BETWEEN ? AND ? GROUP BY metric
                """,
                [entity, start_p, end_p],
            )
            .to_arrow_table()
            .to_pylist()
        ]

    finished = _parse_ts(last["finished_at"])
    if datetime.now(UTC) - finished > STALE_AFTER:
        st.warning(
            f"Data may be stale: the last successful collection finished "
            f"{finished:%Y-%m-%d %H:%M} UTC, more than {STALE_AFTER.total_seconds() / 3600:.0f} "
            "hours ago."
        )

    st.header("Actual demand vs. day-ahead forecast")
    st.caption(
        "Data label: **observed**. Both series are values reported to and published by EIA. "
        "The forecast was made by the balancing authority, not by this application."
    )
    # Blue vs. dark orange: >= 3:1 contrast on both theme backgrounds (WCAG 1.4.11; see
    # tests/test_accessibility.py) and distinguishable for common color-vision
    # deficiencies (Streamlit's default palette draws both series in similar blues).
    utc_label_chart(
        [{"period": p, "Series": ds.DISPLAY_NAMES[m], "Value (MWh)": v} for p, m, v in chart],
        value_field="Value (MWh)",
        value_title="Value (MWh)",
        series_field="Series",
        series_domain=[ds.DISPLAY_NAMES["D"], ds.DISPLAY_NAMES["DF"]],
        colors=["#1f77b4", "#d95f02"],
        key="explore_demand_chart",
        alt_text=(
            "Line chart of hourly actual demand and day-ahead forecast by UTC period label; "
            "the tooltip and the table below show the same label. Gaps mean no valid value."
        ),
    )

    expected = ((end_day - start_day).days + 1) * 24
    by_metric = {row[0]: row for row in stats}
    st.header("Completeness")
    for metric in ds.METRICS:
        rows = by_metric.get(metric, (metric, 0, 0, None, None, None))
        absent = expected - rows[1]
        message = (
            f"**{ds.DISPLAY_NAMES[metric]}**: {rows[1]} of {expected} hours present; "
            f"{rows[2]} reported without a value; {absent} hours absent from the source."
        )
        (st.warning if rows[2] or absent else st.markdown)(message)

    st.header("Source and definitions")
    units = sorted({r[5] for r in stats if r[5]})
    retrieved = [r[4] for r in stats if r[4]]
    st.markdown(
        "\n".join(
            [
                f"- **Source:** U.S. Energy Information Administration, {ds.DATASET} "
                f"(API route `{ds.ROUTE}`, frequency `{ds.FREQUENCY}`).",
                f"- **Units (as reported):** {', '.join(units) or 'none'}.",
                f"- **Interval:** {ds.INTERVAL_TEXT}",
                f"- **Retrieved (by this computer):** {format_utc(max(retrieved))}."
                if retrieved
                else "- **Retrieved:** unknown.",
                f"- **Last successful collection:** {format_utc(finished)} "
                f"(run `{last['run_id']}`).",
                "- **Publication time:** not provided by the source.",
            ]
        )
    )

    with st.expander("Underlying observations (latest revision of each hour)"):
        st.dataframe(table, hide_index=True)

    _limitations()


def _limitations() -> None:
    st.header("Limitations")
    st.markdown("\n".join(f"- {item}" for item in LIMITATIONS))
