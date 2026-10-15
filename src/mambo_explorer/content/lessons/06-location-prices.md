---
lesson_id: location-prices
title: Why modeled prices differ by location
order: 6
sequence_stage: fundamentals
prerequisites: [pf-vs-dispatch]
objectives:
  - Explain how a binding line limit changes the least-cost dispatch.
  - Interpret a modeled nodal price as the verified marginal cost of serving one more MW at a bus, under this formulation.
  - Explain why a nodal price can differ from every generator's offer.
  - Tell apart a cost rate, a one-hour interval cost, a price, and a line-limit sensitivity.
content_version: 1.0.1
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
model_bindings: [uncongested, uncongested-plus10, congested, congested-plus10, relaxed]
model_panels: [location_prices]
exercises:
  - exercise_id: binding-constraint
    kind: model
    generator: binding_constraint
    calculation_id: dc_opf
  - exercise_id: next-increment
    kind: model
    generator: next_increment
    calculation_id: dc_opf
  - exercise_id: positive-sensitivity
    kind: model
    generator: positive_sensitivity
    calculation_id: dc_opf
  - exercise_id: relaxation-cost
    kind: model
    generator: relaxation_cost
    calculation_id: dc_opf
  - exercise_id: cost-units
    kind: model
    generator: cost_units
    calculation_id: dc_opf
glossary_terms: [MW, MWh, Synthetic, Modeled, Offer, Binding constraint, Congestion, Modeled nodal price, Marginal cost, Cost rate, Line-limit sensitivity]
limitations:
  - The offers are synthetic assumptions, not bids from any real generator. The network is synthetic.
  - Modeled nodal prices here come from a lossless DC model with linear offers. Real ISO prices also reflect losses, many more constraints, ancillary services, market rules, and scarcity pricing. This lesson does not explain the components of any actual ISO price.
  - Each price is shown only if this run's check verified it, and the check concerns only the tested ±0.1 MW demand perturbations at each bus.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

Run the lesson's model cases, then walk through three steps.

**A. No congestion.** Every line has room to spare. The cheapest dispatch uses the
generator with the lower **offer** first. One more MW of demand anywhere is served by
that same generator, so the **modeled price** is the same at every bus.

**B. A congested line.** Now line AC has a lower rating. The cheapest dispatch from
step A would push too much power through it, so the optimizer has to use more of the
dearer generator. The line is **binding**: its flow sits exactly at its rating. Look at
the prices now. They differ by bus, and the price at the demand bus can be **higher
than either offer**. The extra-demand table shows why: to serve one more MW at C
without overloading AC, the model raises one generator and *lowers* the other.

**C. Relax the binding limit.** Raise line AC's rating a little. The cost rate falls,
and by the amount the run's **line-limit sensitivity** predicted, because the same line
still binds. The prices can stay the same while the total cost changes: a price
describes the *next* MW, not the total.

Four different numbers appear, and they have different units:

- **Cost rate** (synthetic $/h): offer × MW, summed over the generators.
- **Interval cost** (synthetic $): the cost rate × the one-hour interval. The number
  matches the cost rate only because the interval is exactly one hour.
- **Modeled nodal price** (synthetic $/MWh): how much the cost rate rises per extra MW
  of demand at that bus, verified by re-solving.
- **Line-limit sensitivity** (synthetic $/h per MW): how much the cost rate changes per
  extra MW of a line's rating.

A generator's offer and a bus's price are not the same thing. The offer is an input you
chose. The price is an output of the whole network.

## Technical detail

The prices are the package's reported locational marginal prices,
lmp = λ + Σ μ_k · PTDF[k, bus], where λ is the balance dual and μ_k the line-limit
duals. Stage 7 audited this formulation and verified the sign conventions:

- price = ∂(cost rate)/∂(demand at the bus), in $/MWh;
- line-limit sensitivity = ∂(cost rate)/∂(upper rating), ≤ 0 when the limit binds.

Each run checks the KKT conditions and the price decomposition at every bus (with PTDFs
measured by the verified DC power flow). It re-solves with ±0.1 MW of demand at each bus
and shows prices only if the two average rates, [C(D + h) − C(D)] / h and
[C(D) − C(D − h)] / h with h = 0.1 MW, agree with each other and with the reported price
within 10⁻⁴ $/MWh. The **energy part** of a price is λ; the **congestion
part** is the rest.

In step B, the extra-demand comparison and the price agree: the change in dispatch per
MW of extra demand, weighted by the offers, equals the verified price at C. The
exercises check this from the runs instead of quoting numbers. Step C stays in one
regime (the same binding set), which is why the linear prediction holds. A larger
relaxation could unbind the line and the prediction would stop holding.

Under this lossless DC formulation there is no loss component. Real ISO prices include
one, and many other effects; see the limitations below.
