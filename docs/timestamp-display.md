# Timestamp display: inventory and conventions

Stage 17, ADR 0015. Helpers: `src/mambo_explorer/timeview.py`. Regression tests:
`tests/test_timeview.py` (offline) and the browser procedure at the end.

Rule: **a UTC label never accompanies a browser-local displayed value.** Every time value
the app shows belongs to one of the kinds below, and each kind has one display convention.

## Kinds and conventions

| Kind | What it is | Displayed as | Never |
|---|---|---|---|
| **Verified UTC source period label** | EIA-930 `period` ("YYYY-MM-DDTHH"), stated by the API as UTC | the label string; on a time axis, a Vega-Lite **utc** scale with the verbatim label in the tooltip (`utc_label_chart`) | converted to local time; turned into an interval start/end (the hour-ending convention is unverified for the API field) |
| **Offset-bearing publication timestamp** | ERCOT listing `PublishDate` (e.g. `2026-10-12T05:50:00-05:00`) | as the source wrote it, optionally followed by "(= … UTC)" | re-interpreted in another zone |
| **Retrieval timestamp** | when this computer downloaded or committed data (`retrieved_at_utc`, run `finished_at`, refresh `started_at_utc`) | "YYYY-MM-DD HH:MM UTC" (`format_utc`) or the catalog's ISO string with its `+00:00` offset | presented as a publication time or an effective date |
| **ERCOT operating labels** | `OperDay`, `HourEnding`, `DSTFlag` as published | verbatim; chart x axis is **ordinal in file order** | assigned a time zone or UTC; placed on a time scale |
| **Synthetic elapsed interval** | finance lesson intervals (`t1`, 1 h) | identifier plus elapsed duration | given a calendar timestamp or DST |
| **Unknown semantics** | anything unresolved (interval boundaries, EIA publication time, ERCOT zone) | the word "unknown", "not provided", or the source's own text | derived or guessed |

## Inventory (2026-10-12)

| Page / element | Field | Kind | Convention applied |
|---|---|---|---|
| Explore › EIA demand/forecast chart, tooltip | `period` | UTC label | `utc_label_chart` (utc scale; tooltip = label) — **fixed in Stage 17** (was a naive DuckDB `strptime`, drawn as local) |
| Explore › EIA observations table | `period`, `interval_start_utc`, `interval_end_utc`, `retrieved_at_utc` | UTC label; unknown (null); retrieval | shown raw; interval columns stay null |
| Explore › EIA completeness, "Retrieved", "Last successful collection" | retrieval | retrieval | `format_utc` |
| Explore › generation chart, tooltip | `period` | UTC label | `utc_label_chart` — Stage 16 used naive values (stripped tz); replaced |
| Explore › generation tables (coverage, hour sums, observations) | `period` | UTC label | raw label |
| Explore › ERCOT chart | `HourEnding`, `DSTFlag` | ERCOT labels | ordinal axis in file order (unchanged) |
| Explore › ERCOT "Published by ERCOT", "Retrieved" | `publish_time_raw` (+ UTC), `retrieved_at_utc` | publication; retrieval | raw + "(= … UTC)"; "… UTC" (unchanged) |
| Learn › lesson 2 demand chart, tooltip, table | `period` | UTC label | `utc_label_chart` — **fixed in Stage 17** (aware values drawn as local) |
| Learn › lesson 3 error chart, pairs table | `period` | UTC label | `utc_label_chart` — **fixed in Stage 17** (same defect) |
| Learn › lesson 4 absent runs | `period` | UTC label | raw labels (unchanged) |
| Learn › lesson 13 generation panel | `period` | UTC label | `utc_label_chart` |
| Learn › "Observations:" freshness line | run `finished_at` | retrieval | `format_utc` |
| Learn › window pickers | UTC days by label | UTC label | date input over label dates (unchanged) |
| Learn › finance calculators (lessons 8–10) | interval ids, durations | elapsed | unchanged; no calendar time |
| System Health › attempt/success/refresh lines | catalog ISO with `+00:00` | retrieval | ISO string with offset (unchanged) |
| System Health › "Latest observation label" | `period` or ERCOT labels | UTC label / ERCOT labels | text as the source wrote it |
| System Health › "Publication timestamp" | ERCOT `PublishDate`; EIA "not provided" | publication / unknown | raw / explanation |
| System Health › "Checked at" | now | retrieval-kind | ISO "(UTC)" |
| Compliance › "Retrieved by this project" | record `retrieved_at` | retrieval date | labeled "a retrieval date, not an effective date" |
| CLI `status`, `health`, refresh logs | catalog and log timestamps | retrieval | ISO with offset / `_utc` suffix |

## Why the chart fix is done this way

Streamlit's built-in `st.line_chart`/`st.bar_chart` hand Vega-Lite a temporal field with a
default (local) scale, so the browser's zone decides the tick labels and tooltips. Stage 16
worked around this for one chart by stripping the zone from the datetimes, which happens to
render correctly only because Vega then parses naive values as local time. Stage 17 replaces
both with Altair charts whose x encoding is `scale: {type: "utc"}` over aware UTC instants
(so ticks are formatted in UTC by the renderer) and whose tooltip is the **verbatim label
string** (so it cannot be re-formatted at all). Tables print the same label string.

## Regression procedure (browser)

With a scratch store and a running app, open a page with a time-axis chart in three browser
time zones (UTC, America/Los_Angeles, Asia/Seoul — Playwright `timezoneId`), and for one
chosen observation check that:

1. the first axis tick text equals the UTC label's date/hour;
2. hovering its mark shows a tooltip whose "Period label (UTC)" equals the label;
3. the table row with that label shows the same value.

Also check the 23-hour US spring-forward day and a label at UTC midnight. Record the
observed strings, not only screenshots.

## Still unresolved (display does not resolve them)

- Whether the EIA API `period` label marks the start or the end of the hour.
- ERCOT's time zone and DST representation for `HourEnding`/`DSTFlag`.
- EIA provides no per-value publication time.
- Whether ERCOT reports storage charging as negative generation or within demand.
