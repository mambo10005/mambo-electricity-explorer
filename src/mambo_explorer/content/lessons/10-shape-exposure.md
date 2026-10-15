---
lesson_id: shape-exposure
title: Why matching total energy does not remove shape exposure
order: 10
sequence_stage: financial-contracts-risk
prerequisites: [power-vs-energy, basis-exposure]
objectives:
  - Tell a flat hedge in MW apart from consumption that varies in MWh from interval to interval.
  - Compute interval hedge energy from hedge power and an explicit duration.
  - Identify underhedged and overhedged intervals.
  - Explain why equal total energy can still leave a price-weighted residual cost.
  - Explain that a hedge can raise or lower realized cost and does not guarantee savings.
content_version: 1.0.0
effective_date: 2026-10-11
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: eia-texas-heat-wave-2011
    title: "EIA, Today in Energy: Texas Heat Wave, August 2011: Nature and Effects of an Electricity Supply Shortage (2011-09-09)"
    url: https://www.eia.gov/todayinenergy/detail.php?id=3010
    accessed: 2026-10-11
dataset_bindings: []
calculation_ids: [time_shape]
data_panels: []
calculators: [time_shape]
exercises:
  - exercise_id: interval-status
    kind: shape
    generator: interval_status
    calculation_id: time_shape
  - exercise_id: shape-component
    kind: shape
    generator: shape_component
    calculation_id: time_shape
  - exercise_id: mw-vs-mwh
    kind: shape
    generator: mw_vs_mwh
    calculation_id: time_shape
  - exercise_id: profile-compare
    kind: shape
    generator: profile_compare
    calculation_id: time_shape
  - exercise_id: negative-receipt
    kind: shape
    generator: negative_receipt
    calculation_id: time_shape
glossary_terms: [MW, MWh, Synthetic, Flat-block hedge, Load shape, Quantity mismatch, Time-shape component]
limitations:
  - The intervals, prices, and hedge are synthetic. Nothing here is an exchange block product, a forward curve, or a contract valuation, and the hedge delivers no electricity.
  - Intervals are identifiers with elapsed durations, not calendar times. There are no time zones, DST, holidays, or market calendars.
  - The time-shape component is an accounting split under one chosen decomposition, not a universal industry risk metric.
  - "One location only: no basis, margin, credit, fees, or settlement timing."
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

A buyer's use of electricity changes through the day, but a simple hedge can be
**flat**: the same number of megawatts in every interval. This lesson shows what is left
over when a flat hedge meets a varying load.

**Power versus energy, again.** The hedge is a constant power **B** in MW. In an interval
lasting **d** hours it covers **h = B × d** MWh of energy. The buyer's use in that
interval is **q** MWh. Comparing them needs the same unit, so the hedge's MW are first
turned into MWh with the interval's duration.

**The teaching contract** (synthetic, one location). In each interval the buyer pays the
spot price **p** for the energy it uses. Separately, on the hedge energy, the buyer pays a
fixed price **K** and receives the spot price:

> physical cost = q × p
>
> hedge receipt = h × (p − K), and a negative value means the buyer pays
>
> net cost = physical cost − hedge receipt, and a negative value means a credit

**Interval mismatch.** If q is larger than h, the interval is **underhedged**; if
smaller, **overhedged**. The difference q − h is bought (or, in effect, sold back) at that
interval's spot price.

**Equal totals are not equal exposure.** Suppose the hedge covers exactly the buyer's total
energy over the day, but the buyer uses less than the hedge in a cheap hour and more in an
expensive hour. The surplus in the cheap hour is worth little, while the shortfall in the
expensive hour costs a lot. The two do not cancel, so a residual cost remains even though
the totals match. Reverse the shape and the residual flips sign.

**Two ways to split the total.** The calculator shows both:

1. **Fixed price on the hedge energy + the residual energy at spot prices.**
2. **Fixed hedge component + aggregate energy mismatch + time-shape component.** The
   aggregate mismatch uses the duration-weighted average price p̄. The time-shape
   component collects what is left: each interval's mismatch times how far its price sits
   from that average.

The second split is an **accounting decomposition** chosen for teaching. It is not a
standard industry risk measure.

**A hedge can raise or lower the realized cost.** Compare the total with the cost without
any hedge (q × p summed): depending on the prices, the hedge can do either. A hedge changes
exposure; it does not guarantee savings.

**Real-market context (cited).** An EIA analysis of an August 2011 heat wave in Texas
describes a 16-hour weekday on-peak block. Within it, afternoon "super-peak" hours traded
far above the morning hours, and the high and low hours were averaged together in the
block's price. That is the same idea as this lesson: one block price covers intervals with
very different prices. The lesson uses none of the article's numbers.

## Technical detail

**Definitions.** For intervals t with duration d_t, use q_t, spot p_t, flat hedge power B,
and fixed price K:
- h_t = B·d_t
- r_t = q_t − h_t
- D = Σ d_t, Q = Σ q_t, R = Σ r_t
- p̄ = Σ d_t·p_t / D (duration-weighted)

**Identities** (this teaching contract):

- total net = Σ (q_t·p_t − h_t·(p_t − K)) = Σ h_t·K + Σ r_t·p_t
- Σ h_t = B·D, so total net = B·D·K + Σ r_t·p_t
- Σ r_t·p_t = R·p̄ + Σ r_t·(p_t − p̄), an identity for any p̄, because Σ r_t·(p_t − p̄) =
  Σ r_t·p_t − R·p̄

With p̄ duration-weighted, the components are a fixed hedge component **B·D·K**, an
aggregate energy mismatch **R·p̄**, and a time-shape component **Σ r_t·(p_t − p̄)**.
- When Q = B·D, R = 0 and the aggregate mismatch vanishes, but the time-shape component
  generally does not.
- With constant prices it is zero.
- With a flat load matching the hedge in every interval, every r_t is zero.

**Source-supported versus assumed.**
- *Supported (EIA, 2011):* in that ERCOT episode, a multi-hour on-peak block spanned
  hours with very different prices, and block prices reflected high and low hours averaged
  together.
- *Assumed (synthetic teaching contract):*
  - the flat-block hedge itself and its pay-fixed, receive-spot cash flows;
  - one location, with elapsed-duration intervals and no calendars;
  - the choice of p̄ and the decomposition labels.

No model prices are imported: one-period OPF runs are not stitched into a time series.

Calculation `time_shape` v1.0.0 (`shape.py`). Inputs are bounded and must be finite:
durations over 0 and up to 24 h, energies and hedge power nonnegative. Changing any input
creates a new calculation id and new exercise questions.
