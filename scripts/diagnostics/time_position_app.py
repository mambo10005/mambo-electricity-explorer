"""Time-position diagnostic (Stage 18, ADR 0015 addendum). Not part of the application.

Run:  .venvs/py314/Scripts/streamlit run scripts/diagnostics/time_position_app.py

Draws SYNTHETIC display fixtures with the production helper `timeview.utc_label_chart`, with
explicit UTC ticks on every fixture hour, so a browser check can match each point to its own
tick. Reads and writes no store. Values are synthetic and carry no source meaning; the labels
say nothing about whether a source hour is hour-beginning or hour-ending.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer.timeview import utc_label_chart

# Distinct values so each point is identifiable by value as well as by label.
FIXTURES = {
    "four-hours": [
        ("2026-03-08T07", 700.0),
        ("2026-03-08T08", 800.0),
        ("2026-03-08T09", 900.0),
        ("2026-03-08T10", 1000.0),
    ],
    "utc-midnight": [
        ("2026-03-07T22", 2200.0),
        ("2026-03-07T23", 2300.0),
        ("2026-03-08T00", 2400.0),
        ("2026-03-08T01", 2500.0),
    ],
}

st.title("Time-position diagnostic (synthetic)")
st.caption("SYNTHETIC display fixtures. Not observations. Explicit UTC ticks on every hour.")

for name, points in FIXTURES.items():
    st.header(f"Fixture: {name}")
    rows = [{"period": p, "Value (synthetic)": v} for p, v in points]
    utc_label_chart(
        rows,
        value_field="Value (synthetic)",
        value_title="Value (synthetic)",
        colors=["#1f77b4"],
        key=f"diag_line_{name}",
        tick_labels=[p for p, _ in points],
    )
    st.table(
        [{"Fixture": name, "Label (UTC)": p, "Value (synthetic)": f"{v:,.0f}"} for p, v in points],
        hide_index=True,
    )

st.header("Fixture: four-hours, stacked bars")
bar_rows = [
    {"period": p, "Series": s, "Value (synthetic)": v * w}
    for p, v in FIXTURES["four-hours"]
    for s, w in (("A", 1.0), ("B", -0.25))
]
utc_label_chart(
    bar_rows,
    value_field="Value (synthetic)",
    value_title="Value (synthetic)",
    series_field="Series",
    series_domain=["A", "B"],
    colors=["#1f77b4", "#d95f02"],
    mark="bar",
    stack=True,
    key="diag_bar_four-hours",
    tick_labels=[p for p, _ in FIXTURES["four-hours"]],
)
st.table(
    [
        {
            "Fixture": "four-hours bars",
            "Label (UTC)": r["period"],
            "Series": r["Series"],
            "Value (synthetic)": f"{r['Value (synthetic)']:,.0f}",
        }
        for r in bar_rows
    ],
    hide_index=True,
)
