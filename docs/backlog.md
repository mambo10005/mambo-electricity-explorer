# Backlog

Recorded work that is **not scheduled**, so no results are claimed. Items are not
prerequisites for other milestones unless stated.

| ID | Task | Why | Earliest | Blocks |
|---|---|---|---|---|
| BL-1 | Live DST validation for ERCOT NP6-345-CD: collect OperDay 2026-11-01 (posted about 2026-11-02, public until about 2026-12-02) and record how the repeated fall-back hour and its DSTFlag values appear. Then spring-forward (OperDay 2027-03-14). | The repeated and missing hour representation is unverified (dataset contract). The store keeps DSTFlag as published and never interprets it. | 2026-11-02 | Nothing; reconciliation research later |
| BL-2 | ~~Independently verify DC OPF objective units and dual sign/scaling~~ **Done 2026-10-11 for linear costs, single period (ADR 0007).** Quadratic, piecewise-linear, and elastic-demand forms remain unverified. | — | — | — |
| BL-3 | Human review of the seven beginner lessons (checklist: `docs/review/human-review-checklist.md`) (4 observation lessons, 3 market-mechanics lessons), the glossary, and the model-backed exercise wording | All are agent-drafted (`review_status: unreviewed`) | — | Lesson publication |
| BL-4 | Owner decisions: application license (ADR 0001), publication review per source | Pending | — | PUB-01 |
| BL-5 | ~~Price gate labels~~ **Done 2026-10-11 (Stage 9).** Finite changes are now described as average rates over the stated change, with formulas, units, per-direction feasibility, and gate status (`modeling/sensitivity.py`); a breakpoint inside the change is explained as a blend; the capacity-edge note names only the infeasible direction. Regression tests: `tests/test_sensitivity_terms.py`. Gate decisions unchanged. | — | — | — |
| BL-6 | Accessibility follow-ups. **Closed in Stage 10 (measured, `docs/accessibility.md`, ADR 0008):** focus ring (now ≥ 3.28:1 on every measured background, focus-only CSS); light-theme secondary hover/active; link text colors. **Still open:** no screen-reader session; three lab tables scroll inside their containers at 320 CSS px | Remaining items need a screen reader and a design choice for wide tables | — | Any accessibility claim |
| BL-7 | Owner decision: keep or back up and reset `data/learn/progress.json`, which contains a lesson-6 "viewed" mark written by a Stage 8 test (`docs/testing-isolation.md`). Optional tool: `mambo learn-reset` (dry run by default). Not run by any stage. | The file may also hold legitimate activity; only the owner can decide | — | Nothing |
