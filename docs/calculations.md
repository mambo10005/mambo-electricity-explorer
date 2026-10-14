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

## `energy_settlement` v1.0.0 — Stage 11 (teaching formula; ADR 0009)

`settlement.settle(Inputs)`; one location, one interval, energy only, synthetic inputs.

| Quantity | Formula | Unit |
|---|---|---|
| Day-ahead component | scheduled_MWh × day_ahead_price | synthetic $ |
| Deviation | actual_MWh − scheduled_MWh | MWh (signed) |
| Deviation component | deviation × real_time_price | synthetic $ |
| Energy settlement S | day-ahead component + deviation component | synthetic $ (signed) |

- **Sign convention (this app's, not ISO-NE's invoice convention):** a buyer pays S, a seller
  receives S; S < 0 is a credit to a buyer or a payment by a seller.
- **Identity:** S = A·P_RT + D·(P_DA − P_RT), so P_DA = P_RT gives S = A·P. Exposures:
  ∂S/∂A = P_RT (volume), ∂S/∂P_RT = A − D (price), ∂S/∂P_DA = D.
- **Inputs:** energy 0–100,000 MWh; prices −1,000 to 10,000 per MWh; all finite; no
  booleans or strings. Optional MW entry: MWh = MW × hours, with hours required, over 0
  and up to 24.
- **Provenance:** the result keeps every input, each price's source (synthetic, or modeled
  with run id, scenario, bus, package commit, checks version, and "verified"), the formula
  version, the assumptions, and the source ids. `snapshot_id` hashes all of it.
- **Modeled-price import** (`settlement.modeled_price`) accepts only an optimal `opf.dc` run
  with `price_status == "verified"`, the current `CHECKS_VERSION`, and the pinned package.
  One run cannot supply both stages.

**Benchmarks** (hand-derived in `tests/test_settlement.py`; P_DA = 40, P_RT = 55 unless
stated):

| Case | D (MWh) | A (MWh) | Day-ahead | Deviation | S |
|---|---|---|---|---|---|
| actual = schedule | 100 | 100 | 4,000 | 0 | 4,000 |
| actual above | 100 | 120 | 4,000 | +1,100 | 5,100 |
| actual below | 100 | 80 | 4,000 | −1,100 | 2,900 |
| zero schedule | 0 | 100 | 0 | +5,500 | 5,500 |
| zero actual | 100 | 0 | 4,000 | −5,500 | −1,500 (buyer credit) |
| negative prices (−10, −20) | 100 | 120 | −1,000 | −400 | −1,400 |
| equal prices (40, 40) | 100 | 130 | 4,000 | +1,200 | 5,200 = 130 × 40 |

## `basis_exposure` v1.0.0 — Stage 12 (teaching cash flows; ADR 0010)

`basis.evaluate(Inputs)`: physical purchase of Q MWh at delivery location L, and a separate
financial hedge on H MWh referencing location H in which the buyer pays fixed K and receives
floating P_H.

| Quantity | Formula | Unit |
|---|---|---|
| Basis | P_L − P_H | synthetic $/MWh (this app's sign) |
| Physical purchase cost | Q × P_L | synthetic $ |
| Hedge receipt | H × (P_H − K) | synthetic $ (negative = buyer pays) |
| Net buyer cost | Q × P_L − H × (P_H − K) | synthetic $ (negative = credit) |
| Fixed-price component | Q × K | synthetic $ |
| Location-basis component | Q × (P_L − P_H) | synthetic $ |
| Quantity-mismatch component | (Q − H) × (P_H − K) | synthetic $ |

- **Decomposition.** Net = fixed + basis + mismatch, computed independently and checked
  (relative 1e-12, absolute 1e-6). Verified on a 2,000-point grid of bounded inputs,
  including negative prices and extreme values.
- **Identities (this contract only).** H = Q gives Q·(K + basis); H = Q with P_L = P_H gives
  Q·K.
- **Inputs.** Q and H are 0 to 100,000 MWh. P_L, P_H, and K are −1,000 to 10,000 per MWh.
  All must be finite; no booleans or strings.
- **Positions.**
  - Q = 0 and H > 0: a financial position without physical consumption.
  - H = 0: no hedge.
  - H < Q: underhedged.
  - H > Q: overhedged.

**Benchmarks** (hand-derived in `tests/test_basis.py`; K = 40):

| Case | Q | H | P_L | P_H | Physical | Receipt | Net |
|---|---|---|---|---|---|---|---|
| equal quantities and prices | 100 | 100 | 50 | 50 | 5,000 | 1,000 | 4,000 = Q·K |
| positive basis | 100 | 100 | 60 | 50 | 6,000 | 1,000 | 5,000 = 100·(40+10) |
| negative basis | 100 | 100 | 45 | 50 | 4,500 | 1,000 | 3,500 = 100·(40−5) |
| no hedge | 100 | 0 | 60 | 50 | 6,000 | 0 | 6,000 |
| underhedge | 100 | 60 | 60 | 50 | 6,000 | 600 | 5,400 (4,000+1,000+400) |
| overhedge | 100 | 150 | 60 | 50 | 6,000 | 1,500 | 4,500 (4,000+1,000−500) |
| negative prices | 100 | 100 | −20 | −10 | −2,000 | −5,000 (buyer pays) | 3,000 |
| no energy, hedge only | 0 | 100 | 60 | 50 | 0 | 1,000 | −1,000 (credit) |
| hedge raises cost | 100 | 100 | 30 | 30 | 3,000 | −1,000 | 4,000 > 3,000 unhedged |

**Modeled prices.** `basis.modeled_pair(record, delivery_bus, reference_bus)` imports two
prices from one run, at two different buses, with the Stage 11 checks applied to each. Two
modeled prices from different runs are refused. K is always synthetic.

## `time_shape` v1.0.0 — Stage 13 (teaching cash flows; ADR 0011)

`shape.evaluate(Inputs)`: one location, intervals t with elapsed duration d_t (h),
physical energy q_t (MWh), and spot price p_t; a flat-block hedge of B MW at fixed price K.

| Quantity | Formula | Unit |
|---|---|---|
| Hedge energy | h_t = B × d_t | MWh |
| Physical cost | q_t × p_t | synthetic $ |
| Hedge receipt | h_t × (p_t − K) | synthetic $ (negative = buyer pays) |
| Net cost | physical − receipt | synthetic $ (negative = credit) |
| Mismatch | r_t = q_t − h_t (positive = underhedged) | MWh |
| D, Q, R | Σ d_t, Σ q_t, Σ r_t | h, MWh, MWh |
| Average price | p̄ = Σ d_t·p_t / D (duration-weighted) | synthetic $/MWh |
| Decomposition 1 | Σ h_t·K + Σ r_t·p_t | synthetic $ |
| Decomposition 2 | B·D·K + R·p̄ + Σ r_t·(p_t − p̄) | synthetic $ |

- **Checks.** Both decompositions are computed independently and must reproduce the net
  cost. They are verified on a 432-point bounded grid: 2- and 3-interval cases, unequal
  durations, zero and large energies, negative and extreme prices, B from 0 to 750 MW, and
  K from −1,000 to 10,000. The duration-weighted p̄ is asserted separately.
- **Accounting split.** The time-shape component Σ r_t·(p_t − p̄) is an accounting split
  under this choice of p̄. When Q = B·D the aggregate mismatch is zero, but the time-shape
  component need not be.

**Benchmarks** (hand-derived in `tests/test_shape.py`; B = 100 MW, K = 40, two 1-hour
intervals unless stated):

| Scenario | q (MWh) | p | Physical | Receipt | Net | B·D·K | R·p̄ | Time-shape |
|---|---|---|---|---|---|---|---|---|
| peaky (required) | 50, 150 | 20, 80 | 13,000 | 2,000 | 11,000 | 8,000 | 0 | 3,000 |
| reversed | 150, 50 | 20, 80 | 7,000 | 2,000 | 5,000 | 8,000 | 0 | −3,000 |
| flat match | 100, 100 | 20, 80 | 10,000 | 2,000 | 8,000 | 8,000 | 0 | 0 |
| constant prices | 50, 150 | 50, 50 | 10,000 | 2,000 | 8,000 | 8,000 | 0 | 0 |
| no hedge (B = 0) | 50, 150 | 20, 80 | 13,000 | 0 | 13,000 | 0 | 10,000 | 3,000 |
| underhedge (B = 50) | 50, 150 | 20, 80 | 13,000 | 1,000 | 12,000 | 4,000 | 5,000 | 3,000 |
| overhedge (B = 150) | 50, 150 | 20, 80 | 13,000 | 3,000 | 10,000 | 12,000 | −5,000 | 3,000 |
| negative price | 50, 150 | −10, 30 | 4,000 | −6,000 | 10,000 | 8,000 | 0 | 2,000 |
| hedge only | 0, 0 | 20, 80 | 0 | 2,000 | −2,000 | 8,000 | −10,000 | 0 |
| unequal durations (1 h, 3 h) | 50, 300 | 20, 60 | 19,000 | 4,000 | 15,000 | 16,000 | −2,500 | 1,500 |

In the last row p̄ = (1·20 + 3·60)/4 = 50. An unweighted mean (40) would split the same
net into −2,000 and 1,000.

## `generation_mix` v1.0.0 — Stage 16 (ADR 0014)

`calculations.generation_mix(observations, selection)` over EIA-930 net generation by
energy source (`load_generation`; each observation's `metric` is the energy-source code).

| Quantity | Rule |
|---|---|
| Category energy | Sum of that category's **valid** values over the window (source unit). Absent and null hours add nothing; negative hours subtract. |
| Coverage per category | valid, negative, zero, null, absent counts; `unreviewed` when the code is outside the reviewed list |
| Hour sum | Sum of the categories with a valid value in that hour: "sum of reported categories", never total system generation |
| Complete hour | Every category seen anywhere in the window has a valid value in that hour |
| Window sum | Sum of hour sums over complete hours only |
| Largest category | Highest category energy (ties broken by code) |
| Shares | Only when at least one complete hour exists **and** no category is negative in any complete hour **and** the window sum is non-zero: category energy over complete hours ÷ window sum. Otherwise withheld with a reason. |

- No total system generation: the source's SYS total is not collected.
- Generation is never equated with demand; interchange and losses are never inferred.
- `status: unavailable` with no observations, mixed units, or duplicate (category, period).
- References list every observation used; exclusions list absent rows and null values.

## `dam_price_reading` v1 — Stage 19 (ADR 0016)

Lesson 14 reads one DeliveryDate of stored ERCOT DAM Settlement Point Prices at `HB_NORTH`
(`price_view.load_day`). No arithmetic beyond selection and counting:

| Quantity | Rule |
|---|---|
| Highest hour | the valid price with the largest value (ties: later file row); label = HourEnding + DSTFlag as published |
| Negative hours | count of valid prices below zero (signed as published) |
| Missing | rows whose price is blank; never zero, never filled |
| Revised | rows whose latest revision is above 1 |
| Snapshot | sha256 of (dataset, location, DeliveryDate, [(label, revision, raw value)]) |

### Future explicit import of actual prices into calculators (design only; not implemented)

Actual prices are never injected automatically. A future import must require and record:
- **market stage** (day-ahead vs real-time); a day-ahead price never stands in for a
  real-time price;
- **location** (settlement point and type) and **units** ($/MWh);
- **interval compatibility:** the calculator's interval must match the source's
  DeliveryDate/HourEnding/DSTFlag without assumed time zones;
- **revision reference:** the exact revision and document id used;
- **observation provenance:** run id, archive sha256, publication and retrieval times;
- **a statement that finality was not determined.**

No calculator may infer a contract fixed price (K) from an observed price.

## `rt_price_reading` v1 — Stage 20 (ADR 0017)

Lesson 15 reads the stored ERCOT real-time Settlement Point Prices at `HB_NORTH` for one
DeliveryDate (`rt_price_view.load_day`). There is no arithmetic beyond selection and
counting.

| Quantity | Rule |
|---|---|
| Highest interval | The valid price with the largest value (ties: later in publication order). The label is `H{DeliveryHour} I{DeliveryInterval} {DSTFlag}`, as published. |
| Negative intervals | Count of stored valid prices below zero. |
| Missing | Stored intervals with a blank price. |
| Absent | Intervals not stored at all: shown only as hours with fewer than four stored intervals, never filled. |
| Snapshot | sha256 of (dataset, location, DeliveryDate, [(label, revision, raw value)]). |

### Day-ahead / real-time comparison: prerequisites (design only; nothing implemented)

**Stage 22 status (ADR 0019, `docs/interval-alignment.md` §9):**
- prerequisite 2 (interval compatibility) is **blocked by unavailable evidence**: no
  official label definition, so no mapping is accepted;
- 1, 3, and 5 are partially verified;
- 4 is verified;
- 6 and 7 are unresolved.

**Stage 23 (ADR 0020):** M1 can be used as an opt-in, approval-gated operational assumption.
- Under it, an hour is `complete_under_assumption` only when exactly one selected valid price
  exists for each interval M1 expects (1–4) and for the day-ahead hour.
- That is alignment completeness, not collection coverage, revision availability, finality, or
  official semantics.
- No attributable approval is recorded yet.

**Stage 24 prerequisites:**
1. an active scoped approval of M1;
2. complete alignment under the selected revision policy;
3. an explicit, justified real-time aggregation definition;
4. stated non-settlement and non-backtest limitations.

The interval-alignment diagnostic computes no price figure. Candidate hourly summaries
(arithmetic, duration-weighted, energy-weighted, settlement amount) are researched in
`docs/interval-alignment.md` §8, and none is implemented.

A future comparison of the day-ahead hourly price (NP4-190-CD) with real-time 15-minute
prices (NP6-905-CD) must establish all of the following first:

1. **Same verified location:** the same settlement point name and type in both reports
   (today: `HB_NORTH`, hub).
2. **Compatible operating intervals:** evidence that the day-ahead `HourEnding hh:00` and the
   real-time `DeliveryHour hh` with intervals 1–4 describe the same hour of the same
   Operating Day. Neither report states a time zone.
3. **Explicit DST handling:** the observed representation on both DST transition days
   (DSTFlag, repeated or missing hours), with matching rules.
4. **Verified price definitions:** day-ahead hub price (aggregated Shift Factors per hour)
   vs. real-time hub price (time-weighted Hub Bus prices plus RTRDP, floored per 15
   minutes).
5. **Revision selection:** which revision of each value is used (e.g. latest as of a stated
   time), recorded with document ids.
6. **Complete subinterval coverage:** all four real-time intervals of the hour present and
   valid. An hour with fewer is incomplete and is not compared.
7. **A defined aggregation:** an arithmetic mean of four 15-minute prices is **not**
   automatically an energy-weighted settlement price; the weighting must be stated and
   justified.

A comparison must never average the available intervals and label an incomplete hour
complete, never present the difference as a trading result or backtest, and never imply that
either price is final.

