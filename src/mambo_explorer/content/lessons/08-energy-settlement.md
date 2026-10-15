---
lesson_id: energy-settlement
title: From scheduled energy to settlement
order: 8
sequence_stage: settlement
prerequisites: [power-vs-energy]
objectives:
  - Tell a financial day-ahead commitment apart from the energy actually produced or used.
  - Compute a simplified energy settlement from a day-ahead schedule, actual energy, and two prices.
  - Explain why only the deviation from the schedule is priced at the real-time price in this teaching formula.
  - Describe price exposure and volume exposure in that formula.
  - Explain why this calculation is not a complete bill.
content_version: 1.0.0
effective_date: 2026-10-11
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: iso-ne-da-rt-markets
    title: ISO New England, "Day-Ahead and Real-Time Energy Markets"
    url: https://www.iso-ne.com/markets-operations/markets/da-rt-energy-markets
    accessed: 2026-10-11
  - id: iso-ne-da-energy-bill
    title: ISO New England, settlement bill item "Day-Ahead (DA) Energy"
    url: https://www.iso-ne.com/markets-operations/settlements/understand-bill/item-descriptions/da-energy
    accessed: 2026-10-11
  - id: iso-ne-rt-energy-bill
    title: ISO New England, settlement bill item "Real-Time (RT) Energy"
    url: https://www.iso-ne.com/markets-operations/settlements/understand-bill/item-descriptions/rt-energy
    accessed: 2026-10-11
dataset_bindings: []
calculation_ids: [energy_settlement]
data_panels: []
calculators: [energy_settlement]
exercises:
  - exercise_id: total-amount
    kind: settlement
    generator: total_amount
    calculation_id: energy_settlement
  - exercise_id: deviation-component
    kind: settlement
    generator: deviation_component
    calculation_id: energy_settlement
  - exercise_id: role-reading
    kind: settlement
    generator: role_reading
    calculation_id: energy_settlement
  - exercise_id: volume-exposure
    kind: settlement
    generator: volume_exposure
    calculation_id: energy_settlement
  - exercise_id: price-exposure
    kind: settlement
    generator: price_exposure
    calculation_id: energy_settlement
glossary_terms: [MWh, MW, Synthetic, Modeled, Day-ahead schedule, Deviation, Two-settlement system, Energy settlement, Price exposure, Volume exposure]
limitations:
  - The calculator is a teaching formula with synthetic inputs. It is not ISO New England's or any market's settlement, and it reproduces no actual invoice.
  - "Energy only: no loss or uplift allocations, ancillary services, capacity, transmission, fees, bilateral or virtual transactions, and no five-minute intervals."
  - The sign convention (a buyer pays the signed amount, a seller receives it) is this app's teaching convention, not ISO New England's invoice convention.
  - A day-ahead schedule here is an input. It is not a forecast, and EIA's published demand forecasts are not day-ahead cleared quantities.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

Electricity is traded before it is made. In a **day-ahead** market, a buyer and a seller
commit, the day before, to a quantity of **energy** (MWh) for each hour at a day-ahead
price. That commitment is **financial**: it fixes a price for a quantity. The energy
actually produced or used on the day is almost never exactly the same.

**What one operator says.** ISO New England describes its markets as two settlements. The
day-ahead market settles the day-ahead commitments. The real-time market then settles the
**differences** between those commitments and what actually happened, at the real-time
price (sources below). This lesson uses that idea, and only that idea. Other markets have
their own rules, which this lesson does not describe.

**The teaching formula** (synthetic numbers, one location, one hour, energy only):

> **day-ahead component** = scheduled energy × day-ahead price
>
> **deviation component** = (actual energy − scheduled energy) × real-time price
>
> **energy settlement** = day-ahead component + deviation component

Quantities are **energy in MWh**, not power in MW. If you only know an average power, you
also need a duration: energy (MWh) = average power (MW) × hours.

**A worked SYNTHETIC example.** A buyer schedules 100 MWh at 40 per MWh and actually uses
120 MWh while the real-time price is 55. The day-ahead component is 100 × 40 = 4,000. The
deviation is +20 MWh, so the deviation component is 20 × 55 = 1,100. The total is 5,100.
Had the buyer used only 80 MWh, the deviation would be −20 MWh and the deviation component
−1,100, for a total of 2,900. The unused scheduled energy is "sold back" at the real-time
price.

**Signs.** The total is one **signed** amount. In this app a **buyer pays** it and a
**seller receives** it. A negative total is therefore a credit to a buyer (or a payment by
a seller) under these teaching assumptions. Prices can be negative too, and the same
formula applies.

**Exposure.** The scheduled quantity is priced day-ahead. Only the deviation meets the
real-time price:

- **Volume exposure:** one more MWh than scheduled changes the total by the real-time
  price.
- **Price exposure:** a higher real-time price changes the total in proportion to the
  deviation, and not at all if the deviation is zero.

If both prices happen to be equal, the total is simply actual energy × that price.

**This is not a bill.** A real settlement statement has many more items, uses its own
interval lengths and sign conventions, and follows market-specific rules. Use the
calculator below to try your own synthetic numbers.

## Technical detail

**Supported by the cited source (ISO New England only).** Its markets page describes a
day-ahead settlement of day-ahead commitments and a separate real-time settlement of the
differences from them, at the real-time LMP. Its bill-item pages say the day-ahead energy
item settles the net cleared quantity at each location hourly at the day-ahead LMP. They
say the real-time energy item settles the net deviation from day-ahead obligations at each
location at the real-time LMP, in five-minute settlement intervals, and that invoices also
carry other allocations.

**Teaching assumptions (not from the source).**
- One location and one interval, with one price per stage.
- Both quantities in MWh for the same interval.
- No loss, uplift, ancillary-service, capacity, transmission, or fee items.
- This app's own sign convention. ISO New England's invoice nets credits and charges with
  its own convention, which is not used here.

**Identity.** With D = scheduled MWh, A = actual MWh, and prices P_DA and P_RT:
S = D·P_DA + (A − D)·P_RT = A·P_RT + D·(P_DA − P_RT). So:
- when P_DA = P_RT, S = A·P;
- ∂S/∂A = P_RT (volume exposure);
- ∂S/∂P_RT = A − D (price exposure).

**Modeled prices.** The calculator can optionally copy **one** verified nodal price from
the synthetic teaching network (Model Labs) into one price field. It stays labeled
*modeled*, with its run id, package pin, and verification status. Prices that were
withheld or not verified cannot be imported, and one run never supplies both prices. A
nodal price from a one-period teaching model is not a day-ahead or real-time ISO price.

Calculation `energy_settlement` v1.0.0 (`settlement.py`). Inputs are bounded and must be
finite. Changing any input, or a price's provenance, creates a new calculation id and a
new set of exercise questions.
