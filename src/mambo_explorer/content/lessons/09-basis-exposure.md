---
lesson_id: basis-exposure
title: Why a hedge at another location leaves basis exposure
order: 9
sequence_stage: financial-contracts-risk
prerequisites: [location-prices, energy-settlement]
objectives:
  - Tell a physical energy purchase apart from a separate financial hedge.
  - Compute the physical cost, the hedge receipt or payment, and the net cost in a simplified fixed-price hedge.
  - Explain the sign of locational basis and why a hedge at another location leaves it.
  - Explain how a mismatch between hedge and physical quantities leaves price exposure.
  - Explain why a hedge can raise cost in some scenarios and does not remove all risk.
content_version: 1.0.0
effective_date: 2026-10-11
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: ferc-glossary
    title: FERC, market-assessment glossary (entries Basis, Swaps, Hedging)
    url: https://www.ferc.gov/industries-data/market-assessments/overview/glossary
    accessed: 2026-10-11
dataset_bindings: []
calculation_ids: [basis_exposure]
data_panels: []
calculators: [basis_exposure]
exercises:
  - exercise_id: net-cost
    kind: basis
    generator: net_cost
    calculation_id: basis_exposure
  - exercise_id: hedge-cash-flow
    kind: basis
    generator: hedge_cash_flow
    calculation_id: basis_exposure
  - exercise_id: basis-component
    kind: basis
    generator: basis_component
    calculation_id: basis_exposure
  - exercise_id: mismatch-component
    kind: basis
    generator: mismatch_component
    calculation_id: basis_exposure
  - exercise_id: hedge-effect
    kind: basis
    generator: hedge_effect
    calculation_id: basis_exposure
glossary_terms: [MWh, Synthetic, Modeled, Basis, Fixed-for-floating hedge, Reference location, Quantity mismatch, Price exposure, Modeled nodal price]
limitations:
  - The hedge here is a simplified teaching cash flow with synthetic terms. It is not an exchange contract, a legal or regulatory classification, or a valuation, and it delivers no electricity.
  - "One interval and one price per location: no margin, credit, fees, timing, or settlement-period details."
  - The fixed price K is a synthetic assumption. It is never inferred from a model run, and nothing here is a forward price.
  - Buses A, B, and C are synthetic locations in a teaching model, not market hubs.
  - The identities hold for this teaching contract, not for every real-world hedge.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

A buyer who needs electricity at one place often manages its price risk with a separate
**financial** agreement that refers to the price at another place. This lesson shows what
is left over when the two places' prices differ.

**What the cited source says (concepts only).** FERC's market glossary describes three
ideas this lesson relies on (sources below):
- **Basis** is the price difference between otherwise identical products in different
  markets.
- In a **fixed-for-floating swap**, one party pays a fixed price in return for receiving a
  changing price.
- **Hedging** means protecting value against price changes with something whose price
  change is expected to offset the loss.

The glossary's examples are from natural gas. The scenario below is a **synthetic teaching
example** built on those ideas, not a description of any real contract.

**The scenario (synthetic):**

- The buyer purchases **Q** MWh of actual energy at **delivery location L**, at price
  **P_L**.
- Separately, the buyer has a **financial hedge** on **H** MWh. It refers to the price
  **P_H** at a **reference location**. The buyer **pays a fixed price K** and **receives
  P_H** for each hedged MWh. The hedge moves money, not electricity.

> physical purchase cost = Q × P_L
>
> hedge receipt = H × (P_H − K) — negative means the buyer pays
>
> net buyer cost = Q × P_L − H × (P_H − K) — negative means a credit to the buyer

**Basis.** Here basis = P_L − P_H (this app's sign convention). The hedge pays on P_H,
but the energy is bought at P_L, so the basis is not covered.

**Where the net cost comes from.** The same net cost can be split into three parts:

> net buyer cost = Q × K + Q × (P_L − P_H) + (Q − H) × (P_H − K)

- **Fixed-price component (Q × K):** what the buyer would pay if the hedge worked perfectly.
- **Location-basis component (Q × basis):** positive basis raises the cost; negative basis
  lowers it.
- **Quantity-mismatch component ((Q − H) × (P_H − K)):** zero only when the hedge quantity
  matches the energy bought. Under- or overhedging leaves part of the position exposed to
  the reference price.

If H = Q, the net cost is Q × (K + basis). If also P_L = P_H, it is exactly Q × K. These
follow from this teaching contract, not from every real hedge.

**A hedge can raise cost.** If the reference price ends below K, the buyer pays on the hedge,
and the net cost can be higher than with no hedge at all. A hedge changes exposure; it does
not guarantee savings or remove all risk.

**A financial position with no energy.** If Q = 0 but H > 0, the buyer bought no energy yet
still has hedge cash flows. That is a purely financial position, not ordinary procurement.

## Technical detail

**Algebra.** Q·P_L − H·(P_H − K) = Q·K + Q·(P_L − P_H) + Q·(P_H − K) − H·(P_H − K)
= Q·K + Q·(P_L − P_H) + (Q − H)·(P_H − K). The calculator computes the three components
independently and checks that they reproduce the net cost.

**Source-supported versus assumed.**
- *Supported (FERC glossary, general or natural-gas context):* the concepts of basis as a
  locational price difference, a fixed-for-floating swap, and hedging.
- *Assumed (synthetic teaching contract):*
  - one interval and one price per location;
  - the buyer pays K and receives P_H on H MWh;
  - no margin, credit, fees, or timing;
  - the basis sign P_L − P_H;
  - nonnegative quantities.

**Modeled prices.** Optionally, P_L and P_H can be copied **together** from **one** verified
economic-dispatch run, at two different buses, so their difference is a modeled basis
within one modeled state. The same checks as lesson 8 apply: optimal status, verified
prices, current checks, and the pinned package. Withheld, failed, infeasible, or stale runs
are refused. Editing an imported price makes it synthetic again. K is never taken from a
run, and the buses are synthetic locations, not hubs.

Calculation `basis_exposure` v1.0.0 (`basis.py`). Inputs are bounded and must be finite.
Changing any input, or a price's provenance, creates a new calculation id and new exercise
questions.
