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

## DC OPF (economic dispatch), via mambo-power — Stage 7

Formulation audit and decision: ADR 0007. Implementation: `modeling/adapter.run_dc_opf`.

**Units and the duration convention**

| Quantity | Unit | Where |
|---|---|---|
| Dispatch | MW | `dispatch_mw` |
| Energy over the teaching interval | MWh = MW × 1 h | `energy_mwh` |
| Offer (marginal cost) | synthetic $/MWh | `offer_per_mwh` (c1) |
| Package objective Σ c1·p | synthetic **$/h** (a cost rate) | `cost_rate_per_h` |
| Cost over the interval | synthetic $ = rate × 1 h | `interval_cost` |
| Modeled nodal price | synthetic $/MWh = ∂(cost rate)/∂(demand MW) | `price_per_mwh` |
| Line-limit sensitivity | synthetic $/h per MW of rating | `limit_sensitivity_per_mw` |

The interval is exactly one hour by construction. The cost-rate and interval-cost
numbers are equal for that reason only.

**Per-run checks** (absolute tolerances 1e-6 MW and 1e-6 $/MWh, chosen above HiGHS's 1e-7
feasibility tolerance; cost also uses a 1e-9 relative tolerance):
1. Solver status is `Optimal`, and every value is finite.
2. Σ dispatch = Σ demand.
3. Flows equal a DC power flow at the dispatch (the verified Stage 6 path).
4. Generator bounds and line ratings hold.
5. Σ c1·p equals the reported objective.
6. KKT stationarity: c1 − price(bus) − bound dual = 0 for every generator.
7. Dual signs and complementary slackness.
8. Price decomposition at every bus: price = λ + Σ μ·PTDF, with PTDF measured by the
   DC power flow.

Any failure gives `failed` with no outputs. Steps 1–8 together form a KKT certificate for
this convex LP; feasibility alone would not prove optimality.

**Price verification:**
- Each run re-solves with demand changed by h = ±0.1 MW at every bus. A negative change at a
  0 MW bus is a mathematical check only, and the package accepts it.
- Prices are shown only if both changes are feasible and their average rates agree within
  1e-4 $/MWh with each other and with the reported price. The finite-difference tolerance is
  looser because a quotient over 0.1 MW amplifies 1e-7-scale solver noise.
- Otherwise prices are withheld, with a direction-specific reason and the finite-change
  table (see "Finite demand changes" below).
- Equal offers with feasible room to trade output mark the dispatch as non-unique. The
  objective and prices are still valid.

**Finite demand changes (Stage 9, BL-5; `modeling/sensitivity.py`).** With C(D) the optimal
cost rate in $/h:

| Quantity | Formula | Unit |
|---|---|---|
| Increase: cost-rate change | C(D + h) − C(D) | $/h |
| Increase rate (average incremental cost rate) | [C(D + h) − C(D)] / h | ($/h)/MW = $/MWh |
| Decrease: cost-rate change | C(D − h) − C(D) (negative when it saves money) | $/h |
| Decrease rate (average decremental cost rate) | [C(D) − C(D − h)] / h | $/MWh |

- *Dimensions and the hour:* ($/h) ÷ MW = $/MWh. Over the one-hour teaching interval, a
  change of h MW is h MWh of energy and changes the interval cost by ΔC × 1 h dollars, so
  the same number is dollars per MWh of energy. No other conversion is applied.
- *Averages, not derivatives:* C is piecewise linear and convex in demand. With no breakpoint
  in [D − h, D + h] both rates equal the local slope. If they differ, a breakpoint lies in
  that range, possibly at D. The check cannot locate it, so neither rate is called a local
  (one-sided) marginal rate. A change that crosses a breakpoint gives a **blend**: e.g.
  D = 149.95 MW below a 150 MW capacity gives (0.05 × 20 + 0.05 × 30) / 0.1 = 25 $/MWh for
  the increase, while the local slope is still 20.
- *Direction-specific feasibility:* each direction is reported as feasible or infeasible on
  its own. At the capacity edge only the increase is infeasible; with zero demand only the
  decrease is (generators cannot go below 0 MW). The note names exactly the failing
  direction(s).
- *Three distinct states:* a failed run (any check fails) shows no outputs at all; an
  infeasible base run shows no dispatch, cost, or rates; a verified base run with an
  infeasible *perturbation* keeps its dispatch and cost and withholds only the prices.
- *The gate is unchanged.* Its decisions (verified / withheld, and the order: infeasible
  direction, differing averages, mismatch) are the same as Stage 7. Stage 9 changed only
  what it records (per-direction cost-rate change) and how it explains itself. Clearer
  wording does not strengthen the numerical verification.
- *Versions:* `adapter.CHECKS_VERSION` 1.2.0, `sensitivity.TERMINOLOGY_VERSION` 2.0.0,
  model-exercise generator 1.1.0. Records carry `checks_version`; records from older checks
  are hidden in the lab and are not current for lessons, and exercise snapshots change, so
  older answers are not reused.

**Benchmarks** (`tests/test_opf_benchmarks.py`): derivations are in the module docstring.

| Case | Dispatch (MW) | Cost rate ($/h) | Prices A/B/C ($/MWh) |
|---|---|---|---|
| A uncongested | G1 150, G2 0 | 3000 | 20/20/20 |
| B G1 capacity 100 | 100/50 | 3500 | 30/30/30 |
| C AC rating 60 | 90/60 | 3600 | 20/30/40 (AC dual −40 $/h per MW) |
| D 150 MW capacity vs 200 MW demand | infeasible | — | — |
| E breakpoint (cap 150 = demand) | 150/0 | 3000 | withheld: up 30, down 20 at every bus |
| E2 AC exactly at limit (demand 120) | 120/0 | 2400 | withheld: B up 30/down 20; C up 40/down 20 |
| E3 equal offers | one optimal vertex | 3000 | 20/20/20 (dispatch not unique) |

## Lesson model runs and model-backed exercises — Stage 8

Lessons 5–7 use **fixed, predefined runs** (`modeling/cases.LESSON_RUNS`), never sweeps
or learner-typed values. Each run starts from an economic-dispatch lab preset
(`LAB_CASES`) and may override fixed inputs. All of them go through the verified
adapter: `run_dc_opf` (Stage 7 checks) or `run_dispatch_power_flow` (Stage 6 power-flow
checks at a specified dispatch on the same network).

| Run | Kind | Inputs beyond the defaults | Hand-derived result |
|---|---|---|---|
| uncongested | OPF | AC rating 300 | 150/0 MW, 3,000 $/h, prices 20 |
| uncongested-plus10 | OPF | + demand 160 | 160/0 MW (G1 serves the increment) |
| congested | OPF | — | 90/60 MW, 3,600 $/h, prices 20/30/40, AC sensitivity −40 |
| congested-plus10 | OPF | demand 160 | AC = 80 − g2/4 ≤ 60 → 80/80 MW, 4,000 $/h (ΔG1 −10, ΔG2 +20) |
| relaxed | OPF | AC rating 70 | 70 = 75 − g2/4 → 130/20 MW, 3,200 $/h = 3,600 − 40 × 10 |
| pf-no-limit-cheapest | PF | congested; G2 from the verified uncongested run | AC flow 75 MW > 60 (reported violation) |
| pf-chosen | PF | congested; G2 = 90 | within limits; 20 × 60 + 30 × 90 = 3,900 $/h |
| breakpoint, ac-at-limit, capacity-edge, equal, infeasible | OPF | lab presets | see the Stage 7 table; capacity-edge (100 + 50 = 150 MW): +0.1 MW infeasible, −0.1 MW at 30 |

The cost rate of a power-flow dispatch (`adapter.linear_cost_rate`) is Σ offer × MW,
the same formula as the verified OPF objective.

**When a stored result counts as current** (`cases.is_current`): same kind, scenario id
and version, the installed package matches the pin, and the input fingerprint equals
what the case gives now. A PF run that takes G2 from an OPF run is current only while
that source is current and gives the same G2. Anything else is hidden and must be run
again. Runs happen only on the lesson's button.

**Exercise answers** (`model_exercises.py`, generator v1.0.0) are built only from current
records:
- The **snapshot** hashes the generator version, `adapter.CHECKS_VERSION`, the price-check
  step and tolerance, and for each run: kind, scenario, input fingerprint, status, price
  status, dispatch uniqueness, and package version, commit, and highspy version.
- The **result references** are the run ids. They are saved with the answer in local
  progress, and the runs are in the local model-run store, never in observation storage.
- A required run that is missing, stale, or failed makes the exercise **unavailable**,
  and any earlier verdict for it is cleared.
- Generators re-check what they rely on: the binding set is unchanged across a
  relaxation or a +10 MW step; the re-dispatch reproduces the verified price at C within
  1e-4; the cost change equals sensitivity × rating change within 1e-4.

Tests: `tests/test_model_lessons.py` (benchmarks, answers, snapshots, invalidation,
failures, progress) and `tests/test_model_lessons_ui.py` (AppTest).

Stage 9 adds two lesson runs: `near-breakpoint` (demand 149.95 MW, the +0.1 MW change
crosses G1's capacity: increase 25, decrease 20 $/MWh) and `zero-demand` (increase 20,
decrease infeasible), plus the `blended_rate` exercise, which rebuilds the blend from G1's
headroom and both offers and must match the re-solve within 1e-4.
