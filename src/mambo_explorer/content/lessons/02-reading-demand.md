---
lesson_id: reading-demand
title: Reading an actual demand series
order: 2
sequence_stage: fundamentals
prerequisites: [power-vs-energy]
objectives:
  - State what EIA-930 "demand" is, and what it is not.
  - Read the highest, lowest, and typical values in a selected window, in the source unit.
  - Report coverage: how many hourly labels have a usable value.
content_version: 1.0.0
effective_date: 2026-10-11
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: eia930-instructions
    title: Form EIA-930 instructions, "Data Type" (D = actual demand; energy storage exclusion)
    url: https://www.eia.gov/survey/form/eia_930/instructions.pdf
    accessed: 2026-10-11
  - id: eia-gridmonitor-about
    title: EIA Hourly Electric Grid Monitor — about the data
    url: https://www.eia.gov/electricity/gridmonitor/about
    accessed: 2026-10-11
  - id: eia930-reference-tables
    title: EIA-930 reference tables (balancing authority codes; ERCO)
    url: https://www.eia.gov/electricity/930-content/EIA930_Reference_Tables.xlsx
    accessed: 2026-10-11
dataset_bindings:
  - dataset: EIA-930
    route: electricity/rto/region-data
    entity: ERCO
    metrics: [D]
calculation_ids: [series_summary, coverage]
data_panels: [demand_series]
exercises:
  - exercise_id: demand-max
    kind: data
    generator: demand_max
    calculation_id: series_summary
glossary_terms: [Demand, BA, ERCOT, EIA, EIA-930, MWh, UTC, Period label, Revision]
limitations:
  - Demand here is the balancing authority's reported system total, not individual customer meter readings.
  - This lesson does not explain why demand rose or fell. Weather, time of day, and customer types are not in this data.
  - Values are the latest revision collected on this computer. EIA can revise them later.
  - Hours are shown by their UTC source labels, not converted to local clock time.
implementation_status: implemented
---

## Beginner

**What is "demand" here?** In the EIA-930 survey, each **balancing authority (BA)**
reports its **hourly total actual demand**. That is the total electricity used across
the area it manages, for each hour. For Texas, the BA is **ERCOT** (EIA code `ERCO`).

What it is **not**:
- It is **not** a set of readings from customers' meters. It is one system-wide total
  per hour, reported by the BA.
- It does **not** include electricity sent into storage (such as charging batteries).
  EIA's instructions count that separately.

Each value is in **MWh** and covers one hour, so (from the previous lesson) it also
equals the average MW for that hour.

Below you can pick a window of days and see:
- the **highest** and **lowest** values, and when they happened (by UTC label)
- the **average** over the window
- **coverage**: how many hourly labels have a usable value, and how many have none

Look at the shape: demand usually rises and falls within each day. **This lesson does
not say why.** The data does not include temperature, time of day in Texas, or who
used the electricity, so any explanation would be a guess.

## Technical detail

Source definition (Form EIA-930 instructions, "Data Type"): "D = actual demand. This
value should always be positive." Electricity known to be used to store energy "should
be excluded from the actual demand … and instead be included as a negative
contribution to net generation". The instructions say total actual demand is reported
under data code `SYS`
(system). These are operational BA reports, not metered retail sales.

Calculations:
- `series_summary` v1 returns `max`/`min` (with their labels), `mean`, and `range`
  over **valid** values only. A row with a null or non-numeric value is excluded, and
  so is any expected label that has no row at all. Every exclusion is listed with its
  reason. Ties are broken by the later label.
- `coverage` v1 enumerates every hourly label from the selection's start to its end,
  inclusive, as label arithmetic. It does not interpret the labels as time intervals.
  It then classifies each label as valid, zero, null, non-numeric, or absent.
- If there are no valid values, the result is **unavailable**. It is never computed
  over an empty set.

Every result records the selection (entity, start label, end label), the unit, the
formula version, and the revision and run of each observation used. Revised values
replace earlier ones only through the store's `latest` view.
