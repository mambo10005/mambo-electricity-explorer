# Human-review checklist: lessons 1–7 and the glossary

**Status: not reviewed by a person.** All seven lessons, the glossary, and the exercise
wording were drafted by an AI agent (Claude). This checklist was also prepared by the
agent; it lists what a reviewer should check and the potential issues the agent noticed.
It is **not** a review. BL-3 stays open until a named person completes it.

Rules (from `docs/lesson-authoring.md`):
- Only a named person who is not the author, and not an AI agent, can review.
- A review covers one `content_version`. Any later content change needs a new review.
- After a review, the reviewer (or the owner) sets `review_status: human-reviewed`,
  `reviewed_by`, and `reviewed_at` in that lesson's front matter. The validator rejects
  AI reviewers and missing fields.
- AI corrections made after this checklist was written are still unreviewed.

How to see each lesson: `.venvs/py314/Scripts/streamlit run src/mambo_explorer/app.py`,
open **Learn**. Lessons 2–4 need local EIA observations (`mambo collect`); lessons 5–7
need **Run this lesson's model cases**. Turn on **Show technical detail**.

---

## Review record (one block per lesson or for the glossary)

Copy this block for each item you review. Leave fields blank until they are true.

| Field | Value |
|---|---|
| Item (lesson id or "glossary") | |
| Content version reviewed | |
| Reviewer (name) | |
| Review date | |
| Findings (numbered) | |
| Disposition per finding (accept / change requested / reject) | |
| Approval scope (e.g. "beginner text only", "whole lesson including exercises") | |
| Approved? (yes / no / with changes) | |

---

## Checks that apply to every lesson

- [ ] **Learning objectives** are achievable from the beginner section alone.
- [ ] **Sources and factual claims:** every source-derived statement matches the cited page;
      lessons 5–7 cite no external source, so they must make no claim about real operators,
      ISOs, or markets beyond the stated limitations.
- [ ] **Units and formulas** are correct and consistently labeled (MW vs. MWh; $/h vs. $ vs.
      $/MWh vs. $/h per MW).
- [ ] **Model assumptions** (lessons 5–7) are stated: synthetic network and offers, lossless
      DC, linear offers, one hour, no unit commitment, no load shedding.
- [ ] **Causality limitations:** no causal claims (weather, customer mix, market behavior)
      that the bound data or model do not support.
- [ ] **Forecast-vintage limitations** (lesson 3): the forecast shown is the latest collected
      value, not necessarily the forecast as first issued.
- [ ] **Price and sensitivity caveats** (lessons 6–7): modeled prices are not ISO prices; the
      ±0.1 MW averages are averages over the change, not local derivatives; a blended
      average is never called a one-sided marginal rate; each direction's feasibility is
      stated separately.
- [ ] **Exercise correctness:** the correct option is right for the current data or runs;
      every decoy is wrong for a reason a beginner can learn from; explanations show the
      arithmetic.
- [ ] **Accessibility observations:** readable at phone width; tables have headers; nothing
      relies on color alone; keyboard-only answering works (see `docs/accessibility.md`).

---

## Lesson 1 — Power versus energy (MW and MWh) · `power-vs-energy` · v1.0.0

- Objectives: MW vs. MWh; energy = average power × duration; why hourly MWh equals average MW
  only for a one-hour duration.
- Sources: `eia930-instructions`, `eia-gridmonitor-about`.
- Formulas: `power_energy` v1 (`docs/calculations.md`).
- Exercises: `synthetic-energy` (concept), `one-hour-equivalence` (concept). Numbers are
  labeled SYNTHETIC.
- Agent-noticed items for the reviewer:
  1. The technical section quotes the EIA-930 instructions ("hourly integrated values in
     megawatts by hour ending time"). Confirm the quote against the current PDF.

## Lesson 2 — Reading an actual demand series · `reading-demand` · v1.0.0

- Sources: `eia930-instructions`, `eia-gridmonitor-about`, `eia930-reference-tables`.
- Formulas: `series_summary` v1, `coverage` v1.
- Exercises: `demand-max` (data).
- Agent-noticed items:
  1. Confirm that "demand is **not** a set of readings from customers' meters" matches how
     EIA describes balancing-authority demand.
  2. Check that period labels are never described as local times or interval starts/ends.

## Lesson 3 — Comparing demand with a published forecast · `demand-vs-forecast` · v1.0.0

- Sources: `eia930-instructions`, `eia-gridmonitor-about`.
- Formulas: `forecast_error` v1 (error = actual − forecast; MAE; RMSE; mean error).
- Exercises: `error-sign` (data), `mae` (data).
- Agent-noticed items:
  1. Forecast vintage: confirm the lesson never implies the forecast shown is the one first
     issued, and that it says "not a trading test".
  2. Sign convention: positive error means demand above the forecast. Confirm the beginner
     text and the exercise use the same convention.

## Lesson 4 — Understanding missing observations · `missing-observations` · v1.0.0

- Sources: `eia-gridmonitor-about`, `eia-api-docs`.
- Formulas: `coverage` v1.
- Exercises: `absent-not-zero` (concept), `forecast-absent-count` (data).
- Agent-noticed items:
  1. Confirm that absent rows are never explained with a cause (the lesson says it does not
     guess why).

## Lesson 5 — Power flow versus economic dispatch · `pf-vs-dispatch` · v1.0.0

- Model runs: uncongested, congested, two power flows at a specified dispatch
  (`modeling/cases.py`). No external sources.
- Exercises: `pf-reports-violation`, `feasible-not-cheapest` (model).
- Agent-noticed items:
  1. "It is not the model any real system operator runs": confirm the wording is fair and
     not itself a claim about operators that needs a source.
  2. The "cheapest if lines had no limits" dispatch is taken from a verified run. Confirm a
     beginner can follow why it is used.

## Lesson 6 — Why modeled prices differ by location · `location-prices` · v1.0.1

- Model runs: uncongested (+10 MW), congested (+10 MW), AC rating 70 MW.
- Exercises: `binding-constraint`, `next-increment`, `positive-sensitivity`,
  `relaxation-cost`, `cost-units` (model).
- Agent-noticed items:
  1. The limitations say real ISO prices "also reflect losses, many more constraints,
     ancillary services, market rules, and scarcity pricing". The lesson cites no source for
     this. Decide whether it needs a citation or softer wording.
  2. `cost-units` uses two options with the same number (cost rate vs. interval cost).
     Confirm that this tests units fairly rather than tricking the learner.
  3. v1.0.1 changed only the technical wording of the price check (average rates over
     ±0.1 MW).

## Lesson 7 — When one marginal number is not verified · `unverified-marginal` · v1.1.0

- Model runs: breakpoint, 0.05 MW below a breakpoint, line AC at its rating, edge of
  capacity, no demand, equal offers, not enough capacity.
- Exercises: `withheld-reason`, `blended-rate`, `infeasible-direction`,
  `nonunique-vs-infeasible`, `uniqueness-vs-price` (model).
- Agent-noticed items:
  1. The technical section says the solver's dual at a breakpoint is "a subgradient that lies
     between the two averages in these cases". A test checks the "between" part for the two
     breakpoint cases; the word *subgradient* is the agent's interpretation.
  2. The "no demand" case uses a −0.1 MW change at buses with no demand (a negative load).
     Confirm that the lesson's "mathematical perturbation for the check only" framing is
     clear enough for a beginner.
  3. v1.1.0 (Stage 9) rewrote the explanation of the price check (BL-5). The previous
     wording called the ±0.1 MW quotients "one-sided rates" and said "more or less demand
     cannot be met" when only one direction failed.

---

## Glossary (`src/mambo_explorer/content/glossary.yaml`)

35 terms. Check each definition for accuracy, beginner readability, and consistency with
the lessons that use it.

- [ ] Observation terms: Absent row, BA, Day-ahead demand forecast, Demand, EIA, EIA-930,
      ERCOT, Energy, Forecast error, MAE, Mean error, MW, MWh, Null value, Period label,
      Power, Revision, RMSE, UTC.
- [ ] Model terms: Average change rate, Binding constraint, Breakpoint, Congestion, Cost rate,
      Dispatch, Line rating, Line-limit sensitivity, Marginal cost, Modeled, Modeled nodal
      price, Offer, Optimal power flow, Power flow, Reference bus, Synthetic.
- Agent-noticed items:
  1. "Congestion" is a simplified definition (cheaper power cannot reach where it is needed).
     Decide whether that is acceptable for beginners.
  2. "Offer" is defined as a synthetic cost per MWh, explicitly not a market bid. Confirm a
     reader cannot confuse it with real offers.
