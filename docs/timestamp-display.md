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

1. the label's **own** tick (or, with automatic ticks, the two neighbouring ticks)
   lines up with the mark — measure positions; do not read the first ticks of the axis;
2. hovering its mark shows a tooltip whose "Period label (UTC)" equals the label;
3. the table row with that label shows the same value.

Also check the 23-hour US spring-forward day and a label at UTC midnight. Record the
observed strings and pixel positions, not only screenshots. The synthetic diagnostic
(`streamlit run scripts/diagnostics/time_position_app.py`) puts a tick on every hour.

## Position evidence (Stage 18, 2026-10-12)

Three different properties, checked separately:

| Property | Meaning | How it was checked |
|---|---|---|
| **Time-zone invariance** | the same strings appear whatever the browser zone | Stage 17 and 18: identical tick labels, tooltips, and table rows in UTC, America/Los_Angeles, Asia/Seoul |
| **Correct instant parsing** | the instant behind a label is that label's UTC hour | `tests/test_timeview.py`: the Arrow dataset the browser receives holds, for each row, the instant built independently from the label's digits; explicit tick values serialize as `{…, "utc": true}` |
| **Correct visual position** | the mark is drawn where its own tick is | browser: point or bar centre vs. its tick's screen x (below) |

**The Stage 17 discrepancy.** Stage 17's report put the axis ticks "2026-03-07 00:00, 03:00,
06:00" next to the tooltip and table for observation 2026-03-08T08. The probe that produced
it recorded `ticks.slice(0, 3)`: the **first three ticks of a 48-hour chart** whose data
starts at 2026-03-07T00 (16 ticks, every 3 h, ending 2026-03-08 21:00). Those ticks are
the far left of the axis, about 32 hours from the point, and never described the point's
position. The evidence was mislabelled; the code was not wrong. Nothing in Stage 17 had
checked visual position at all, only zone-invariance of strings.

**Measuring position.** Streamlit's theme draws no tick marks and rotates labels by
−45°. Vega renders each label as `translate(tickX, 16) rotate(315) translate(0, 9)`, so the
label's visible origin sits about 7 px from the tick; the tick's position is the **first**
translate. A point (symbol) is drawn at `translate(x, y)`; a bar is measured at its
bounding-box centre. Both are mapped to screen pixels through the parent group's transform.
A −0.5 px offset is Vega's half-pixel axis offset for crisp rendering.

**Diagnostic** (`scripts/diagnostics/time_position_app.py`, synthetic, explicit UTC ticks on
every fixture hour via `utc_label_chart(…, tick_labels=…)`; production charts never set
ticks — test-enforced):

| Chart | Zone | Domain (ticks) | Hovered | Tooltip | Table row | Point x vs own tick x |
|---|---|---|---|---|---|---|
| four-hours line | UTC | 07:00 .. 10:00 (4) | 2026-03-08T08, 800 | Period label (UTC) 2026-03-08T08 · 800.00 | four-hours 2026-03-08T08 800 | 568.7 vs 569.2 (−0.5 px; 207.7 px/h) |
| four-hours line | Los Angeles | same | same | same | same | 568.7 vs 569.2 (−0.5) |
| four-hours line | Seoul | same | same | same | same | 568.7 vs 569.2 (−0.5) |
| utc-midnight line | UTC / LA / Seoul | 2026-03-07 22:00 .. 2026-03-08 01:00 (4) | 2026-03-08T00, 2,400 | 2026-03-08T00 · 2,400.00 | utc-midnight 2026-03-08T00 2,400 | 776.3 vs 776.8 (−0.5) in all three |
| four-hours stacked bars | UTC / LA / Seoul | 07:00 .. 10:00 (4) | 2026-03-08T08, series A, 800 | Series A · 2026-03-08T08 · 800.00 | four-hours 2026-03-08T08 800 | 549.7 vs 550.2 (−0.5; 183.7 px/h) in all three |

In every chart the marks are in chronological order left to right.

**Production views** (synthetic scratch store, 2026-03-07T00 .. 2026-03-08T23):

| Chart | Zone | Ticks | Hovered | Tooltip | Table row | Position |
|---|---|---|---|---|---|---|
| lesson 2 demand | UTC / LA / Seoul | 16, every 3 h, 2026-03-07 00:00 .. 2026-03-08 21:00 | 2026-03-08T08 | 2026-03-08T08 · 41,234.00 | 2026-03-08T08 41234 megawatthours 1 | no own tick (neighbours 06:00 and 09:00); x = 960.8 vs 961.3 interpolated from the tick scale (15.7 px/h): −0.5 px |
| generation bars | UTC / LA / Seoul | same 16 | 2026-03-07T15, COL, 7,000 | Category COL · 2026-03-07T15 · 7,000.00 | — (raw table not opened) | own tick 15:00: 669.5 vs 670.0 (−0.5; 13.7 px/h) |

The browser's own local rendering of each instant differed (e.g. 2026-03-08T08 = 00:00 in Los
Angeles, 17:00 in Seoul), so the agreement is not coincidence.

**Conclusion.** No code defect: instants are parsed and serialized correctly, and marks are
drawn at their own UTC hour in every zone. The only code change is the optional
`tick_labels` argument used by the diagnostic. None of this establishes whether a source
label marks the start or the end of its hour.

## Still unresolved (display does not resolve them)

- Whether the EIA API `period` label marks the start or the end of the hour.
- ERCOT's time zone and DST representation for `HourEnding`/`DSTFlag`.
- EIA provides no per-value publication time.
- Whether ERCOT reports storage charging as negative generation or within demand.
