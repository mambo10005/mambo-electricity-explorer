---
lesson_id: power-vs-energy
title: Power versus energy (MW and MWh)
order: 1
sequence_stage: fundamentals
prerequisites: []
objectives:
  - Tell power (MW, a rate) apart from energy (MWh, an amount).
  - Convert between them using energy = average power × duration.
  - Explain why an hourly MWh value and an average MW value can share a number only when the duration is exactly one hour.
content_version: 1.0.0
effective_date: null
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: eia930-instructions
    title: Form EIA-930 instructions, "General instructions" (hourly integrated values in megawatts)
    url: https://www.eia.gov/survey/form/eia_930/instructions.pdf
    accessed: 2026-10-11
  - id: eia-gridmonitor-about
    title: EIA Hourly Electric Grid Monitor — about the data
    url: https://www.eia.gov/electricity/gridmonitor/about
    accessed: 2026-10-11
dataset_bindings: []
calculation_ids: [power_energy]
data_panels: [power_energy_example]
exercises:
  - exercise_id: synthetic-energy
    kind: concept
    generator: power_energy_synthetic
    calculation_id: power_energy
  - exercise_id: one-hour-equivalence
    kind: concept
    generator: one_hour_equivalence
    calculation_id: power_energy
glossary_terms: [MW, MWh, Power, Energy, EIA-930, UTC, Period label]
limitations:
  - All numbers in this lesson are a synthetic example, not observations.
  - The source reports hourly values. This lesson does not say when each hour starts or ends, because the API does not state how its period labels map to clock intervals.
implementation_status: implemented
---

## Beginner

**Power** is how fast electricity is being made or used right now. It is measured in
**megawatts (MW)**. Think of it as the speed of a car.

**Energy** is how much electricity was made or used over some time. It is measured in
**megawatt-hours (MWh)**. Think of it as the distance the car travelled.

They are linked by time:

> **energy (MWh) = average power (MW) × duration (hours)**

So 100 MW kept up for 3 hours is 300 MWh. The same 300 MWh spread over 6 hours is an
average of only 50 MW.

**Why the numbers sometimes match.** EIA publishes hourly demand with the unit
**MWh**. Each value covers exactly one hour. When the duration is exactly 1 hour, the
formula gives *energy = average power × 1*, so a value of 48,000 MWh for one hour equals
an average power of 48,000 MW during that hour. The numbers match **only because the
duration is one hour**. This app keeps the unit as the source gives it (MWh) and does
not relabel values as MW.

The example below uses **synthetic** (made-up) numbers so you can practise the
conversion. It is not real data.

## Technical detail

EIA-930 instructions ask balancing authorities to "report all data as hourly
integrated values in megawatts by hour ending time". An hourly integrated MW value is
the time-weighted average power over the hour, and that is numerically equal to the
energy in MWh for a one-hour duration. The EIA API returns these values with the unit
string `megawatthours`, and this application stores and displays exactly that unit.

The hour-ending wording in the form instructions describes how respondents report
to EIA. The API's own documentation does not say how its `period` labels map to clock
intervals. This application therefore uses period labels only as labels, and does not
compute interval start or end times (see the source register). That does not affect
this lesson: the conversion depends only on the duration (1 hour), not on where the
hour falls.

Calculation `power_energy` v1: `energy_mwh = average_mw × hours` and
`average_mw = energy_mwh ÷ hours`. It refuses a duration that is zero, negative, or
not a number, and it refuses inputs that give both or neither of the two quantities.
