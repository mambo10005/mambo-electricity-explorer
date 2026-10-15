# Progress Log

Newest first. One entry per meaningful step.

## 2026-10-12 — Stage 18: timestamp position audit (#35)

Stacked on Stage 17 (PR #34) ← … ← #2. None merged. Real `data/` and progress unchanged.

- **Discrepancy explained.** Stage 17's "ticks 2026-03-07 00:00/03:00/06:00" were
  `ticks.slice(0, 3)` — the first three ticks of a 48-hour axis starting 2026-03-07T00 —
  reported beside the tooltip and table for 2026-03-08T08. They never described that
  point's position. Evidence error, not a code defect; the Stage 17 progress entry and
  PR #34 description are corrected.
- **Position verified** in UTC, America/Los_Angeles, and Asia/Seoul with a synthetic
  diagnostic (`scripts/diagnostics/time_position_app.py`, explicit UTC ticks on 07–10 UTC
  and a UTC-midnight set, line and stacked bars) and the production lesson 2 and
  generation charts: each hovered mark sits on its own tick (or at its interpolated
  position) within −0.5 px, tooltips and table rows name the same observation, marks are
  chronological. Details in `docs/timestamp-display.md`, "Position evidence".
- **Code:** only an optional `tick_labels` argument on `utc_label_chart` for the
  diagnostic; production tick density unchanged (test-enforced). New offline tests check
  serialized instants against independently built UTC instants, explicit UTC tick values,
  the fixture domain, and chronological order.

## 2026-10-12 — Stage 17: timestamp-display consistency (#33)

Stacked on Stage 16 (PR #32) ← … ← #2. None merged. mambo-power unchanged at 26be8c1. Real
`data/` and progress unchanged (gate check).

- **Inventory** (`docs/timestamp-display.md`): every time value shown is classified as a
  verified UTC source label, an offset-bearing publication timestamp, a retrieval
  timestamp, an ERCOT label as published, a synthetic elapsed interval, or unknown; each
  kind has one display convention.
- **Helper** (`timeview.py`, ADR 0015): `utc_label_chart` draws UTC labels on a Vega-Lite
  utc scale over aware instants with the verbatim label in the tooltip; `format_utc` prints
  retrieval times. Built-in Streamlit charts are no longer given datetimes (test-enforced).
- **Views corrected:** lesson 2 demand chart and lesson 3 error chart (aware values drawn
  in browser-local time under a UTC title), Explore demand/forecast chart (naive DuckDB
  timestamps, local by luck), generation chart (Stage 16's stripped-zone workaround).
  ERCOT's ordinal axis, tables, health labels, and finance intervals were audited and left
  as they were.
- **Unchanged:** observation values, identities, revisions, selections, snapshot ids,
  lesson text and versions, review statuses; interval boundaries still null; ERCOT zone
  and storage sign convention still unresolved.
- **Browser evidence (Playwright, synthetic scratch store, emulated zones UTC,
  America/Los_Angeles, Asia/Seoul):** for label 2026-03-08T08 (00:00 in LA) on lesson 2,
  every zone showed axis ticks "2026-03-07 00:00, 03:00, …", tooltip "Period label (UTC)
  2026-03-08T08 / 41,234.00", and table row "2026-03-08T08 41234 megawatthours 1" (the
  quoted ticks were the axis's first three, not the point's position — corrected in
  Stage 18); the
  same held for the DST-transition label 2026-03-08T10 in LA, UTC midnight 2026-03-08T00
  in Seoul, lesson 3's error chart, and the generation bars for 2026-03-07T15 (00:00 in
  Seoul). Dark theme at 640 CSS px and light at 375 px: no page overflow; the data-table
  expander opens by keyboard. Empty store: no chart, "no observations" notices.

## 2026-10-12 — Stage 16: net generation by energy source and lesson 13 (#31)

Stacked on Stage 15 (PR #30) ← … ← #2. None merged. mambo-power unchanged at 26be8c1. Real
`data/` and progress unchanged (gate check).

- **Dataset review** (ADR 0014; `docs/datasets/eia930-fuel-type-data.md`). Route
  `electricity/rto/fuel-type-data` discovered from the live parent listing with the local
  key (4 metadata requests): facets `respondent` and `fueltype`, `value` = "Net
  Generation" in `megawatthours`, hourly UTC, `startPeriod` 2019-01-01T00. Codes from the
  Form EIA-930 instructions (15) plus `UES` from the API facet. Storage sign rules and the
  About page's conflicting pumped-storage guidance are recorded; ERCOT's convention is
  disclosed as unstated. Local use cleared on the route's own terms; publication unreviewed.
- **Connector** (`generation.py`): `EIAClient.fetch_series` generalizes the existing fetch;
  store namespace `eia930-fuel-type` with `energy_source` in the identity; no category
  filter (unknown codes kept and flagged); signs and units preserved; revisions with lineage.
- **Refresh**: dataset `eia-generation`, disabled by default and optional in plan files;
  separate budget; `eia_api_requests_budgeted` shows the combined EIA load; its health and
  coverage come from its own store.
- **Explore and lesson 13** (EXPLORE-04): signed stacked bars with category selection,
  coverage per category, hour sums with completeness, shares withheld when negative or
  incomplete, definitions (net generation vs capacity vs fuel vs marginal). Lesson 13
  "Reading the actual generation mix" with five snapshot-bound exercises; 7 glossary terms.
- **Wording fix**: older ERCOT OperDays are "not available through the access method this
  app implements", not lost.
- **Live (scratch storage, local key, never shown).** `sources --remote`: route, facet,
  entity, and units confirmed, no unreviewed codes (3 requests). `collect --days 2
  --lookback-days 0`: 1 request, 232 rows = 8 categories (BAT, COL, NG, NUC, OTH, SUN,
  WAT, WND) × 29 hours (2026-10-11T00 .. 2026-10-12T04; EIA had published nothing later).
  Every stored value matched the archived response (232/232); BAT negative in 16 hours
  (min −7,907). Repeat: 1 request, 0 new, 0 revised, 232 unchanged. `validate` ok;
  `health`: fresh, label 2026-10-12T04.
- **Browser (Playwright CLI; scratch data; PID-tracked servers).** Populated and empty
  Explore views, keyboard source selection, keyboard category selection (Backspace to
  BAT only: axis −8,000 .. 10,000, 16 bars below zero), dark theme at 640 CSS px, light
  at 375 px (no page overflow), lesson 13 exercise answered by keyboard. Fix found: the
  chart axis showed local clock time under a UTC label (aware timestamps); now naive UTC.

## 2026-10-12 — Stage 15: bounded local refresh and System Health (#29)

Stacked on Stage 14 (PR #28) ← … ← #2. None merged. mambo-power unchanged at 26be8c1. Real
`data/` and progress unchanged (gate check).

- **Refresh** (`refresh.py`, `refresh_config.py`, `content/refresh.yaml`; ADR 0013).
  - `mambo refresh [--dry-run] [--source …] [--config …]` calls the existing EIA and
    ERCOT collectors one after another, under a refresh lock.
  - Each source has its own budget. Results are complete (exit 0), partial (exit 3), or
    failed (exit 2), with redacted diagnostics and pruned JSON logs.
  - Catch-up is planned from committed runs. EIA: UTC days after the last committed day
    plus a lookback, capped at 14. ERCOT: calendar-label OperDays plus one lookback
    document, capped at 7; gaps older than the ~31-day public list are flagged as
    outside history.
  - Absent rows are never treated as a missed job or filled.
- **System Health (HEALTH-01).** A read-only page and `mambo health`, showing separately:
  last attempt vs last success, observation label, publication time (ERCOT only), and
  retrieval time. Also shown:
  - freshness from labels or publication time, and "unknown" when the store can't be
    read;
  - coverage and absent counts, storage validation, and recent refreshes;
  - content versions, review dates, and status, with "no automatic monitoring" and the
    regulatory snapshot notice.
- **Scheduling (OPS-01).** `scripts/refresh-task.ps1` previews by default and has Task
  Scheduler parse the XML; no task was registered.
- **Live (scratch storage).** ERCOT refresh: 4 requests, 648 new values (OperDays
  10/09–10/11/2026). Repeat: a 1-document lookback, 2 requests, 216 unchanged. Health
  showed fresh, and validate passed. EIA was not run live (credential not reused).
- **Browser (Playwright CLI; scratch data; PID-tracked server).**
  - States: empty, successful, partial (a live refresh with no EIA key: EIA failed,
    ERCOT succeeded, exit 3), stale (threshold lowered in a scratch plan), and unknown (a
    hidden Parquet file).
  - Keyboard: "Check again" (Enter) and the view selector (arrow keys).
  - Dark theme at 640 CSS px (200% equivalent) and light theme at 375 px: no page
    overflow.
  - Fixes found: the per-source refresh-log result is now shown (failures before
    collection were invisible); the coverage table is transposed for phones; lesson
    labels no longer render as a Markdown list.

## 2026-10-11 — Stage 14: regulatory responsibility explorer and compliance lessons (#27)

Stacked on Stage 13 (PR #26) ← … ← #2. None merged. mambo-power unchanged at 26be8c1. Real
`data/` and progress unchanged (gate check).

- **Source review.**
  - Used: FPA §201 and §215 and CEA §2 (GovInfo U.S. Code), 18 CFR 40.1 (eCFR), three
    Federal Register documents (GovInfo and the FR API), the CPUC About and Resource
    Adequacy pages, ERCOT About, and the ISO-NE tariff index.
  - Not readable and not bypassed: ferc.gov (403), nerc.com, texasre.org, cftc.gov
    (verification page), DOE OE-417 pages, puc.texas.gov (402), and federalregister.gov
    pages (verification).
- **Records** (`responsibilities.yaml` v1.0.0, ADR 0012).
  - 17 records across six activities, each validated.
  - Labels: binding, tariff, guidance, summary, or proposal.
  - Dates: null when unknown; an effective date needs a quoted basis; proposals never
    carry one; a retrieval date is never an effective date.
  - Wording that concludes applicability is rejected.
  - Also recorded: four open questions (ERCOT and federal roles, CIP-003-11 rule vs
    standard dates, the DOE-417 version, the CFTC/FERC boundary) and the source gaps.
- **Compliance page (COMP-02).**
  - Explorer by activity, with "Relevant source to investigate" entries.
  - Each entry shows links, sections, versions, dates, limitations, and review status.
  - Overlaps are shown; a claim-to-source map is included.
- **Lessons 11 and 12 (COMP-03).**
  - New lesson fields: `claims` linked to records, and `compliance` exercises keyed on the
    record-set fingerprint.
  - Lesson 12 uses a SYNTHETIC company and its own invented policy.
  - 20 glossary terms.
  - Operational compliance (COMP-04) and a maintained rules database (COMP-01) stay
    planned.

## 2026-10-11 — Stage 13: time-shape exposure under a flat-block hedge (#25)

Stacked on Stage 12 (PR #24) ← … ← #2. None merged. mambo-power unchanged at 26be8c1. Real
`data/` and progress unchanged (gate check).

- **Context sourced** from EIA's 2011 Texas heat-wave article (a 16-hour on-peak block whose
  afternoon hours traded far above its morning hours; block prices average both). FERC's
  glossary showed a human-verification page and was not used.
- **Calculation `time_shape` v1.0.0** (ADR 0011): per-interval physical q·p, hedge receipt
  B·d·(p − K), net; totals Σh·K + Σr·p = B·D·K + R·p̄ + Σ r(p − p̄) with duration-weighted
  p̄. Both decompositions computed independently and checked; verified on a 432-point grid.
  Ten hand-derived benchmarks, including the required case (net 11,000 = 8,000 + 0 +
  3,000), the reversed shape (−3,000), equal totals with a non-zero residual, and unequal
  durations (p̄ = 50, not 40).
- **Lesson 10** and a Finance section (FIN-05). Accessible interval editor (choose an
  interval, edit its numbers; add or remove intervals), narrow one-interval viewer, and the
  wide table in an expander. No model prices; no calendars or DST. Block products, forward
  curves, and valuation remain unimplemented.
- **Browser:**
  - the default scenario rendered the required benchmark;
  - choosing t2 by typing and entering 100 MWh by keyboard gave 7,000 = 8,000 − 2,500 + 1,500,
    labeled "edited from synthetic scenario peaky v1.0.0";
  - a 0 h duration showed the error and no shape tables;
  - "Add an interval" by keyboard added t3;
  - focus ring on every Finance control ≥ 3.28 (light) / ≥ 4.03 (dark);
  - at 375 px only the all-columns table (in its "scrolls sideways" expander) scrolls inside
    its box, with no page overflow;
  - 200% zoom fine;
  - a lesson 10 exercise answered by keyboard.

  Owned PIDs only; all stopped; real data and progress unchanged.
- **Tests:** 603 passed, 1 skipped on CPython 3.11.16 and 3.14.2; gate 9/9.

## 2026-10-11 — Stage 12: locational basis exposure and a simplified hedge (#23)

Stacked on Stage 11 (PR #22) ← … ← #2. None merged. mambo-power unchanged at 26be8c1. Real
`data/` unchanged (gate check); user progress not reset.

- **Concepts sourced** from FERC's market-assessment glossary (basis, fixed-for-floating
  swaps, hedging; natural-gas context), checked in a browser. The CFTC glossary showed a
  human-verification page and was not used.
- **Calculation `basis_exposure` v1.0.0** (ADR 0010): basis = P_L − P_H; physical Q·P_L; hedge
  receipt H·(P_H − K) (negative = buyer pays); net Q·P_L − H·(P_H − K) (negative = credit)
  = Q·K + Q·basis + (Q − H)·(P_H − K), computed independently and checked; verified on a
  2,000-point bounded grid plus the matched-hedge identities. Nine hand-derived benchmarks
  including negative prices, Q = 0 with H > 0 (a financial position), and a case where the
  hedge raises cost.
- **Same-run pair import:** two verified prices from one run at two different buses (Stage 11
  checks per bus); different runs refused; K never modeled; Stage 11's stage restriction
  unchanged (tested).
- **Lesson 9** (financial-contracts-and-risk stage; after lessons 6 and 8; agent-authored,
  unreviewed) and a second Finance section (FIN-04). Forwards, swaps, futures, options, and
  PPAs remain unimplemented.
- **Found and fixed:** with the default H = Q, the mismatch exercise's options collapsed (all
  zero) and it became unavailable; a decoy that stays distinct was added, and the default is
  now underhedged (H = 80) so every component is visible.
- **Browser:**
  - after lesson 7 only the 1 verified run was offered (5 withheld + infeasible excluded);
  - a same-bus import was refused with values unchanged;
  - after lesson 6 the pair import (run cb07445a, C/A) by keyboard gave P_L 40, P_H 20,
    basis 20, net 5,600 = 4,000 + 2,000 − 400, a case where the hedge raised cost;
  - editing P_H relabeled only P_H as synthetic;
  - focus ring on every Finance control ≥ 3.28 (light) / ≥ 4.03 (dark);
  - lesson 9 exercise answered by keyboard;
  - no overflow at 375 px (dark) or 200% zoom.

  Owned PIDs only; all stopped; real data unchanged.
- **Tests:** 551 passed, 1 skipped on CPython 3.11.16 and 3.14.2; gate 9/9.

## 2026-10-11 — Stage 11: introductory energy settlement (#21)

Stacked on Stage 10 (PR #20) ← … ← #2. None merged. mambo-power unchanged at 26be8c1. Real
`data/` unchanged (gate check); user progress not reset.

- **Source boundary (ADR 0009):** ISO New England's public markets page and its DA/RT energy
  bill-item pages support a day-ahead settlement of commitments and a separate real-time
  settlement of deviations at the RT LMP (hourly DA; five-minute RT; invoices carry other
  allocations). Nothing generalized to other markets; ISO-NE's invoice sign convention not
  adopted. Cited as reference documents in the source register (no data ingested).
- **Calculation `energy_settlement` v1.0.0:** S = D·P_DA + (A − D)·P_RT on MWh and
  $/MWh; one signed amount (buyer pays, seller receives; negative = buyer credit);
  bounded finite inputs; MW entry needs an explicit duration; full provenance and a
  calculation id. Seven hand-derived benchmarks plus the equal-price identity and the
  exposure derivatives.
- **Modeled-price import:** only an optimal `opf.dc` run with verified prices, current checks,
  and the pinned package; one price, one field; one run never supplies both prices;
  editing the value drops the modeled label.
- **Finance page (FIN-03) and lesson 8** "From scheduled energy to settlement" (settlement
  stage; agent-authored, unreviewed), with 5 exercises from the calculator's current
  result. Futures, options, PPAs, hedging, credit, and collateral stay planned.
- **Found and fixed:**
  - an invalid MW entry (no duration) raised before the price widgets were drawn, so
    Streamlit reset the prices; widgets are now drawn before calculating;
  - number inputs only recolored a thin border on focus; `focus.css` now rings them
    (3.68 light / 5.14 dark);
  - the import's run labels ("cost 3,000 per h") were ambiguous; they now show demand, AC
    rating, and offers.
- **Browser:** Finance and lesson 8 in both themes, keyboard entry and the full import by
  keyboard (only the 6 verified runs offered out of 12 saved), a keyboard-answered exercise,
  375 px and 200% zoom without overflow. Owned PIDs only; all stopped; real data unchanged.
- **Tests:** 515 passed, 1 skipped on CPython 3.11.16 and 3.14.2; gate 9/9.

## 2026-10-11 — Stage 10: isolation hardening, focus visibility, review readiness (#19)

Stacked on Stage 9 (PR #18) ← … ← #2. None merged. mambo-power unchanged at 26be8c1.

- **Real progress file preserved:** `data/learn/progress.json` was not modified (its
  timestamp is still 18:15:35). The contamination is documented without claiming the file
  holds no real activity. New optional `mambo learn-reset` (dry run by default, typed
  confirmation, verified timestamped backup outside any tracking repository, no
  overwrite, restore steps). Not executed. Owner decision recorded as BL-7.
- **Isolation hardening:** `MAMBO_FORBIDDEN_DATA_DIRS` in the app's own configuration check
  (casing, relative paths, junctions/symlinks, 8.3 aliases); the test session uses a
  scratch data dir, the protection variable, and a scratch working directory; the gate
  gives subprocesses scratch dirs and adds a 9th check, **real data directory unchanged**.
  Sentinel tests use a fake protected folder; mutation checks confirm the guard layers.
- **Found while hardening:**
  - the user's home folder contains a `.git` folder, which made temp folders look
    "inside a repository" (the scratch working directory is now its own root);
  - that `.git` is not a valid repository, so the backup tool asks Git itself.
- **Focus:** no supported theme option can reach 3:1 in dark mode, so per the stage's
  authorization a focus-only stylesheet adds a 3 px #3B82F6 ring (ADR 0008). Measured in
  both themes on every named control: ≥ 3.28:1 (light), ≥ 4.03:1 (dark); chip buttons
  5.17:1. Also measured: light secondary hover, links (7.51 / 6.58, underlined), 200% zoom,
  320 CSS px.
- **Content:** lesson 6 → v1.1.0 (uncited "real ISO prices also reflect…" list replaced by
  one cited statement from PJM Manual 11, Revision 137; model statements, the market
  statement, and limitations separated); lesson 5 → v1.0.1 (uncited operator claims
  removed); lesson 7 → v1.1.1 ("subgradient" labeled as interpretation); shared lesson
  text narrowed. Lesson 1's EIA quote verified against the current PDF. No exercise
  changed. Corrections log in the checklist; BL-3 stays open.
- **Browser:** keyboard focus across all named controls in both themes, real Tab and
  Shift+Tab, 200% zoom, 320 px, light secondary hover, links. No screen reader available.
  Owned PIDs only; all stopped.

## 2026-10-11 — Stage 9: explanation correctness, button contrast, review package (#17)

Stacked on Stage 8 (PR #16) ← #14 ← … ← #2. None merged. mambo-power unchanged at 26be8c1.

- **BL-5 fixed (wording and records, not the gate):** one shared module
  (`modeling/sensitivity.py`) now words the price check everywhere (adapter notes, lab,
  lesson 7 panel, exercises, lessons 6–7, glossary). Rates are *average* incremental /
  decremental cost rates over the stated ±0.1 MW change, with formulas, units, the
  per-direction cost-rate change, feasibility per direction, and the gate status. A
  breakpoint inside the change is explained as a blend; neither average is called a local
  marginal rate. The capacity-edge note names only the infeasible direction. Gate decisions
  unchanged (tested).
- **New lesson runs:** 0.05 MW below a breakpoint (blend 25 vs. local 20) and zero demand
  (decrease-only infeasible); new exercise `blended-rate`. Lesson 7 → v1.1.0, lesson 6 →
  v1.0.1. `CHECKS_VERSION` 1.2.0 and generator 1.1.0 invalidate older results and answers.
- **Contrast:** `.streamlit/config.toml` sets primary `#2563EB` for both themes (the
  System/Light/Dark menu remains). White button text: 5.17:1 default/active, 8.54:1
  hover/focus (was 3.30:1). Automated checks in `tests/test_theme_contrast.py`. Focus-ring
  contrast and other items logged as BL-6.
- **Review package:** `docs/review/human-review-checklist.md` (all 7 lessons and the
  35-term glossary, blank reviewer fields, agent-noticed items). BL-3 stays open.
- **Found and fixed: test pollution.** A Stage 8 test's `monkeypatch.undo()` dropped its
  `MAMBO_DATA_DIR` override, and an AppTest rerun wrote a "viewed" mark for lesson 6 into
  the real `data/learn/progress.json` (created 18:15:35 by that test). Tests now run with a
  session temp data dir and fail if the real `./data` changes (`tests/conftest.py`). The
  existing file was left for the owner to decide.
- **Browser:** near-breakpoint and capacity-edge wording, the infeasible base run, a failed
  run through a scratch-only corrupted-solver harness, rendered button colors in both
  themes and states, keyboard answering, 375 px. Owned PIDs only; all stopped.

## 2026-10-11 — Stage 8: market-mechanics lessons backed by verified model runs (#15)

Stacked on Stage 7 (PR #14) ← #12 ← … ← #2. None merged. mambo-power is still pinned to
26be8c1 (unmodified). No new collectors, cost forms, networks, or calibration.

- **Three lessons** (fundamentals stage, after lesson 1; agent-drafted, unreviewed):
  5. Power flow versus economic dispatch (prerequisite: lesson 1)
  6. Why modeled prices differ by location (prerequisite: 5)
  7. When one marginal number is not verified (prerequisite: 6)
- **Fixed lesson runs** (`modeling/cases.py`): 10 OPF runs from lab presets plus fixed
  overrides, and 2 power-flow runs at a specified dispatch
  (`adapter.run_dispatch_power_flow`, Stage 6 checks; G2 either fixed or taken from a
  verified OPF run). Results count only while current (case, scenario version, pin,
  fingerprint). Runs happen only on the lesson's button and are saved to the model-run
  store, never to observation storage.
- **11 model-backed exercises** (`model_exercises.py`): binding constraint, next increment,
  positive price sensitivity (re-dispatch reproduces the verified price), relaxation
  cost (equals the sensitivity × rating change, same binding set), cost rate vs.
  interval cost vs. price vs. sensitivity, power-flow violation, feasible but not
  cheapest, withheld reason, infeasible direction, non-unique vs. infeasible, and
  uniqueness vs. price verification. The snapshot covers inputs, pin, check and
  generator versions, and statuses; the run ids are saved with the answer.
- **Navigation:** lessons link to their lab presets; each lab links to its lessons.
  Only validated ids cross pages.
- **Benchmarks asserted in tests:** congested 90/60 MW, 3,600 $/h, prices 20/30/40, AC
  sensitivity −40. Also: +10 MW → 80/80 (4,000 $/h); AC 70 MW → 130/20 (3,200 $/h); the
  150/0 power flow puts 75 MW on AC (rated 60); the 60/90 dispatch is feasible at
  3,900 $/h. At both breakpoint cases the solver's dual lies between the one-sided rates.
- **Found in the browser and fixed:** the provenance table scrolled sideways at 375 px
  (now 3 columns); the topology table said ratings were a "learner control" inside
  lessons; "you (fixed)" mislabeled a dispatch taken from a verified run.
- **Not changed:** the price gate. Two label issues are logged as BL-5.
- **Tests:** 382 offline (42 new). Gate 8/8 on CPython 3.11.16 and 3.14.2. Mutation
  checks: removing the fingerprint guard, the `$` escaping, or the verdict reset each
  fails a test.
- **Processes:** baseline none. Owned servers were started with recorded PIDs and
  restarted once by PID; all 6 stopped, 0 remain, ports free.

## 2026-10-11 — Stage 7: independently verified DC OPF and economic-dispatch lab (#13)

Stacked on Stage 6 (PR #12) ← #10 ← #8 ← #6 ← #4 ← #2. None merged. mambo-power is still
pinned to 26be8c1 (unmodified); highspy is 1.15.1.

- **Formulation audit (ADR 0007),** traced in `opf/dc_opf.py` and `opf/__init__.py`:
  - MW dispatch variables; objective Σ c1·p (+c2·p² if present)
  - one balance row; PTDF flow rows with fixed-load constants
  - reference bus only through PTDF; pu → MW before the LP
  - raw HiGHS row and column duals; `lmp = λ + μ·PTDF`
- **Units:** the objective is a cost *rate* in $/h. The lab uses an explicit 1-hour
  interval: interval cost ($) = rate × 1 h.
- **Hand-derived benchmarks:** uncongested (3000 $/h, all 20), capacity-limited
  (3500, all 30), congested (90/60 MW, 3600, prices 20/30/40, AC dual −40), infeasible,
  breakpoint (one-sided 30/20), congestion breakpoint, and equal offers (non-unique
  dispatch). All match.
- **Price verification:**
  - Two-sided demand perturbations at every bus at 0.01, 0.1, and 1 MW equal the reported
    prices within 1e-6 $/MWh, inside the same active set.
  - The rating relaxation equals the flow dual.
  - At breakpoints the one-sided rates differ, and the solver's single dual lies between
    them.
- **Adapter** (`run_dc_opf`, extending the existing adapter):
  - status, finiteness, balance
  - flows recomputed with the verified DC power flow
  - bounds, ratings, recomputed objective
  - KKT stationarity, signs, and complementary slackness
  - price decomposition at every bus, with PTDF measured by the DC power flow
  - per-run two-sided ±0.1 MW price check; prices are withheld at breakpoints, for
    unservable perturbations, or on a mismatch
  - non-unique dispatch detection
  - Tampered dispatch or prices fail the run with no outputs.
- **Lab:** a lab selector (power flow stays the default) and an economic-dispatch lab
  with teaching-case presets. Results are invalidated on any input change, infeasible
  runs show no numbers, and runs persist locally (`kind = opf.dc`).
- **Found in the browser and fixed:**
  - a pair of "$" in markdown rendered as LaTeX and erased the cost units (escaped, with a
    regression test proven to fail without the fix)
  - escaping the slider labels put "\$" into aria-label (reverted: one "$" cannot pair)
  - the 6-column dispatch table and the saved-runs table overflowed at 375 px (narrowed)
- **Tests:** 340 offline tests. Gate 8/8 on CPython 3.11.16 and 3.14.2.
- **Processes:** baseline none. Owned servers were restarted 4 times, by PID only; all
  stopped, 0 remain, ports free.

## 2026-10-11 — Stage 6: verified mambo-power integration and first teaching lab (#11)

Stacked on Stage 5 (PR #10) ← #8 ← #6 ← #4 ← #2. None merged.

- **Package:** mambo10005/mambo-power (MIT), **pinned to v0.2.0 commit 26be8c1**.
  Inspected from a read-only clone; the package repository was not modified.
  - Capability register (`docs/capability-register.md`): only **DC power flow** is
    verified and exposed.
  - DC OPF is inspected but not exposed: its duals are labeled LMPs ($/MWh) and that
    was not independently verified.
- **Package's own tests at the pin** (DC power flow, roles, islands, invariants, guards,
  results): 99 passed on 3.11.16 and 99 on 3.14.2.
- **Dependency:** a Git direct reference at the full commit (hatch
  `allow-direct-references`; the package is never published).
  - New packages: scipy (1.17.1 on 3.11, 1.18.1 on 3.14), highspy, pydantic,
    pydantic-core, annotated-types, typing-inspection.
  - Inventory: 54 packages; mambo-power's license reviewed (MIT).
  - Installs and imports on both Pythons. At runtime the adapter verifies the
    installed commit matches the pin.
- **Lab:** synthetic three-bus DC power flow (`modeling/`).
  - Bounded inputs: G2 0–200 MW, load at C 0–300 MW, x_AC 0.05–0.50 pu, AC in or out.
  - Independent checks at 1e-6 MW: balance, KCL, Δθ/x, reference angle, finiteness.
  - Limit violations are reported. Failed runs show no outputs.
  - Results are hidden when inputs change.
  - Runs are saved to `<MAMBO_DATA_DIR>/model-runs/`.
- **Numerical verification:**
  - hand-worked case (AB 37.5, BC 87.5, AC 62.5 MW; θB = −0.0375 rad, θC = −0.125 rad)
  - an independent closed-form reference over 6 cases, a radial case, monotonicity,
    and sign reversal, all within 1e-9 MW
- **Accessibility:** a new ERCOT **observation viewer**: a narrow (5-column) table of
  every value for one series, with series switchable by keyboard. At 375 px it fits with
  no sideways scrolling. The wide table is kept in an expander. DSTFlag stays as
  published.
  - Correction: my Stage 5 chat summary called DSTFlag `N` "standard time". That
    interpretation is unsupported; it appears nowhere in the repository.
- **Backlog:** `docs/backlog.md` BL-1 (live ERCOT DST validation, recorded and not
  scheduled), BL-2 (OPF verification).
- **Tests:** 286 offline tests. Gate 8/8 on CPython 3.11.16 and 3.14.2.
- **Browser (Chrome):**
  - Lab, populated and empty: run → 37.5/87.5/62.5 with provenance.
  - Keyboard-only: an arrow key moved G2 50 → 60 and hid the stale result; Tab to Run,
    Enter → 30/90/60, matching the hand calculation.
  - ERCOT viewer at 375 px dark: fits; keyboard series switch to EAST works.
- **Processes:** the baseline had no servers. Two were started with recorded PIDs, and
  exactly those 6 PIDs were killed. 0 remain; ports are free.

## 2026-10-11 — Stage 5: direct ERCOT actual-load connector (#9)

Stacked on Stage 4 (PR #8) ← #6 ← #4 ← #2. None merged.

- **Report:** ERCOT NP6-345-CD "Actual System Load by Weather Zone" (type 13101).
  - Access: the ercot.com public listing + download, which needs no login. These are
    the URLs ERCOT's product page uses, not a documented developer API (ADR 0005).
  - The ERCOT Public API needs registration (401 without it). No account was created
    and no terms were accepted.
- **Review** (source register; `docs/datasets/ercot-np6-345-cd.md`):
  - Terms §5 permit raw-data reuse in compilations, charts, and analyses; §6 forbids
    degrading ERCOT systems.
  - Local use cleared. Publication review still pending.
  - Unverified: units, label time zone, DST representation, and the TOTAL definition.
- **Connector:**
  - one transport; budget of 10 requests and at most 7 documents per run
  - 30 s timeouts, at most 2 retries, 1 s pause between requests
  - listing and ZIP size limits; in-memory ZIP reading with path, member, and size
    checks (`safe_zip.py`)
  - strict CSV header and row validation
  - clear access and unavailable errors; no scraping fallback; never uses
    EIA_API_KEY
- **Storage:** `Store(namespace, schema, identity)`.
  - ERCOT lives in `ercot-np6-345-cd/` with its own catalog and lock. EIA is
    untouched (no migration).
  - Identity includes OperDay, HourEnding, and DSTFlag, so DST twins stay distinct.
  - Reposts become revisions with document lineage.
- **CLI:** `--source ercot` on `sources`/`collect`/`validate`/`status`/`storage`.
  ERCOT collect takes `--latest N` or `--publish-date`, plus `--dry-run`.
- **Explore:** a source selector (EIA or ERCOT direct, never joined). The ERCOT view
  shows:
  - TOTAL and zones in a tested 9-colour palette
  - original labels, with HourEnding/DSTFlag on the chart axis
  - a chart `alt` text
  - coverage and the zone-sum check
  - publication time (raw and UTC) and retrieval time
  - units "not stated", and limitations
- **Tests:** 252 offline tests. Gate 8/8 on CPython 3.11.16 and 3.14.2. Fixtures are
  synthetic; no ERCOT file is committed.
- **Live (2026-10-11, no credential):**
  - The listing showed 32 public CSV documents (published 2026-09-10..2026-10-11).
  - `--latest 3` collected OperDays 10/08–10/10/2026: 648 values, all DSTFlag N,
    0 nulls, max |zone sum − TOTAL| 0.02.
  - Stored values match the archived files 648/648.
  - The repeat collection was idempotent (648 unchanged). `validate` ok.
  - The EIA catalog sha256 was unchanged.
- **Browser (Chrome),** using scratch copies of the data:
  - EIA view still renders.
  - ERCOT view: chart, label axis, units, provenance, coverage, and limitations;
    zone selection works by keyboard.
  - 375 px dark: no page overflow.
  - Empty ERCOT store: instructions, no chart, and no store created.
  - **Gap:** the 12-column hourly table scrolls inside a container that can't take
    keyboard focus (a Streamlit limitation).
- **Processes:** the baseline had 0 Streamlit processes. Servers were started with
  recorded PIDs, and exactly those 6 PIDs (2 trees) were killed. 0 remain.
- Next: verify ERCOT's DST representation on OperDay 2026-11-01 (posted about
  2026-11-02), then reconciliation research only if units and time zones become
  documented.

## 2026-10-11 — Stage 4: beginner lessons using EIA observations (#7)

Stacked on Stage 3 (PR #6) ← #4 ← #2. None merged.

- **Lesson engine** (`lessons.py`): validated Markdown + YAML front matter with
  versions, effective dates, sources, dataset bindings, calculation ids,
  exercises, limitations, and review fields. Validation rejects "human-reviewed"
  without a named reviewer, an AI reviewer, or a reviewer who is also the author.
  All four lessons are **agent-drafted, unreviewed**.
- **Four lessons:**
  1. power vs. energy (synthetic examples only)
  2. reading a demand series
  3. demand vs. the published forecast (error = actual − forecast; mean error,
     MAE, RMSE)
  4. missing observations (absent vs. null vs. zero vs. not collected;
     coverage per series)
- **Calculations** (`calculations.py`, CALC-01; docs/calculations.md):
  - `power_energy`, `series_summary`, `coverage`, `forecast_error`, all
    pure and versioned
  - results keep selection, unit, formula version, valid counts,
    exclusions, and revision references
  - "unavailable" instead of a number for empty, duplicate, or mixed-unit input
- **Exercises:**
  - generated from a snapshot fingerprint (selection + revisions + values)
  - deterministic per snapshot; regenerated, with a notice, when the window or
    the data changes
  - answers computed by the same calculations
- **Progress:** local JSON in `<MAMBO_DATA_DIR>/learn/progress.json`
  (gitignored), with three distinct states. "Understanding demonstrated" requires
  every exercise to be right on the first attempt.
- **Learn page:**
  - status table and lesson selector; prerequisite buttons; deep links
    (`?lesson=`)
  - beginner/technical toggle and glossary with acronym expansions
  - sources and freshness
  - charts with HTML data tables
  - exercises with worked explanations; bookmarks
- **Tests:** 192 offline tests. Gate 8/8 on CPython 3.11.16 and 3.14.2.
- **Browser (Chrome),** using copies of the real local observations in scratch
  directories, so the user's own progress file was not touched:
  - all 4 lessons populated in the light theme
  - all 4 empty: text readable, no charts, instructions, data exercises marked
    unavailable
  - keyboard-only: Tab order reaches every control; arrow keys pick an option;
    Enter submits
  - 375 px dark: no page overflow
  - light theme: text contrast 12.5:1
- **Fixed from browser findings:**
  - the status table lagged one interaction behind an answer
  - lesson labels changed with progress, which can reset the selector
  - an 8-column coverage table needed sideways scrolling on phones; now 3 columns
  - the orange chart line was 2.53:1 on white; now #d95f02 at ≥ 3.7:1 in both
    themes, with a regression test
- Also found: a Stage 3 Streamlit server was still running, because TaskStop
  leaves the server process behind. It is stopped, and cleanup is now explicit.
- Not done:
  - no human review of lesson content
  - no screen-reader testing
  - charts have captions and data tables but no in-chart text alternative
  - other browsers not tested
- Next: Stage 5, a bounded ERCOT connector (R-29), after its source review.

## 2026-10-11 — Stage 3: first bounded EIA collection, storage, and chart (#5)

Stacked on Stage 2 (PR #4), which is stacked on Stage 1 (PR #2). None merged.

- **Dataset review** (source register):
  - EIA-930 `electricity/rto/region-data`; `ERCO` verified in EIA's official
    reference tables; metrics `D`/`DF`; units `megawatthours`.
  - Hour-ending is documented for EIA-930 but **not for the API `period`
    field**, so interval boundaries are not derived.
  - Cleared for local collection and use. Public redistribution not yet reviewed.
  - Without a key, EIA metadata returns HTTP 403, so live facet verification
    is pending.
- **Dependencies:** `duckdb 1.5.6` and `pyarrow 25.0.1` declared and locked.
  The license inventory has 46 packages. A new test replaces the Stage 2 ban:
  every declared runtime dependency must be imported in `src/`.
- **Connector:**
  - bounded queries, deterministic pagination, strict validation
  - timeouts, bounded retries with backoff, a request budget
  - redaction of raw, encoded, query, and echoed keys; errors raised `from None`
- **Storage:**
  - Parquet partitioned by entity/metric/run, a SQLite run catalog, DuckDB
    `observations`/`latest` views
  - idempotent re-ingest; revisions with lineage
  - atomic file writes plus a one-transaction commit; single-writer lock
  - `validate` for recovery (reports by default; quarantine moves, never deletes)
- **CLI** (`mambo`): `sources [--remote]`, `collect [--dry-run]`, `validate`,
  `status`, `storage`.
- **Explore page:**
  - ERCOT actual demand vs. the BA-published day-ahead forecast
  - date range, completeness and missing-value indicators, observation table
  - source, units, and interval text; last collection and a stale warning
  - limitations
  - instructions instead of a chart when no data exists
- **Tests:** 118 offline tests. The gate passes 8/8 on CPython 3.11.16 and
  3.14.2. All fixtures are **synthetic**, generated in `tests/eia_fixtures.py`.
- **Browser (Chrome, desktop):**
  - Populated state, using a scratch store seeded with *synthetic* rows: the
    chart draws two lines with a gap at the missing hour, and the table expands.
  - Empty state: instructions, no chart or table, no store created.
  - Fixed during the check: legend labels were truncated, and both series were
    drawn in near-identical blues.
- **Live (2026-10-11):** a key appeared in the gitignored `.env` partway
  through the stage. All live commands ran through a guard that suppresses
  output containing any form of the key; no leak was detected.
  - Metadata verified with 3 requests.
  - One bounded collection (1 request): 408 rows. Demand complete; 24
    forecast hours absent from the source.
  - All 408 stored rows match the archived response.
  - The repeat collection was idempotent (408 unchanged).
  - Field names confirmed. Missing data appears as absent rows. The period
    convention is still not stated by the API.
  - DATA-01 → `done`.
  - Explore browser-checked with the real data: two lines, the forecast gap
    shown, the absent-hours warning shown.
- **Guard fix:** the Stage 2 chart guard counted *any* done feature as unlocking
  its section. That meant done backend features would have authorized charts on
  the "Not implemented" Sources and System Health pages. Features that deliver a
  page are now marked `ui: true`, and only those unlock charts. A test also
  checks that the page dispatcher matches these flags.
- Next: beginner lessons using these observations.

## 2026-10-11 — Stage 2: reproducible local quality workflow (#3)

Stacked on Stage 1 (PR #2, unmerged).

- **Lock:** `uv.lock` (uv 0.12.5, universal) covers runtime dependencies and
  the `dev` group. The dev tools moved from an extra to a PEP 735 dependency
  group (ADR 0003). DuckDB and PyArrow are still not declared.
- **Environments:** `.venvs/py311` (CPython 3.11.16) and `.venvs/py314`
  (CPython 3.14.2), built with `uv sync --locked`. The developer's `.venv`
  was not touched.
- **Quality gate** (`scripts/check.ps1` → `scripts/quality.py`), 8 checks:
  - config/content validation, offline lock check, Ruff lint and format check
  - offline pytest (42 tests), import + headless startup smoke test
  - tracked/staged/untracked path check, secret scan
- **Results:** 8/8 pass on both Python 3.11.16 and 3.14.2 (Windows 11).
- **The gate fails when it should:**
  - It exited 1 on a real lint/format slip.
  - It exited 1 on a planted token-shaped string and a force-staged
    stack dump, without printing the token.
  - Its temporary server is stopped, and it changes no source or tracked
    files.
- **Guards:** the fake-result guards are now feature-status-aware
  (`tests/guards.py`). Self-tests show that a chart on an unimplemented page
  fails, an authorized chart on an implemented page passes, and feature-status
  drift fails.
- **Licenses:** `docs/dependency-licenses.md` covers 45 locked packages.
  - 10 are flagged "needs review": compound expressions, a bare "BSD
    License" classifier, or MPL.
  - 3 shipped license files were read by hand (pytest, pyyaml, ruff).
  - Streamlit's wheel ships no license file, so it is unresolved.
- **Sources:** ERCOT recorded as the first operator after EIA (R-29). EIA
  terms reviewed (source register); the source notes of each EIA route are
  still pending.
- Not done: hosted CI, Python 3.12/3.13, non-Windows platforms, a browser
  re-check (no UI change except QA-01's status).
- Next: DATA-01 bounded EIA collection and storage.

## 2026-10-11 — Stage 1: product specification and application shell (#1)

- PRD filled in from the owner's requirements and split into confirmed
  requirements (R-1..R-28), proposed design decisions (P-1..P-8), and
  unresolved decisions (U-1..U-9). The license is still pending.
- Added the source register (EIA first; every source's review still pending)
  and ADR 0002 (stack and dependency versions).
- Streamlit shell in `src/mambo_explorer`: Home plus 8 sections. Every
  section shows its scope and "Not implemented". The app shows no data,
  charts, or model output.
- `.env.example`: the generic `DATA_SOURCE_API_KEY` is replaced by
  `EIA_API_KEY` (PRD P-7). `DATA_DIR`, `CACHE_DIR`, and `LOG_LEVEL` are kept.
- Offline tests: import, navigation, feature-status consistency, docs/content
  structure, and Streamlit `AppTest` rendering of every page.
- Not done: data collection, storage, modeling, finance/compliance engines,
  authentication, CI.
- Next: QA-01 local quality workflow, then DATA-01 EIA connector.

## 2026-10-11 — Repository initialized

- Created private repo `mambo10005/mambo-electricity-explorer`.
- Added scaffold: README, CLAUDE.md, .gitignore, .env.example,
  pyproject.toml, docs, ADRs, issue and PR templates.
- No application code or dependencies yet.
