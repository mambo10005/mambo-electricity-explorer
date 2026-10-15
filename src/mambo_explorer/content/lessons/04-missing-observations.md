---
lesson_id: missing-observations
title: Understanding missing observations
order: 4
sequence_stage: fundamentals
prerequisites: [demand-vs-forecast]
objectives:
  - Tell apart an absent row, a null value, a zero value, and data that has not been collected yet.
  - Measure coverage separately for actual demand and for the forecast.
  - Explain why an absent forecast row does not mean zero demand or a zero forecast.
content_version: 1.0.0
effective_date: 2026-10-11
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: eia-gridmonitor-about
    title: EIA Hourly Electric Grid Monitor — about the data ("published exactly as reported without imputation")
    url: https://www.eia.gov/electricity/gridmonitor/about
    accessed: 2026-10-11
  - id: eia-api-docs
    title: EIA API v2 documentation (frequency "hourly" in UTC; pagination)
    url: https://www.eia.gov/opendata/documentation.php
    accessed: 2026-10-11
dataset_bindings:
  - dataset: EIA-930
    route: electricity/rto/region-data
    entity: ERCO
    metrics: [D, DF]
calculation_ids: [coverage]
data_panels: [coverage]
exercises:
  - exercise_id: absent-not-zero
    kind: concept
    generator: absent_not_zero
    calculation_id: coverage
  - exercise_id: forecast-absent-count
    kind: data
    generator: forecast_absent_count
    calculation_id: coverage
glossary_terms: [Absent row, Null value, Period label, UTC, Day-ahead demand forecast, Demand]
limitations:
  - This lesson does not explain why any row is missing. The data does not say.
  - Gaps are described by their UTC source labels only. They are not converted to local days or operating days, because the API does not state how labels map to clock intervals.
  - '"Not collected yet" depends on what this computer has downloaded, not on what EIA has published.'
implementation_status: implemented
---

## Beginner

Data can be "missing" in different ways, and each means something different:

| Situation | What you see | What it means |
|---|---|---|
| **Absent row** | No record for that hour label at all | The value is not in the data you have. |
| **Null value** | A record exists, but the value is empty | The source sent the hour without a number. |
| **Zero value** | A record with the number 0 | A real reported value of zero. This is *not* missing. |
| **Not collected yet** | Hours outside what you downloaded | Your computer has not fetched that period. EIA may still have it. |

**Coverage is measured separately for each series.** Actual demand can be complete
while the forecast has gaps, or the other way round. The table below counts each
series on its own.

**An absent forecast is not a zero forecast, and it is not zero demand.** If the
forecast row for an hour is absent, you simply do not know the forecast for that
hour from this data. The actual demand for that hour comes from its own row.

**This lesson does not guess why rows are missing.** The data does not include a
reason. Gaps are listed by their UTC labels exactly as the source writes them.

## Technical detail

EIA states that it publishes hourly balancing-authority data "exactly as reported
without imputation". Its imputations appear only in regional and daily aggregates,
which this application does not use. In the live collection on 2026-10-11, missing
hours appeared as **absent rows**, not as nulls. The calculation still handles nulls,
empty strings, and non-numeric values in case the source represents them differently
in future.

Calculation `coverage` v1, run separately for each metric:
- It enumerates every hourly label from the selection's start to its end, inclusive,
  using label arithmetic only.
- It classifies each label as valid (including zero), zero, null, non-numeric, or
  absent.
- It reports contiguous absent runs as (first label, last label, count).

Label ranges are not turned into local dates or "operating days", because the
API does not state whether a label marks the start or the end of its hour. Treating
a run of 24 labels as one local day would rely on that unverified convention.
