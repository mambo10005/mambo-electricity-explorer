"""System Health page (HEALTH-01, ADR 0013). Read-only: it never collects, sends a request,
repairs storage, or changes a file. Collection runs only from `mambo refresh` / `mambo collect`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from mambo_explorer import generation, health, refresh, refresh_config
from mambo_explorer.catalog import features
from mambo_explorer.config import ConfigError, load_settings
from mambo_explorer.ercot import collect as ercot_collect
from mambo_explorer.ercot import prices as ercot_prices
from mambo_explorer.ercot import rt_prices as ercot_rt
from mambo_explorer.storage import Store

# Replaceable clock (tests use a fixed time; nothing depends on today's date).
NOW = lambda: datetime.now(UTC)  # noqa: E731

SNAPSHOT_NOTE = (
    "Regulatory content is a snapshot. The responsibility records and lessons were checked "
    "against their sources on the dates shown, and nothing in this app watches those sources "
    "for changes. They are not automatically maintained."
)
STATE_TEXT = {
    health.FRESH: "Fresh: within the configured threshold",
    health.STALE: "Stale: older than the configured threshold",
    health.UNKNOWN: "Unknown: freshness cannot be determined",
    health.NO_DATA: "No data: nothing has been collected",
}


def _run_text(run: dict | None) -> str:
    if not run:
        return "none recorded"
    when = run["finished_at"] or run["started_at"]
    return f"{run['status']} at {when} (run {run['run_id']})"


def _refresh_text(entry: dict | None) -> str:
    if not entry:
        return "none recorded"
    return f"{entry['status']} (refresh started {entry['started_at']})"


def _source(h: health.SourceHealth) -> None:
    st.subheader(h.title)
    (st.success if h.freshness == health.FRESH else st.warning)(
        f"**{STATE_TEXT[h.freshness]}.** Basis: {h.freshness_basis}."
    )
    st.table(
        [
            {"Item": "Last attempted collection", "Value": _run_text(h.last_attempt)},
            {"Item": "Last successful collection", "Value": _run_text(h.last_success)},
            {"Item": "Last refresh including this source", "Value": _refresh_text(h.last_refresh)},
            {"Item": "Latest observation label", "Value": h.latest_label or "none"},
            {"Item": "Publication timestamp", "Value": h.publication_time},
            {"Item": "Retrieval timestamp", "Value": h.retrieval_time or "none"},
            {"Item": "Configured freshness threshold", "Value": f"{h.threshold_hours} hours"},
            {"Item": "Freshness", "Value": h.freshness},
        ],
        hide_index=True,
    )
    if h.problems:
        st.error("Errors and partial failures:\n" + "\n".join(f"- {p}" for p in h.problems))
    else:
        st.caption("No failed or interrupted runs since the last successful collection.")
    if h.coverage:
        st.markdown("**Coverage** (counts of the latest values; absent rows are never filled)")
        # One row per measure and one column per series keeps the table narrow on phones.
        measures = next(iter(h.coverage.values())).keys()
        st.table(
            [
                {"Measure": m.replace("_", " "), **{s: str(c[m]) for s, c in h.coverage.items()}}
                for m in measures
            ],
            hide_index=True,
        )
    st.markdown("**Storage validation** (read-only check of committed files and checksums)")
    st.table([{"Check": k, "Result": str(v)} for k, v in h.storage.items()], hide_index=True)
    for note in h.notes:
        st.caption(note)


def render_system_health() -> None:
    st.title("System Health")
    st.markdown(
        "Read-only status of local collection, freshness, storage, and content. This page "
        "**never collects data**: run `mambo refresh` (or `mambo collect`) from a terminal. "
        "Nothing here is real-time; each source publishes on its own schedule."
    )
    try:
        settings = load_settings()
        config = refresh_config.load()
    except (ConfigError, refresh_config.RefreshConfigError) as exc:
        st.error(f"Configuration problem: {exc}. Status cannot be shown.")
        return
    stores = {
        "eia": Store(settings.data_dir),
        "ercot": ercot_collect.store(settings.data_dir),
        "eia-generation": generation.store(settings.data_dir),
        "ercot-dam-spp": ercot_prices.store(settings.data_dir),
        "ercot-rt-spp": ercot_rt.store(settings.data_dir),
    }
    now = NOW()
    st.caption(f"Checked at {now.astimezone(UTC).isoformat(timespec='seconds')} (UTC).")
    st.button("Check again", key="health_recheck", help="Re-reads local files; sends nothing")

    view = st.radio(
        "Show",
        ["all", "eia", "ercot", "eia-generation", "ercot-dam-spp", "ercot-rt-spp"],
        format_func={
            "all": "All sources",
            "eia": "EIA-930 demand",
            "ercot": "ERCOT NP6-345-CD",
            "eia-generation": "EIA-930 generation",
            "ercot-dam-spp": "ERCOT DAM price (HB_NORTH)",
            "ercot-rt-spp": "ERCOT real-time price (HB_NORTH)",
        }.get,
        horizontal=True,
        key="health_view",
    )
    st.header("Collection and freshness")
    logs = refresh.read_logs(settings.data_dir)
    for h in health.source_health(stores, config, now, logs):
        if view in ("all", h.source):
            _source(h)

    st.header("Recent refreshes")
    if logs:
        st.table(
            [
                {
                    "Started (UTC)": r.get("started_at_utc", ""),
                    "Result": r.get("overall", ""),
                    "Sources": ", ".join(
                        f"{x['source']}: {x['status']}" for x in r.get("results", [])
                    ),
                    "Requests used / budgeted": f"{r.get('requests_used', '?')} / "
                    f"{r.get('requests_budgeted', '?')}",
                }
                for r in logs
            ],
            hide_index=True,
        )
    else:
        st.caption("No refresh logs yet. `mambo refresh --dry-run` shows what would run.")

    with st.expander("Refresh plan in use"):
        st.caption(f"Plan: {config.origin}")
        st.table(
            [
                {
                    "Source": s.title,
                    "Enabled": "yes" if s.enabled else "no",
                    "Source publication cadence": s.publication_cadence,
                    "Collection interval (your schedule)": f"{s.collection_interval_hours} h",
                    "Request budget per refresh": str(s.request_budget),
                }
                for s in (
                    config.eia,
                    config.ercot,
                    config.generation,
                    config.prices,
                    config.rt_prices,
                )
            ],
            hide_index=True,
        )

    st.header("Content status")
    st.warning(SNAPSHOT_NOTE)
    content = health.content_health()
    st.markdown("**Regulatory responsibility records**")
    st.table([{"Item": k, "Value": str(v)} for k, v in content["records"].items()], hide_index=True)
    st.markdown("**Lessons**")
    st.table(content["lessons"], hide_index=True)

    st.header("Status of System Health features")
    st.table(
        [
            {"ID": f["id"], "Feature": f["name"], "Status": f["status"]}
            for f in features()
            if f["section"] == "system-health"
        ],
        hide_index=True,
    )
