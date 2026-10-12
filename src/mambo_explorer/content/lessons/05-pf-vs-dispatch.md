---
lesson_id: pf-vs-dispatch
title: Power flow versus economic dispatch
order: 5
sequence_stage: fundamentals
prerequisites: [power-vs-energy]
objectives:
  - Say what a power flow does with a dispatch it is given, and what an optimal power flow chooses.
  - Explain why a dispatch that respects every limit is not automatically the cheapest one.
  - Tell a limit that power flow only reports apart from a limit that optimal power flow enforces.
content_version: 1.0.0
effective_date: null
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources: []
dataset_bindings: []
calculation_ids: [dc_power_flow, dc_opf]
data_panels: []
model_bindings: [uncongested, congested, pf-no-limit-cheapest, pf-chosen]
model_panels: [pf_vs_opf]
exercises:
  - exercise_id: pf-reports-violation
    kind: model
    generator: pf_reports_violation
    calculation_id: dc_power_flow
  - exercise_id: feasible-not-cheapest
    kind: model
    generator: feasible_not_cheapest
    calculation_id: dc_opf
glossary_terms: [MW, Synthetic, Modeled, Dispatch, Power flow, Optimal power flow, Offer, Line rating, Reference bus, Cost rate]
limitations:
  - Every number in this lesson is modeled on a synthetic three-bus network with synthetic offers. Nothing is calibrated to ERCOT or any real market.
  - The model is lossless (DC approximation). It ignores voltages, reactive power, losses, start-up costs, and time.
  - Real system operators use much larger and more detailed models and market rules. This lesson does not describe how any operator dispatches.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

Two different questions can be asked about the same small network.

**Power flow** answers: *"If the generators produce exactly this much, where does the
power go?"* You give it the **dispatch** (how much each generator produces). It works
out the flow on every line. It does not choose anything and it does not enforce any
limit. If a line would carry more than its **rating**, power flow simply reports it.

**Optimal power flow** answers: *"Which dispatch meets demand at the lowest total cost
without breaking any limit?"* It chooses the dispatch itself, using each generator's
**offer** (its cost per MWh) and every capacity and line rating.

This lesson runs both on the same **synthetic** three-bus network. Press the run button
below, then compare:

1. A power flow of the dispatch that would be cheapest **if the lines had no limits**.
   Watch which line ends up above its rating.
2. A power flow of a dispatch **chosen by hand** that stays within every limit. It is
   *feasible*, but look at its cost rate.
3. The **optimal power flow**, which finds the cheapest dispatch that stays within
   every limit.

Two lessons follow from the comparison:

- **Feasible does not mean cheapest.** Many dispatches respect every limit. Only one
  cost rate is the lowest (sometimes several dispatches share it; see the third lesson
  in this series).
- **Reported is not enforced.** A power flow that exceeds a rating is still a valid
  calculation; it tells you the dispatch would overload a line. The optimal power flow
  never picks such a dispatch.

Every result here is **modeled**, not observed. The model is a teaching tool. It is not
the model any real system operator runs.

## Technical detail

Both runs use the same network: buses A, B, C in a triangle with reactances
x_AB = x_BC = 0.10 pu and x_AC = 0.20 pu on a 100 MVA base. G1 is at bus A (the
**reference bus**), G2 at bus B, and the demand at bus C. Line ratings, capacities, and
offers come from the lesson's case table, never from this text.

- **Power flow** (`mambo_power.pf.solve_dc`): solves B′θ = P for the given injections.
  G2's output is fixed; G1, at the reference bus, covers the rest, because the DC model
  is lossless. The adapter then checks balance, the reference angle, flow = Δθ / x, and
  bus balance. Ratings and capacities are *limit* checks: a violation marks the run
  "solved, limits exceeded" and is never hidden.
- **Optimal power flow** (`mambo_power.opf.solve_dc_opf`): a linear program that
  minimises Σ offer × output (a cost rate in synthetic $/h) subject to one balance
  equation, generator bounds, and line limits written with power transfer distribution
  factors. The adapter verifies the result independently: flows are recomputed with the
  power flow above, the cost is recomputed, and the optimality (KKT) conditions are
  checked.
- The "cheapest if lines had no limits" dispatch is taken from a verified optimal power
  flow of the same case with line AC's rating raised out of the way. It is not typed in.
- The cost rate of a power-flow dispatch uses the same formula as the optimizer's
  objective: Σ offer × MW.

See `docs/calculations.md` (DC power flow; DC OPF) and ADR 0006 and 0007 for the
formulation and its verification.
