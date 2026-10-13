# 0015 — Application-wide timestamp-display consistency

- **Status:** Accepted
- **Date:** 2026-10-12

## Context

Stage 16's browser check found the generation chart drawing UTC period labels in the
browser's local clock under an axis titled "UTC"; lesson 2's demand chart and lesson 3's
error chart had the same defect (aware datetimes given to Streamlit's built-in charts),
and the Explore demand chart avoided it only by building naive values in DuckDB. Stage 16's
fix stripped the time zone, which relies on the renderer parsing naive values as local time.

Two uncertainties must survive untouched: whether the EIA API `period` label marks the start
or the end of the hour, and ERCOT's time zone for `OperDay`/`HourEnding`/`DSTFlag`.

## Decision

1. **Six kinds of time value, one convention each** (`docs/timestamp-display.md`):
   verified UTC source label; offset-bearing publication timestamp; retrieval timestamp;
   ERCOT labels as published; synthetic elapsed interval; unknown semantics.
2. **`timeview.utc_label_chart`** draws every time-axis chart of UTC labels as an Altair
   chart with `x: {type: temporal, scale: {type: "utc"}}` over **aware** UTC instants and a
   tooltip whose first time field is the **verbatim label string**. Tick labels are
   formatted by the renderer in UTC; the tooltip cannot be re-formatted; tables print the
   same string. Streamlit built-in charts are no longer given datetimes (test-enforced).
3. **`timeview.format_utc`** prints retrieval-kind timestamps as "YYYY-MM-DD HH:MM UTC".
4. **ERCOT** keeps its ordinal file-order axis and verbatim labels; nothing is assigned a
   zone. **Synthetic intervals** keep identifiers and elapsed durations only.
5. **No source-time reinterpretation:** interval start/end columns stay null; no storage
   migration; observation identities, revisions, and selections are unchanged (the
   snapshot ids are untouched, so no exercise answer is invalidated).
6. **Tests** carry fixtures at UTC midnight, the America/Los_Angeles and Asia/Seoul date
   boundaries, and the US spring-forward transition; they check the serialized chart
   configuration, the chart dataset's instants, tooltip fields, table labels, and that
   observation selection is unchanged. The browser procedure emulates the three zones and
   reads the axis tick, the tooltip, and the table row for one observation.

## Addendum (Stage 18, 2026-10-12)

Stage 17's browser report quoted the first three ticks of a 48-hour axis as if they
located a point 32 hours later. A position audit (`docs/timestamp-display.md`,
"Position evidence") measured each mark against its own tick in UTC, Los Angeles,
and Seoul and found correct placement (−0.5 px, Vega's half-pixel offset). No defect
was found. `utc_label_chart` gained an optional `tick_labels` argument for the
synthetic diagnostic only; production tick density is unchanged (test-enforced).

## Consequences

- Lesson text did not change, so content versions and review statuses stay as they were.
- `tests/test_accessibility.py` now reads chart colors from `utc_label_chart` calls.
- Display consistency does not resolve the hour-ending or ERCOT time-zone questions, and
  the storage sign convention (ADR 0014) remains disclosed as unresolved.
