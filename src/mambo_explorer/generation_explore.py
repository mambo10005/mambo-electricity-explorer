"""Explore and Learn views for EIA-930 net generation by energy source (Stage 16, ADR 0014).

Reads committed observations from the generation store only. Never collects. Values are
signed and shown exactly as published; a sum of categories is never called total system
generation; percentages are withheld when they would mislead.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import streamlit as st

from mambo_explorer import calculations as calc
from mambo_explorer import generation
from mambo_explorer.eia import dataset as ds
from mambo_explorer.explore import STALE_AFTER

SETUP_INSTRUCTIONS = """\
```powershell
# 1. Put your free EIA key in .env (gitignored) or the environment: EIA_API_KEY=...
# 2. Preview scope and request budget (no key needed, nothing sent):
.venvs/py314/Scripts/mambo collect --source eia-generation --dry-run
# 3. Collect the last 7 completed UTC days of net generation by energy source:
.venvs/py314/Scripts/mambo collect --source eia-generation
```"""

DEFINITIONS = [
    "**Net generation** (this data): " + ds.NET_GENERATION_TEXT,
    "**Installed capacity**: the most a plant could produce (MW). Not in this data; a category "
    "with little generation may still have large capacity, or none.",
    "**Fuel consumption**: the fuel burned (MMBtu or tons). Not in this data; generation per "
    "unit of fuel differs by technology.",
    "**Marginal generation**: the unit whose output would change if demand changed by a "
    "little, which depends on offers and constraints. Not identifiable from the mix.",
]
LIMITATIONS = [
    "One balancing authority (ERCOT, EIA code ERCO). Categories are the ones EIA publishes "
    "for it; the source's SYS total is not collected, so no total system generation is shown.",
    "Values are signed exactly as published. " + ds.STORAGE_TEXT,
    "A category absent from an hour has no value. It is not zero and is never filled.",
    "Generation is not demand. Interchange and losses are not inferred from any difference.",
    "No capacity, fuel, emissions, plant-level, or price data; nothing here identifies the "
    "price-setting unit or fuel.",
    "EIA provides no per-value publication time; 'retrieved' is when this computer downloaded "
    "the data. Revisions are detected only for re-collected days.",
    "Period labels are UTC source labels; the hour-ending convention is not verified for the "
    "API field, so no interval boundaries are derived.",
]
# Sign-safe, distinguishable series colors (both themes); storage categories get the
# darker tones so a negative bar is easy to spot.
COLORS = [
    "#1f77b4",
    "#d95f02",
    "#2ca02c",
    "#7570b3",
    "#e7298a",
    "#8c564b",
    "#17becf",
    "#bcbd22",
    "#666666",
    "#1b9e77",
    "#a6761d",
    "#e6ab02",
    "#7f7f7f",
    "#9467bd",
    "#ff7f0e",
    "#393b79",
]


def _fmt(value) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


def window_picker(store, key: str):
    """(store, selection, last_run) for a chosen UTC-day window, or Nones when no data."""
    last = store.last_committed_run()
    if last is None or not store.committed_files("observations"):
        return None, last
    with store.query() as con:
        first, final = con.execute(
            "SELECT min(period), max(period) FROM latest WHERE entity = ?", [ds.ENTITY]
        ).fetchone()
    if first is None:
        return None, last
    first_day, last_day = ds.parse_period(first).date(), ds.parse_period(final).date()
    picked = st.date_input(
        "UTC days (by the source's period label)",
        value=(max(first_day, last_day - timedelta(days=2)), last_day),
        min_value=first_day,
        max_value=last_day,
        key=key,
    )
    if not isinstance(picked, tuple) or len(picked) != 2:
        st.info("Select a start and an end day.")
        return None, last
    return calc.Selection(ds.ENTITY, f"{picked[0]}T00", f"{picked[1]}T23"), last


def _no_data() -> None:
    st.info(
        "No net-generation observations have been collected on this computer. Collection "
        "runs from the command line, never from this page."
    )
    st.markdown(SETUP_INSTRUCTIONS)


def render_mix(obs: list[calc.Observation], sel: calc.Selection, key: str) -> calc.CalcResult:
    """Chart, coverage, and totals for one window. Returns the generation_mix result."""
    result = calc.generation_mix(obs, sel)
    if not result.ok:
        st.warning(f"Generation mix unavailable: {result.reason}")
        return result
    v, unit = result.values, ds.unit_label(result.unit)
    categories = v["categories"]
    chosen = st.multiselect(
        "Energy-source categories to chart",
        categories,
        default=categories,
        format_func=lambda c: f"{c} — {ds.energy_source_name(c)}",
        key=f"{key}_categories",
    )
    st.caption(
        "Data label: **observed**. Signed hourly net generation by category, exactly as EIA "
        "publishes it; bars below zero are net storage hours. Stacked bars show each "
        "category separately, not a total. The axis shows the UTC period label, not local time."
    )
    rows = [
        {
            "Period label (UTC)": ds.parse_period(o.period).replace(tzinfo=None),
            "Category": o.metric,
            f"Net generation ({unit})": o.value,
        }
        for o in obs
        if o.metric in chosen and o.value is not None
    ]
    if rows:
        st.bar_chart(
            rows,
            x="Period label (UTC)",
            y=f"Net generation ({unit})",
            color="Category",
            stack=True,
        )
    else:
        st.info("No valid values for the chosen categories in this window.")

    st.markdown("**Coverage by category** (counts over the window; nothing is filled)")
    st.table(
        [
            {
                "Category": c,
                "Name": ds.energy_source_name(c),
                f"Energy, valid hours ({unit})": _fmt(p["energy_sum"]),
                "Valid": p["valid_values"],
                "Negative": p["negative_hours"],
                "Null": p["null_values"],
                "Absent": p["absent_rows"],
            }
            for c, p in v["per_category"].items()
        ],
        hide_index=True,
    )
    unreviewed = [c for c, p in v["per_category"].items() if p["unreviewed"]]
    if unreviewed:
        st.warning(
            f"Categories not in the reviewed code list, kept as published: {unreviewed}. "
            "Their meaning has not been checked against EIA documentation."
        )

    st.markdown("**Observed totals and completeness**")
    st.markdown(
        f"- Hours in the window: {v['expected_labels']}; **complete** hours (every one of the "
        f"{len(categories)} categories has a valid value): {v['complete_hours']}; incomplete: "
        f"{v['incomplete_hours']}.\n"
        f"- Sum of all reported categories over complete hours: "
        f"**{_fmt(v['window_sum_complete_hours'])} {unit}**. This is the sum of the categories "
        "EIA published, **not** total system generation (the source's SYS total is not "
        "collected) and not demand.\n"
        f"- Absent category-hours: {v['absent_category_hours']}; null: "
        f"{v['null_category_hours']}."
    )
    if v["shares"]:
        st.markdown(f"**Shares** — {v['share_note']}.")
        st.table(
            [
                {"Category": c, "Share of the category sum": f"{s * 100:.1f}%"}
                for c, s in v["shares"].items()
            ],
            hide_index=True,
        )
    else:
        st.info(f"Percentages {v['share_note']}.")
    with st.expander(f"Hour-by-hour category sums ({len(v['hours'])} rows)"):
        st.table(
            [
                {
                    "Label (UTC)": h["period"],
                    "Categories present": h["categories_present"],
                    "Complete": "yes" if h["complete"] else "no",
                    f"Sum of reported categories ({unit})": _fmt(h["category_sum"]),
                    "Any negative": "yes" if h["has_negative"] else "",
                }
                for h in v["hours"]
            ],
            hide_index=True,
        )
    return result


def render_generation(settings) -> None:
    store = generation.store(settings.data_dir)
    sel, last = window_picker(store, "explore_generation_window")
    if last is None:
        _no_data()
        _definitions_and_limits()
        return
    finished = datetime.fromisoformat(last["finished_at"]).astimezone(UTC)
    if datetime.now(UTC) - finished > STALE_AFTER:
        st.warning(
            f"Data may be stale: the last successful collection finished "
            f"{finished:%Y-%m-%d %H:%M} UTC, more than {STALE_AFTER.total_seconds() / 3600:.0f} "
            "hours ago."
        )
    st.header("Net generation by energy source")
    if sel is None:
        _definitions_and_limits()
        return
    obs = calc.load_generation(store, sel)
    render_mix(obs, sel, "explore_generation")
    st.header("Source and definitions")
    st.markdown(
        "\n".join(
            [
                f"- **Source:** U.S. Energy Information Administration, {ds.DATASET} "
                f"(API route `{ds.GENERATION_ROUTE}`, facet `{ds.GENERATION_FACET}`, "
                f"frequency `{ds.FREQUENCY}`).",
                f"- **Units (as reported):** {', '.join(sorted({o.unit for o in obs})) or 'none'}.",
                f"- **Interval:** {ds.GENERATION_INTERVAL_TEXT}",
                f"- **Last successful collection:** {finished:%Y-%m-%d %H:%M} UTC "
                f"(run `{last['run_id']}`). Publication time is not provided by the source.",
            ]
        )
    )
    with st.expander("Underlying observations (latest revision of each category-hour)"):
        st.table(
            [
                {
                    "Label (UTC)": o.period,
                    "Category": o.metric,
                    "Value": o.value_raw,
                    "Unit": o.unit,
                    "Flags": o.quality_flags,
                    "Revision": o.revision,
                }
                for o in obs
            ],
            hide_index=True,
        )
    _definitions_and_limits()


def _definitions_and_limits() -> None:
    st.header("What this is, and is not")
    st.markdown("\n".join(f"- {d}" for d in DEFINITIONS))
    st.header("Limitations")
    st.markdown("\n".join(f"- {item}" for item in LIMITATIONS))
