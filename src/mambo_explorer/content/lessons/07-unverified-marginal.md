---
lesson_id: unverified-marginal
title: When one marginal number is not verified
order: 7
sequence_stage: fundamentals
prerequisites: [location-prices]
objectives:
  - Explain why adding and removing demand can change the cost at different rates.
  - Recognize when one direction of a small demand change is infeasible.
  - Tell a non-unique dispatch apart from an infeasible run.
  - Explain why dispatch uniqueness and price verification are separate questions.
content_version: 1.0.0
effective_date: null
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources: []
dataset_bindings: []
calculation_ids: [dc_opf]
data_panels: []
model_bindings: [breakpoint, ac-at-limit, capacity-edge, equal, infeasible]
model_panels: [unverified_marginal]
exercises:
  - exercise_id: withheld-reason
    kind: model
    generator: withheld_reason
    calculation_id: dc_opf
  - exercise_id: infeasible-direction
    kind: model
    generator: infeasible_direction
    calculation_id: dc_opf
  - exercise_id: nonunique-vs-infeasible
    kind: model
    generator: nonunique_vs_infeasible
    calculation_id: dc_opf
  - exercise_id: uniqueness-vs-price
    kind: model
    generator: uniqueness_vs_price
    calculation_id: dc_opf
glossary_terms: [Synthetic, Modeled, Marginal cost, Breakpoint, Modeled nodal price, Dispatch, Optimal power flow]
limitations:
  - The price check tests only ±0.1 MW of demand at each bus. Passing it does not prove that the dispatch or the solver's dual is unique, or that the price holds for larger changes.
  - A perturbation can cross into a different constraint regime. Near a breakpoint, a one-sided rate can mix two regimes.
  - Synthetic network and offers; lossless DC model; not any ISO's prices or rules.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

In the previous lesson a single price described both directions: one more MW of demand
and one less MW changed the cost at the same rate. That is not always true. This
lesson runs cases where the app **withholds** prices, and says why.

**A breakpoint.** Suppose demand exactly uses up the cheap generator's capacity. One
more MW must come from the dearer generator, while one less MW is saved at the cheap
generator. Adding and removing demand change the cost at **different rates**. The run
is still optimal and its dispatch and cost are verified. But for this run, **a unique
two-sided marginal price was not verified**, so the app shows both one-sided rates
instead of one number. The same thing can happen when a line sits exactly at its
rating.

**One direction is infeasible.** If demand equals the total capacity, one more MW cannot
be served at all. One less MW is fine. With one side missing, there is no two-sided
price to verify.

**Equal offers.** If both generators offer the same price, many splits between them cost
exactly the same. The dispatch is **not unique**, yet the cost is known, and the price
check can still pass. That is different from an **infeasible** run, where no dispatch
meets demand at all and nothing is shown.

So two separate questions are asked of every run:

1. *Is the dispatch unique?* (Could another split cost the same?)
2. *Was a two-sided marginal price verified?* (Did a little more and a little less demand
   change the cost at the same rate as the reported price?)

The answer to one does not decide the other.

## Technical detail

The solver still reports a dual for every bus, and at a breakpoint it is a legitimate
number: a subgradient that lies between the one-sided rates in these cases. It is
withheld not because it is meaningless, but because no single number can equal both
one-sided derivatives, so it cannot be presented as *the* marginal cost.

The per-run check re-solves with ±0.1 MW of demand at each bus (a negative load at the
generator buses, used only as a mathematical perturbation). Prices are shown only if, at
every bus, both re-solves are feasible and their rates agree with each other and with
the reported price within 10⁻⁴ $/MWh. What this check establishes is limited:

- It concerns only the tested perturbations. It is not a proof of global price validity.
- It does not establish uniqueness of the dispatch or of the duals. Non-uniqueness of the
  dispatch is tested separately, by shifting output between equal-offer generators and
  re-checking the limits with the verified power flow.
- A ±0.1 MW step can cross a constraint boundary that lies closer than 0.1 MW. Then a
  one-sided rate mixes two regimes. The run's prices are still withheld in that case,
  but the reported one-sided rate is a blend, not either regime's marginal cost.

An infeasible run carries no dispatch, cost, or prices, and this model never sheds load
to restore feasibility.
