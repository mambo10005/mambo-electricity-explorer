"""Timestamp display helpers (Stage 17, ADR 0015). One place for the display convention of
every kind of time value the app shows, so charts, tooltips, tables, and captions agree
whatever the browser's time zone is.

Kinds of time value (see docs/timestamp-display.md):

- UTC_LABEL: a verified UTC source period label ("YYYY-MM-DDTHH", EIA-930). Shown as the
  label string itself. On a time axis the instant is drawn on a Vega-Lite **utc** scale and
  the tooltip carries the verbatim label, so nothing depends on the browser's zone. Whether
  the label marks the start or the end of the hour is unverified for the API field, so no
  interval start/end is ever drawn or printed.
- PUBLICATION: an offset-bearing timestamp the source published (ERCOT listing PublishDate).
  Shown as the source wrote it, optionally with its UTC equivalent marked "UTC".
- RETRIEVAL: when this computer downloaded or committed data. Shown in UTC, marked "UTC".
- ERCOT_LABEL: OperDay, HourEnding, and DSTFlag exactly as published; never converted, never
  placed on a time axis (ordinal axis in file order).
- ELAPSED: synthetic interval identifiers with elapsed durations (finance lessons); no
  calendar time at all.
- UNKNOWN: a value whose semantics are unresolved is shown with the word "unknown" or the
  source's own text, never as a derived time.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import altair as alt
import pandas as pd
import streamlit as st

from mambo_explorer.eia import dataset as ds

UTC_LABEL, PUBLICATION, RETRIEVAL, ERCOT_LABEL, ELAPSED, UNKNOWN = (
    "utc-source-label",
    "publication-timestamp",
    "retrieval-timestamp",
    "ercot-label-as-published",
    "synthetic-elapsed-interval",
    "unknown-semantics",
)
AXIS_TITLE = "Period label (UTC)"
# Vega-Lite time format for axis ticks on the UTC scale: the label's own granularity.
AXIS_FORMAT = "%Y-%m-%d %H:00"
UTC_SCALE = {"type": "utc"}


def format_utc(value: datetime | str | None, *, seconds: bool = False) -> str:
    """A RETRIEVAL-kind timestamp as 'YYYY-MM-DD HH:MM UTC' (aware input converted to UTC)."""
    if value is None:
        return "unknown"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)  # catalog and store timestamps are written in UTC
    fmt = "%Y-%m-%d %H:%M:%S UTC" if seconds else "%Y-%m-%d %H:%M UTC"
    return value.astimezone(UTC).strftime(fmt)


def label_frame(rows: Sequence[dict], label_key: str = "period") -> pd.DataFrame:
    """Add an aware UTC `instant` column derived from the verbatim source label.

    The label column is kept untouched for tooltips and tables.
    """
    frame = pd.DataFrame(list(rows))
    frame["instant"] = [ds.parse_period(p) for p in frame[label_key]]
    return frame


def utc_datetime(label: str) -> alt.DateTime:
    """A Vega-Lite DateTime for a UTC source label, flagged utc so no browser zone applies."""
    t = ds.parse_period(label)
    return alt.DateTime(year=t.year, month=t.month, date=t.day, hours=t.hour, utc=True)


def utc_label_chart(
    rows: Sequence[dict],
    *,
    value_field: str,
    value_title: str,
    series_field: str | None = None,
    colors: Sequence[str] | None = None,
    series_domain: Sequence[str] | None = None,
    mark: str = "line",
    stack: bool | None = None,
    label_key: str = "period",
    key: str | None = None,
    alt_text: str | None = None,
    tick_labels: Sequence[str] | None = None,
) -> alt.Chart | None:
    """Draw values against verified UTC period labels; the browser's time zone never matters.

    Rows need the verbatim label (`label_key`) and `value_field`; `series_field` names the
    series for multi-series charts. The x axis is a Vega-Lite utc scale; the tooltip shows
    the verbatim label and the value. Returns the chart, or None when there are no rows.

    `tick_labels` (UTC source labels) pins axis ticks to those instants. Production views
    leave it unset (Vega chooses tick density); the time-position diagnostic sets it so
    each observation can be matched to its own tick.
    """
    if not rows:
        return None
    frame = label_frame(rows, label_key)
    axis = dict(title=AXIS_TITLE, format=AXIS_FORMAT, labelAngle=-45)
    if tick_labels is not None:
        axis["values"] = [utc_datetime(label) for label in tick_labels]
    x = alt.X("instant:T", scale=alt.Scale(**UTC_SCALE), axis=alt.Axis(**axis))
    y = alt.Y(f"{value_field}:Q", title=value_title)
    if stack is not None:
        y = alt.Y(f"{value_field}:Q", title=value_title, stack="zero" if stack else None)
    tooltip = [
        alt.Tooltip(f"{label_key}:N", title=AXIS_TITLE),
        alt.Tooltip(f"{value_field}:Q", title=value_title, format=",.2f"),
    ]
    encodings = {"x": x, "y": y, "tooltip": tooltip}
    if series_field:
        domain = list(series_domain or sorted(frame[series_field].unique()))
        scale = alt.Scale(domain=domain, range=list(colors)) if colors else alt.Undefined
        encodings["color"] = alt.Color(f"{series_field}:N", title=series_field, scale=scale)
        encodings["tooltip"] = [alt.Tooltip(f"{series_field}:N", title=series_field), *tooltip]
    base = alt.Chart(frame)
    # Points on lines give every observation its own hoverable mark and tooltip.
    chart = base.mark_bar() if mark == "bar" else base.mark_line(point=True)
    if not series_field and colors:
        chart = (
            chart.mark_bar(color=colors[0])
            if mark == "bar"
            else chart.mark_line(color=colors[0], point=True)
        )
    chart = chart.encode(**encodings).properties(width="container")
    st.altair_chart(chart, width="stretch", key=key)
    if alt_text:
        st.caption(alt_text)
    return chart
