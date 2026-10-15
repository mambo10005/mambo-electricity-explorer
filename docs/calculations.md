# Calculations

Implemented in `src/mambo_explorer/calculations.py` (feature CALC-01). The functions
are pure and deterministic: they take observation records and do no I/O. Lessons,
exercises, and tests all call the same functions, so the numbers in a lesson and the
answer to its exercise always come from one place.

## Shared conventions

- **Inputs** are `Observation` records (entity, metric, period label, value,
  `value_raw`, unit, flags, revision, run id). They are loaded from the store's
  `latest` view by `load_observations()`, which reads committed files only.
- **Selection** = entity + inclusive start and end **UTC source labels**
  (`YYYY-MM-DDTHH`). Labels are enumerated by hourly label arithmetic.
  **No interval start or end times are derived**, because the API does not state the
  label convention (see `docs/source-register.md`).
- **Valid value** = a finite number. Zero is valid. Null, empty, and non-numeric
  values are invalid.
- **Every result** (`CalcResult`) records:
  - `calculation_id`, `formula_version`, and `status` (`ok` or `unavailable`)
  - `selection`, `unit` (the source unit, e.g. `megawatthours`), and `values`
  - `valid_count`
  - `exclusions`: every excluded label with its reason (absent row, null value,
    non-numeric value, unit mismatch)
  - `references`: metric, period, revision, and run id of each observation used
- **Unavailable** is returned instead of a number when:
  - there are no valid inputs or no matched pairs
  - the units are mixed
  - a period appears more than once in the input (duplicates are never silently
    resolved)
  - the input is invalid
- Nothing is filled, interpolated, clipped, or imputed.
- `snapshot_id` is a fingerprint of the selection plus each scoped observation's
  (metric, period, revision, `value_raw`, unit). It does not depend on row order.
  It changes when the window changes or when data is revised. Exercises use it to
  stay stable, and to regenerate when it changes.

## `power_energy` v1

| Given | Result | Formula |
|---|---|---|
| average power *P* (MW), duration *h* | energy (MWh) | *E = P × h* |
| energy *E* (MWh), duration *h* | average power (MW) | *P = E ÷ h* |

Unavailable if both or neither of *P*/*E* is given, or if *h* ≤ 0 or is not finite.
It is used only with **synthetic** example numbers (lesson 1).

## `series_summary` v1

For one metric in the selection: `max` (and its label), `min` (and its label),
`mean`, `range = max − min`, `expected_labels`, `present_rows`, `valid_values`, and
`absent_rows`. These are computed over valid values only, in the source unit. Ties
for max or min are broken by the later label. Unavailable when there are no valid
values or units are mixed.

## `coverage` v1

For **one** metric (run separately per series), each expected label is classified as
valid, zero (a subset of valid), null, non-numeric, or absent (no row). It also
returns contiguous `absent_runs` as (first label, last label, count). A run is a set
of UTC labels; it is **not** described as a local day or operating day.

## `forecast_error` v1

Pairs actual (`D`) and forecast (`DF`) by entity and source period label. The steps:

1. For each expected label, exclude it (recording why) if either side is absent,
   null, or non-numeric, or if the two units differ.
2. For the *n* matched pairs, with eᵢ = actualᵢ − forecastᵢ (source unit):
   - **mean error** = Σeᵢ / n. Positive means demand came in above the forecast
     on average.
   - **MAE** = Σ|eᵢ| / n
   - **RMSE** = √(Σeᵢ² / n)
3. It also returns:
   - counts of under-forecast hours (e > 0), over-forecast hours (e < 0), and exact hours
   - the largest absolute error and its label
   - per-pair errors
4. Unavailable when *n* = 0 or duplicates exist.

The forecast used is the **latest revision stored locally**, which is not necessarily
the forecast as first issued. This is descriptive accuracy for learning, not a trading
backtest.

## Tests

`tests/test_calculations.py` covers:
- known examples and sign conventions
- absent rows, nulls, non-numeric values, and zero
- duplicates and mixed units
- empty inputs (unavailable, never 0)
- window changes, other entities and metrics ignored
- snapshot stability and change
- revision references through a real (synthetic-data) store, where the latest
  revision is used
