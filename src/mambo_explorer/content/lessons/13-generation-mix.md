---
lesson_id: generation-mix
title: Reading the actual generation mix
order: 13
sequence_stage: fundamentals
prerequisites: [reading-demand]
objectives:
  - State what EIA-930 net generation by energy source is, and which categories EIA publishes.
  - Tell net generation apart from installed capacity, fuel consumption, and marginal generation.
  - Explain why a category that is absent from an hour is not zero.
  - Read a negative value as net storage (or station use above output), not as an error.
  - Explain why the generation mix alone does not show which unit or fuel set the price.
content_version: 1.0.0
effective_date: 2026-10-12
authored_by: Claude (AI agent)
authored_at: 2026-10-12
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: eia930-instructions
    title: Form EIA-930 instructions (OMB 1905-0129), "Data Type" and "Data Code" for NG; energy storage examples; energy balance
    url: https://www.eia.gov/survey/form/eia_930/instructions.pdf
    accessed: 2026-10-12
  - id: eia930-about
    title: EIA, About the EIA-930 data (data elements; imputation; net generation definition)
    url: https://www.eia.gov/electricity/930-content/about.html
    accessed: 2026-10-12
  - id: eia-api-fuel-type-data
    title: EIA API v2 route electricity/rto/fuel-type-data, "Hourly Generation by Energy Source" (metadata read with a key)
    url: https://www.eia.gov/opendata/browser/electricity/rto/fuel-type-data
    accessed: 2026-10-12
dataset_bindings:
  - dataset: EIA-930
    route: electricity/rto/fuel-type-data
    entity: ERCO
    metrics: [NG]
calculation_ids: [generation_mix]
data_panels: [generation_mix]
exercises:
  - exercise_id: largest-category
    kind: generation
    generator: largest_category
    calculation_id: generation_mix
  - exercise_id: negative-meaning
    kind: generation
    generator: negative_meaning
    calculation_id: generation_mix
  - exercise_id: absent-category-hours
    kind: generation
    generator: absent_category_hours
    calculation_id: generation_mix
  - exercise_id: partial-sum-not-total
    kind: generation
    generator: partial_sum_not_total
    calculation_id: generation_mix
  - exercise_id: mix-not-price
    kind: generation
    generator: mix_not_price
    calculation_id: generation_mix
glossary_terms: [Net generation, Energy source category, Installed capacity, Fuel consumption, Marginal generation, Net storage, Absent row, Category sum, EIA-930, MWh, Period label, Revision]
limitations:
  - One balancing authority (ERCOT, EIA code ERCO). The categories shown are the ones EIA publishes for it; the source's total net generation (data code SYS) is not collected, so no total system generation is shown.
  - Whether ERCOT reports storage charging as negative net generation or within demand is not stated per balancing authority by EIA. Values are shown signed, exactly as published.
  - Generation is not demand. Interchange and losses are never inferred from a difference.
  - No capacity, fuel, emissions, plant-level, or price data. Nothing here identifies the price-setting unit or fuel.
  - Values are the latest revision collected on this computer. EIA can revise them later, and a revision changes the exercises.
  - Hours are shown by their UTC source labels, not converted to local clock time.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

**What this data is.** Each hour, a balancing authority reports to EIA how much
electricity its generating units produced, split by **energy source**: coal, natural gas,
nuclear, hydro, solar, wind, batteries, and a few more. EIA calls the measure **net
generation**: the metered output of the generating units the balancing authority manages
or can see. Small generators on the distribution system, such as rooftop solar, are
typically not included. The values are in **MWh** per hour, the same unit as demand.

**The categories.** EIA's form lists fifteen codes, for example `COL` (coal), `NG`
(natural gas), `NUC` (nuclear), `WAT` (hydro), `SUN` (solar), `WND` (wind), `BAT`
(battery storage), `PS` (pumped storage), `OTH` (other), and `UNK` (unknown). Two things
to know:

- **Other can hide small categories.** When a category has three or fewer generators and
  confidentiality rules apply, the balancing authority reports it under `OTH`.
- **The list can change.** This app keeps any category the source publishes, even one not
  in the list it reviewed, and marks it so.

**What it is not.**
- Not **installed capacity**: how much a plant *could* produce. A fuel with a small share
  of generation may still have a lot of capacity sitting idle, or none at all.
- Not **fuel consumption**: how much coal or gas was burned.
- Not **marginal generation**: the unit that would change its output if demand changed a
  little. Lessons 5 to 7 show that this depends on offers and constraints.

**Absent is not zero.** If a category has no row for an hour, the source published no
value. The app shows it as absent and never fills it. A zero is only a zero when the
source reported one.

**Negative values.** The EIA-930 instructions say that for hours when storage devices
store more electricity than they generate, the net storage is reported as **negative** net
generation for that category. Station use that exceeds a plant's output can also give a
negative value. So a negative number is a sign to read, not a mistake to remove. EIA's
"About the EIA-930 data" page adds a complication: EIA has asked balancing authorities to
count pumped-storage charging as demand instead, and it accepts negative values where a
balancing authority says it reports battery charging. Which convention ERCOT follows is
not stated. This app shows the sign exactly as published and says so.

**Adding categories up.** The sum of the categories reported in an hour is just that: the
sum of what was reported. The instructions say the by-source values are expected to equal
the total "to the extent possible", and that total is not collected here. So the app never
calls the sum "total system generation", and it never says generation equals demand. The
difference between generation and demand is **not** interchange or losses; those are
separate reported quantities.

**Percentages.** A share only makes sense when every category is present and none is
negative. Otherwise a "share" of a signed, incomplete sum would mislead, and the app
withholds it and says why.

**Mix is not price.** A fuel generating the most energy is not, for that reason, the one
setting the price. Which unit is marginal depends on offers, limits, and dispatch, none of
which are in this data.

## Technical detail

- **Route and identity.** EIA API v2 route `electricity/rto/fuel-type-data` ("Hourly
  Generation by Energy Source"), frequency `hourly` (UTC labels), facets `respondent` and
  `fueltype`, data column `value` (alias "Net Generation", units `megawatthours`). Each
  observation's identity includes the category code, and generation is stored in its own
  namespace, so it can never overwrite a demand or forecast observation.
- **Category codes** (Form EIA-930 instructions, Data Code for data type NG): COL, NG, NUC,
  OIL, WAT, PS, SUN, SNB, WND, WNB, BAT, OES, GEO, OTH, UNK. The API facet list read on
  2026-10-12 also had `UES`, which the instructions read do not define; it is kept and
  flagged as unreviewed.
- **Storage conventions** (instructions): pumped storage, batteries, and other storage
  report net storage as negative net generation for the hour; hydro combined with pumped
  storage may also be negative; total net generation may be negative when storage exceeds
  the entire system's generation. The instructions also move storage charging out of
  demand and into negative generation, while the "About" page describes EIA asking BAs to
  report pumped-storage charging as demand instead. The lesson discloses this rather than
  resolving it.
- **Dual-fuel units** are reported under the fuel actually used if known, else the
  primary fuel; the instructions say not to report them as unknown.
- **Revisions.** EIA says reporting errors above 10 MWh in an hour are resubmitted within
  30 days. This app keeps every revision; the exercises use the latest one and change
  when it changes.
- **Calculation `generation_mix` v1.0.0:** per-category energy is the sum of valid hourly
  values (absent and null hours add nothing); an hour is complete when every category
  seen in the window has a valid value; the hour sum is the sum of reported categories;
  shares are offered only over complete hours with no negative value, with the denominator
  being the sum of all categories over those hours.
- **Period labels** are compared as UTC labels only; the hour-ending convention is not
  verified for the API field, so no interval boundaries are derived.
