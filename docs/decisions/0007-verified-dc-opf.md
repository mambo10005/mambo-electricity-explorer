# 0007 — Verified DC OPF (linear costs) and the economic-dispatch lab

- **Status:** Accepted
- **Date:** 2026-10-11
- **Package:** mambo-power 0.2.0, commit `26be8c18b7efb865419054bec7b0b171478bc37a`
  (unchanged), highspy 1.15.1 (HiGHS)

## Formulation audit (traced in `opf/dc_opf.py` and `opf/__init__.py` at the pin)

| Item | Implementation |
|---|---|
| Decision variables | One per in-service generator: dispatch **p_g in MW** (`gen_p_min/max_pu × base_mva`). No angle variables. |
| Objective | HiGHS minimises `Σ c1_g·p_g` (+ `c2_g·p_g²` via a Hessian `2·c2` when nonzero). `objective_cost` = that value + Σ c0. Costs come from `Generator.cost.coefficients`, highest order first, right-aligned into `[c2, c1, c0]`. |
| Balance | One equality row: `Σ p_g − Σ p_d(elastic) = Σ fixed load MW + Σ shunt MW`. Phase-shift injections cancel system-wide. |
| Branch limits | One row per branch: `−rating − const ≤ Σ PTDF[k, gen_bus]·p_g ≤ rating − const`, where `const = pf_shift − PTDF·(fixed load + shunt + p_shift)`. `rating` is `rating_mva × 1` MW (DC). Unrated means an infinite bound. |
| Reference bus | Only through PTDF (slack column zero). Flows are reported via `flow_from_ptdf` at the dispatch. |
| Per unit | Bounds, loads, shunts, and ratings are converted pu × `base_mva` to MW before the LP. The LP is in MW. |
| Solver | `highspy.Highs`, default options, `output_flag` off. Status string from `modelStatusToString`. Non-"Optimal" gives an empty result with a message (no exception). |
| Duals | `row_dual[0]` is the balance dual; `row_dual[1..]` are the flow-row duals; `col_dual[:n_gen]` are the bound duals. Read raw from HiGHS. |
| Price transform | `lmp_bus = balance_dual + Σ_k flow_dual_k·PTDF[k, bus]` (`lmp_decomposition`). |
| Cost terms | Polynomial up to quadratic (c2 ≥ 0), convex piecewise-linear, and concave elastic-demand bids. Start-up and shut-down costs are not modelled. |

## Verified (linear costs, single period, this lab's network)

- **Units:**
  - p in MW and c1 in $/MWh, so the objective is a **cost rate in $/h**.
  - The lab uses an explicit **1-hour** teaching interval. Interval cost ($) = rate × 1 h.
  - The package takes no duration argument; none is claimed.
- **Signs and scale**, established by the hand-derived benchmarks and by perturbing demand
  and ratings in both directions at 0.01, 0.1, and 1.0 MW (`tests/test_opf_benchmarks.py`):
  - `lmp` = ∂(cost rate)/∂(demand at the bus), in $/MWh
  - `flow_limit_dual` = ∂(cost rate)/∂(upper rating), in $/h per MW (≤ 0 when binding)
  - `bound_dual` = the reduced cost of the generator bound (≤ 0 at p_max, ≥ 0 at p_min)
- **Per run**, the adapter re-verifies:
  - primal feasibility and the objective
  - flows, recomputed by the separately verified DC power flow
  - KKT stationarity, dual signs, and complementary slackness
  - price decomposition at every bus, with PTDF measured by the DC power flow
  - two-sided ±0.1 MW demand sensitivities at every bus

  Prices are shown only when the sensitivities agree with each other and with the reported
  value. Otherwise they are withheld, with the average rates over each ±0.1 MW change and
  each direction's feasibility shown. (Stage 9 corrected this wording: the quotients are
  averages over the change, not one-sided local rates; see `docs/calculations.md`. The
  decision rule itself is unchanged.)

## Not verified (not exposed)

Quadratic costs, piecewise-linear costs, elastic-demand bids, phase shifters, the AC
feasibility check, multiperiod, zonal, and market modules.

## Decision

- Expose linear-cost single-period DC OPF in a separate economic-dispatch lab.
- Keep the DC power-flow lab unchanged as the default.
- Call prices "modeled nodal prices", never ISO prices, and show them only per-run verified.
- Never shed load: infeasible is reported as infeasible.

## Consequences

- Each run makes 6 extra OPF solves (±0.1 MW at three buses) and 4–6 DC power flows (1 flow
  check, 3 PTDF measurements, and up to 2 for the non-uniqueness test). That is negligible
  for three buses, but would need a design change for large networks.
- Breakpoints, unservable perturbations, and price mismatches withhold prices by design.
- No package defect was found. No issue was filed against mambo-power.
