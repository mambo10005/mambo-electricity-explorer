# Backlog

Recorded work that is **not scheduled**, so no results are claimed. Items are not
prerequisites for other milestones unless stated.

| ID | Task | Why | Earliest | Blocks |
|---|---|---|---|---|
| BL-1 | Live DST validation for ERCOT NP6-345-CD: collect OperDay 2026-11-01 (posted about 2026-11-02, public until about 2026-12-02) and record how the repeated fall-back hour and its DSTFlag values appear. Then spring-forward (OperDay 2027-03-14). | The repeated and missing hour representation is unverified (dataset contract). The store keeps DSTFlag as published and never interprets it. | 2026-11-02 | Nothing; reconciliation research later |
| BL-2 | ~~Independently verify DC OPF objective units and dual sign/scaling~~ **Done 2026-10-11 for linear costs, single period (ADR 0007).** Quadratic, piecewise-linear, and elastic-demand forms remain unverified. | — | — | — |
| BL-3 | Human review of the seven beginner lessons (4 observation lessons, 3 market-mechanics lessons), the glossary, and the model-backed exercise wording | All are agent-drafted (`review_status: unreviewed`) | — | Lesson publication |
| BL-4 | Owner decisions: application license (ADR 0001), publication review per source | Pending | — | PUB-01 |
| BL-5 | Review the per-run price gate's *labels* (not its decisions). Observed 2026-10-11, not changed in Stage 8: (a) with a breakpoint closer than the 0.1 MW step (e.g. demand 149.95 MW, cheap capacity 150 MW), the up-side quotient blends two regimes (25 $/MWh) and the note says "Breakpoint" and shows that blend as a one-sided rate; (b) in the edge-of-capacity case the note says "slightly more or less demand cannot be met" when only *more* is infeasible (the rates table is correct). Prices are withheld correctly in both. | Wording could mislead a careful learner; Lesson 7 explains the blend and computes the infeasible side itself | — | Nothing |
