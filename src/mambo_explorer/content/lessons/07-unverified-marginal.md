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
content_version: 1.1.1
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
model_bindings: [breakpoint, near-breakpoint, ac-at-limit, capacity-edge, zero-demand, equal, infeasible]
model_panels: [unverified_marginal]
exercises:
  - exercise_id: withheld-reason
    kind: model
    generator: withheld_reason
    calculation_id: dc_opf
  - exercise_id: blended-rate
    kind: model
    generator: blended_rate
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
glossary_terms: [Synthetic, Modeled, Marginal cost, Average change rate, Breakpoint, Modeled nodal price, Dispatch, Optimal power flow]
limitations:
  - The price check tests only ±0.1 MW of demand at each bus. Passing it does not prove that the dispatch or the solver's dual is unique, or that the price holds for larger changes.
  - A perturbation can cross into a different constraint regime. If a limit is reached inside a 0.1 MW change, that change's average rate blends two regimes; it is never a local marginal rate.
  - Synthetic network and offers; lossless DC model; not any ISO's prices or rules.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

In the previous lesson a single price described both directions: one more MW of demand
and one less MW changed the cost at the same rate. That is not always true. This lesson
runs cases where the app **withholds** prices, and says exactly why.

**How the check works.** For each bus, the app re-solves the model twice: once with a
little more demand (+0.1 MW) and once with a little less (−0.1 MW). From each re-solve it
computes an **average rate**: how much the cost rate changed, divided by the 0.1 MW
change. These are averages over a small but finite change, not "the" marginal cost at
one exact point.

**A breakpoint.** Suppose demand exactly uses up the cheap generator's capacity. More
demand must come from the dearer generator; less demand is saved at the cheap one. The
two average rates **differ**. The run is still optimal, and its dispatch and cost are
verified. But **a unique two-sided marginal price was not verified for this run**, so
the app shows both average rates instead of one number. The same happens when a line
sits exactly at its rating.

**Close to a breakpoint.** Now suppose demand is a hair *below* that capacity, closer
than 0.1 MW. The +0.1 MW change starts on the cheap generator and finishes on the dearer
one, so its average **blends** two rates and matches neither. That is why the app never
calls these averages local marginal rates.

**One direction is infeasible.** Each direction is checked on its own:

- If demand equals the total capacity, the **+0.1 MW** change is infeasible (there is
  nothing left to serve it), while the −0.1 MW change is fine.
- If there is no demand at all, the **−0.1 MW** change is infeasible (generators cannot
  produce less than zero), while the +0.1 MW change is fine.

Either way, one direction is missing, so there is no two-sided price to verify. The run
itself is still optimal: an infeasible *change* is not an infeasible *run*.

**Equal offers.** If both generators offer the same price, many splits between them cost
exactly the same. The dispatch is **not unique**, yet the cost is known, and the price
check can still pass. That is different from an **infeasible** run, where no dispatch
meets demand at all and nothing is shown.

So two separate questions are asked of every run:

1. *Is the dispatch unique?* (Could another split cost the same?)
2. *Was a two-sided marginal price verified?* (Did a little more and a little less demand
   change the cost at the same average rate as the reported price?)

The answer to one does not decide the other.

## Technical detail

**Formulas.** With C(D) the optimal cost rate in synthetic $/h and h = 0.1 MW:

- increase rate = [C(D + h) − C(D)] / h
- decrease rate = [C(D) − C(D − h)] / h

Both are in ($/h) per MW, which is $/MWh. Over the one-hour teaching interval, a change of
h MW is h MWh of energy and changes the interval cost by ΔC × 1 h dollars, so the same
number is also dollars per MWh of energy. The tables show each direction's cost-rate
change C(D ± h) − C(D) in $/h (negative for a decrease that saves money) and its rate.

**What the averages can and cannot say.** C is piecewise linear and convex in demand (a
linear program). If no breakpoint lies in [D − h, D + h], both averages equal the local
slope. If they differ, a breakpoint lies somewhere in that range, possibly exactly at D.
The check cannot tell where, so neither average is presented as a local (one-sided)
marginal rate. When the breakpoint lies inside a change, that change's average is a
weighted blend of the slopes on either side.

The solver still reports a dual for every bus, and at a breakpoint it is a legitimate
number. This lesson's interpretation is that it is a subgradient; what the app checks numerically is
that it lies between the two averages in these cases. It is withheld
not because it is meaningless, but because no single number can equal both directions, so
it cannot be presented as *the* marginal cost.

Prices are shown only if, at every bus, both re-solves are feasible and their average
rates agree with each other and with the reported price within 10⁻⁴ $/MWh (a negative
load at a bus without demand is a mathematical perturbation for the check only). What
this check establishes is limited:

- It concerns only the tested perturbations. It is not a proof of global price validity.
- It does not establish uniqueness of the dispatch or of the duals. Non-uniqueness of the
  dispatch is tested separately, by shifting output between equal-offer generators and
  re-checking the limits with the verified power flow.
- Clearer wording does not make the check numerically stronger. The decisions it makes
  are the same as before; only their explanation changed.

An infeasible run carries no dispatch, cost, or prices, and this model never sheds load
to restore feasibility. A run that fails any of its own checks shows no results at all.
