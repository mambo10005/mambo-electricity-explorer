# Human-review checklist: lessons 1–15, the glossary, and the responsibility records

**Status: not reviewed by a person.** All fifteen lessons, the glossary, the exercise
wording, and the regulatory responsibility records were drafted by an AI agent (Claude). This checklist was also prepared by the
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

## Corrections log (agent-made; **not reviewed by a person**)

| Date | Item | Version | Change | Reason |
|---|---|---|---|---|
| 2026-10-11 | `unverified-marginal` | 1.0.0 → 1.1.0 | Price-check explanation rewritten (average rates over ±0.1 MW, per-direction feasibility, blends); two runs and `blended-rate` exercise added | BL-5 (Stage 9) |
| 2026-10-11 | `location-prices` | 1.0.0 → 1.0.1 | Technical wording of the price check | BL-5 (Stage 9) |
| 2026-10-11 | `location-prices` | 1.0.1 → 1.1.0 | Removed the uncited list of what "real ISO prices also reflect"; added one sourced statement (PJM Manual 11: LMP = system energy + congestion + loss price) and separated model statements from the market statement | Stage 10 review readiness |
| 2026-10-11 | `pf-vs-dispatch` | 1.0.0 → 1.0.1 | Removed uncited claims about what real operators run ("much larger and more detailed models"); now only says the lesson does not describe any operator | Stage 10 review readiness |
| 2026-10-11 | `unverified-marginal` | 1.1.0 → 1.1.1 | "Subgradient" now labeled as the lesson's interpretation; only "between the two averages" is checked numerically | Stage 10 review readiness |
| 2026-10-11 | Lessons 5–7 (shared model section) | — (UI text) | "not the model any real system operator runs" → "does not describe how any real system operator dispatches or prices electricity" | Stage 10 review readiness |

No exercise question or answer changed in Stage 10, so no exercise was invalidated. (Stage 9's
changes did invalidate older lesson 7 answers through the version-bumped snapshot.)

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
- [ ] **Compliance wording** (lessons 11–12 and the Compliance page): every entry reads as a
      source to investigate, never as "this applies to you"; no applicability is concluded
      from a title, label, or location; proposals are never shown as effective; synthetic
      requirements are never attributed to a real authority.
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
     megawatts by hour ending time"). Confirm the quote against the current PDF. *Agent check
     (2026-10-11): the sentence appears verbatim under "General Instructions" (page 3) of the
     PDF at the cited URL. Still for the reviewer to confirm.*

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

## Lesson 5 — Power flow versus economic dispatch · `pf-vs-dispatch` · v1.0.1

- Model runs: uncongested, congested, two power flows at a specified dispatch
  (`modeling/cases.py`). No external sources.
- Exercises: `pf-reports-violation`, `feasible-not-cheapest` (model).
- Agent-noticed items:
  1. *Corrected in v1.0.1:* the uncited claims about operators' models were removed; the
     lesson now only says it does not describe how any operator dispatches. Confirm that this
     is enough context for a beginner.
  2. The "cheapest if lines had no limits" dispatch is taken from a verified run. Confirm a
     beginner can follow why it is used.

## Lesson 6 — Why modeled prices differ by location · `location-prices` · v1.1.0

- Model runs: uncongested (+10 MW), congested (+10 MW), AC rating 70 MW.
- Sources: `pjm-manual-11` (PJM Manual 11, Revision 137, Section 1 overview), for the single
  actual-market statement.
- Exercises: `binding-constraint`, `next-increment`, `positive-sensitivity`,
  `relaxation-cost`, `cost-units` (model).
- Agent-noticed items:
  1. *Corrected in v1.1.0:* the uncited list was removed. The lesson now makes one market
     statement, cited to PJM Manual 11 (each PJM LMP is the sum of a system energy price, a
     congestion price, and a loss price; agent-checked against Revision 137, Section 1
     overview). Confirm the paraphrase and that the "other ISOs define their prices in their
     own rules" sentence is fair without a citation.
  2. `cost-units` uses two options with the same number (cost rate vs. interval cost).
     Confirm that this tests units fairly rather than tricking the learner.
  3. v1.0.1 changed only the technical wording of the price check (average rates over
     ±0.1 MW). v1.1.0 separated model statements ("What is verified here") from the sourced
     market statement and the limitations.

## Lesson 7 — When one marginal number is not verified · `unverified-marginal` · v1.1.1

- Model runs: breakpoint, 0.05 MW below a breakpoint, line AC at its rating, edge of
  capacity, no demand, equal offers, not enough capacity.
- Exercises: `withheld-reason`, `blended-rate`, `infeasible-direction`,
  `nonunique-vs-infeasible`, `uniqueness-vs-price` (model).
- Agent-noticed items:
  1. *Clarified in v1.1.1:* "subgradient" is now labeled as the lesson's interpretation; a
     test checks only that the dual lies between the two averages in the two breakpoint
     cases.
  2. The "no demand" case uses a −0.1 MW change at buses with no demand (a negative load).
     Confirm that the lesson's "mathematical perturbation for the check only" framing is
     clear enough for a beginner.
  3. v1.1.0 (Stage 9) rewrote the explanation of the price check (BL-5). The previous
     wording called the ±0.1 MW quotients "one-sided rates" and said "more or less demand
     cannot be met" when only one direction failed.

## Lesson 8 — From scheduled energy to settlement · `energy-settlement` · v1.0.0

- Calculator: `energy_settlement` v1.0.0 (`settlement.py`); synthetic inputs, optional
  import of one verified modeled price.
- Sources: `iso-ne-da-rt-markets`, `iso-ne-da-energy-bill`, `iso-ne-rt-energy-bill` (ISO New
  England; agent-checked 2026-10-11).
- Exercises: `total-amount`, `deviation-component`, `role-reading`, `volume-exposure`,
  `price-exposure` (settlement; answers from the calculator's current inputs).
- Agent-noticed items:
  1. Confirm the paraphrases of the three ISO New England pages: day-ahead commitments are
     settled; real-time settles differences from them at the real-time LMP; day-ahead energy
     is settled hourly on net cleared quantity at the day-ahead LMP; real-time energy is
     settled on net deviation at the real-time LMP in five-minute intervals; invoices carry
     other allocations.
  2. The sign convention (a buyer pays the signed amount; a seller receives it) is the app's
     own. ISO New England's invoice nets credits and charges with its own convention. Confirm
     that the lesson says this clearly enough.
  3. "Sold back at the real-time price" for a negative deviation is a teaching phrase. Decide
     whether it could mislead.
  4. Forecast-vintage limitation: the lesson says EIA demand forecasts are not day-ahead
     cleared quantities. Confirm.

## Lesson 9 — Why a hedge at another location leaves basis exposure · `basis-exposure` · v1.0.0

- Calculator: `basis_exposure` v1.0.0 (`basis.py`); synthetic inputs, optional import of two
  verified prices from one run (two different buses); K always synthetic.
- Sources: `ferc-glossary` (FERC market-assessment glossary: Basis, Swaps, Hedging;
  agent-checked 2026-10-11 in a browser).
- Exercises: `net-cost`, `hedge-cash-flow`, `basis-component`, `mismatch-component`,
  `hedge-effect` (basis; answers from the calculator's current inputs).
- Agent-noticed items:
  1. The FERC glossary's examples are natural gas. Confirm that applying the *concepts* to
     an electricity teaching scenario, with the lesson saying so, is acceptable.
  2. The CFTC glossary (a more direct source for "basis") could not be checked: the site
     showed a human-verification page. Decide whether to add it after a person checks it.
  3. The basis sign (delivery minus reference) and the pay-fixed/receive-floating direction
     are the app's teaching conventions. Confirm the lesson labels them clearly.
  4. "A financial position with no energy" (Q = 0, H > 0): confirm the wording does not
     imply advice or a legal classification.

## Lesson 10 — Why matching total energy does not remove shape exposure · `shape-exposure` · v1.0.0

- Calculator: `time_shape` v1.0.0 (`shape.py`); synthetic interval scenarios, editable
  intervals, no model prices.
- Sources: `eia-texas-heat-wave-2011` (EIA Today in Energy, 2011-09-09; agent-checked
  2026-10-11).
- Exercises: `interval-status`, `shape-component`, `mw-vs-mwh`, `profile-compare`,
  `negative-receipt` (shape; answers from the calculator's current inputs).
- Agent-noticed items:
  1. Confirm the paraphrase of the EIA article: a 16-hour weekday on-peak block in ERCOT in
     August 2011, afternoon super-peak hours far above morning hours, and block prices
     averaging high and low hours. It is context only; none of its numbers are used.
  2. The "time-shape component" is the app's accounting split with a duration-weighted p̄.
     Confirm that the lesson says it is not a standard industry metric.
  3. The FERC glossary (used in lesson 9) showed a human-verification page on 2026-10-11 and
     was not re-checked for this lesson.

## Lesson 11 — Who sets the rules? · `who-sets-the-rules` · v1.0.0

- Claims (record ids in `content/responsibilities.yaml`): ferc-wholesale-sales,
  ferc-not-other-sales, cpuc-utility-service, ercot-wholesale-settlement,
  iso-ne-market-rule-1, ferc-reliability-oversight, standards-name-their-subset,
  ero-develops-standards, regional-entity-enforcement, cftc-swaps-futures,
  cea-ferc-state-savings.
- Sources: `fpa-201`, `fpa-215`, `cfr-18-40-1`, `ercot-about`, `iso-ne-tariff`,
  `cpuc-about`, `fr-2025-18396`, `cea-2` (all agent-checked 2026-10-11).
- Exercises: `wholesale-definition`, `operator-vs-overseer`, `who-complies-reliability`,
  `layers-new-england` (overlap: the answer names more than one source), `roles-differ`
  (compliance; static answers keyed on the record-set fingerprint).
- Agent-noticed items:
  1. ferc.gov, nerc.com, texasre.org, cftc.gov, and puc.texas.gov could not be read. NERC
     is described only from the statute and one Federal Register abstract. Decide whether
     the lesson should wait for those sources.
  2. The lesson deliberately leaves ERCOT's relationship to federal wholesale and
     reliability provisions unresolved. `operator-vs-overseer` avoids FERC as a decoy for
     that reason. Confirm this framing.
  3. Confirm the paraphrases of FPA §201(b)(1) ("does not apply to any other sale … except
     as specifically provided") and CEA §2(a)(1)(I) (savings clause plus CFTC's retained
     authority). Both are detailed provisions summarized for beginners.
  4. `roles-differ` decoys are "not supported by the cited sources", not claimed false.
     Check that a beginner reads them that way.

## Lesson 12 — From a requirement to evidence · `requirement-to-evidence` · v1.0.0

- Claims: doe-417-collection, cip-003-11-proposal, cip-003-11-final,
  standards-name-their-subset.
- Sources: `fr-2023-18729`, `fr-2025-18396`, `fr-2026-05711`, `cfr-18-40-1`.
- Exercises: `chain-order`, `label-not-applicability` (unresolved: never "yes"),
  `evidence-period`, `proposal-not-effective`, `test-not-approval`, `after-review`.
- Agent-noticed items:
  1. The chain (source → applicability questions → requirement → control → evidence →
     review → remediation) is the app's teaching framework, not taken from an authority.
     Its exercises say so.
  2. Riverside Example Power and policy SYN-1 are synthetic. Confirm that nothing reads as
     a DOE, FERC, or NERC requirement.
  3. The DOE-417 notice (2023) is a proposal to extend and change the form. The lesson
     says who must file and whether filing is mandatory were not determined. Confirm.
  4. Order No. 918's effective date (2026-05-26) is the final rule's. The standard's own
     enforceable date follows its implementation plan, which was not read.

## Lesson 13 — Reading the actual generation mix · `generation-mix` · v1.0.0

- Data: EIA-930 `electricity/rto/fuel-type-data`, entity ERCO, net generation by energy
  source (own store; `mambo collect --source eia-generation`). Calculation
  `generation_mix` v1.0.0.
- Sources: `eia930-instructions` (OMB 1905-0129; Data Code list, storage sign rules,
  energy balance), `eia930-about` (net generation definition; imputation; pumped-storage
  guidance), `eia-api-fuel-type-data` (route metadata read with a key; agent-checked
  2026-10-12).
- Exercises: `largest-category`, `negative-meaning`, `absent-category-hours`,
  `partial-sum-not-total`, `mix-not-price` (generation; answers from the window's
  observations; a revision or new category regenerates them).
- Agent-noticed items:
  1. The instructions and the About page differ on pumped-storage charging (negative
     generation vs demand). The lesson discloses this and says ERCOT's convention is not
     stated. Confirm that framing, and whether EIA states ERCOT's practice anywhere.
  2. "Net of station use" is inferred from the instructions' remark that station use above
     gross output yields negative net generation. Confirm.
  3. `UES` appears in the API facet but not in the instructions read; it is labeled
     "not in the form instructions". Check a current reference table.
  4. The exercise "largest category" sums signed valid values; confirm a beginner reads
     "largest" as energy over the window, not capacity or share.

## Lesson 14 — Reading an actual day-ahead electricity price · `day-ahead-price` · v1.0.0

- Data: ERCOT NP4-190-CD DAM Settlement Point Prices, `HB_NORTH` only (own store;
  `mambo collect --source ercot-dam-spp`). Calculation `dam_price_reading` v1.
- Sources: `ercot-np4-190-cd`, `ercot-dam`, `ercot-nodal-protocols` (Sections 2, 3.5.2.1,
  4.5.3), `ercot-np4-160-sg` (agent-checked 2026-10-12).
- Exercises: `highest-hour`, `negative-count`, `missing-not-zero`, `not-a-bill`,
  `finality-unknown` (price; answers from the chosen DeliveryDate's stored prices).
- Agent-noticed items:
  1. The unit ($/MWh) comes from the Protocols' correction thresholds, not the file.
     Confirm a reviewer accepts that basis.
  2. `HB_NORTH` ↔ North 345 kV Hub rests on matching 75/75 hub buses between NP4-160-SG and
     Protocols §3.5.2.1. Confirm.
  3. The lesson says the DAM "matches buyers and sellers for each hour"; check this
     simplification against the DAM page wording ("voluntary, financially-binding forward
     energy market").
  4. Finality is shown as "not determined"; confirm the explanation of §4.5.3(6) is fair.

## Lesson 15 — Reading an actual real-time settlement-point price · `real-time-price` · v1.0.0

- Data: ERCOT NP6-905-CD real-time Settlement Point Prices, `HB_NORTH` (type HU) only;
  calculation `rt_price_reading` v1.
- Sources: `ercot-np6-905-cd`, `ercot-nodal-protocols` (§3.5.2.1(4), §6.3, §6.6.1),
  `ercot-np4-197-m`, `ercot-prices` (agent-checked 2026-10-12).
- Exercises: `highest-interval`, `negative-count`, `absent-interval`, `spp-vs-lmp`,
  `not-invoice` (rtprice; answers from the stored intervals).
- Agent-noticed items:
  1. The beginner wording "time-weighted average of the hub's bus prices plus an adder" is a
     simplification of §3.5.2.1(4). Confirm it is fair.
  2. The `spp-vs-lmp` decoy calls SCED "five-minute"; the Protocols describe SCED running
     every five minutes in places. Confirm the wording.
  3. The settlement wording ("an invoice also depends on metered quantities, day-ahead
     positions, ancillary services, and other charge types") is general. Check it.
  4. DST intervals are unobserved; the lesson says so.

## Regulatory responsibility records (`content/responsibilities.yaml`, set v1.0.0)

- 17 records, 11 sources, 4 open questions, 7 source gaps. Each record: claim paraphrase,
  section, version, dates (null when unknown), limitations, `human_review_status:
  unreviewed`.
- [ ] Each `supported_responsibility` matches its cited section.
- [ ] Each status label (binding requirement, approved tariff or rule, official guidance,
      proposed change) is right for its source.
- [ ] Jurisdiction scopes are not overstated (California and New England records are
      regional; ERCOT records reflect only ERCOT's own page).
- [ ] The open questions are still open, or are resolved by a newly readable source.

---

## Glossary (`src/mambo_explorer/content/glossary.yaml`)

85 terms. Check each definition for accuracy, beginner readability, and consistency with
the lessons that use it.

- [ ] Observation terms: Absent row, BA, Day-ahead demand forecast, Demand, EIA, EIA-930,
      ERCOT, Energy, Forecast error, MAE, Mean error, MW, MWh, Null value, Period label,
      Power, Revision, RMSE, UTC.
- [ ] Settlement terms (lesson 8): Day-ahead schedule, Deviation, Energy settlement,
      Price exposure, Two-settlement system, Volume exposure.
- [ ] Basis terms (lesson 9): Basis, Fixed-for-floating hedge, Quantity mismatch,
      Reference location.
- [ ] Shape terms (lesson 10): Flat-block hedge, Load shape, Time-shape component.
- [ ] Real-time price terms (lesson 15): Price adder, Price floor, Real-time Settlement Point
      Price, SCED, Settlement Interval.
- [ ] Price terms (lesson 14): Day-Ahead Market, Delivery date, Price finality, Settlement
      Point Price, Trading hub.
- [ ] Generation terms (lesson 13): Category sum, Energy source category, Fuel consumption,
      Installed capacity, Marginal generation, Net generation, Net storage.
- [ ] Compliance terms (lessons 11–12): Applicability, Bulk-power system, Compliance review,
      Control, Effective date, Electric reliability organization, Evidence, FERC, Proposed
      rule, Regional entity, Regulator, Reliability standard, Remediation, Requirement,
      Retail sale, Retrieval date, Rule layers, System operator, Tariff, Wholesale sale.
- [ ] Model terms: Average change rate, Binding constraint, Breakpoint, Congestion, Cost rate,
      Dispatch, Line rating, Line-limit sensitivity, Marginal cost, Modeled, Modeled nodal
      price, Offer, Optimal power flow, Power flow, Reference bus, Synthetic.
- Agent-noticed items:
  1. "Congestion" is a simplified definition (cheaper power cannot reach where it is needed).
     Decide whether that is acceptable for beginners.
  2. "Offer" is defined as a synthetic cost per MWh, explicitly not a market bid. Confirm a
     reader cannot confuse it with real offers.

## Assumption and aggregation records (Stages 23–24)

Agent-authored records that govern optional diagnostics. Approvals are recorded separately
with the CLI; ticking a box here records no approval.
- [ ] M1 1.0.0 rule, scope, and unresolved definitions (`docs/assumption-register.md`).
- [ ] AGG-A 1.0.0 (arithmetic mean) and AGG-B 1.0.0 (duration-weighted mean): formulas,
      output names, allowed and prohibited uses, and limitations.
- [ ] The persistent limitation text: "This is an analytical summary under review-approved
      assumptions. It is not an ERCOT-defined hourly settlement price, settlement, or trading
      backtest."
- [ ] The aggregation-evidence classification (`docs/aggregation-evidence.md`), especially the
      HRSAP finding (a credit formula, not a published price).
