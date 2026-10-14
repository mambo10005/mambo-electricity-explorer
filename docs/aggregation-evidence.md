# Hourly real-time aggregation: evidence and candidates (Stage 24)

Investigation of ways to summarize the four M1-aligned NP6-905-CD 15-minute Settlement Point
Prices of one hour at `HB_NORTH` into one hour-level **analytical** value.
- **Decision:** ADR 0021. **Records:** `src/mambo_explorer/ercot/aggregation_policy.py`
  (register in `docs/assumption-register.md`). **Service:** `ercot/aggregation.py`. **Panel:**
  `aggregation_view.py`.
- **Retrieval:** 2026-10-13 for every source. **Review:** AI-authored; not human-reviewed.

## Decision

**No method is production-active.**
- **Records:** two records are defined and approvable, AGG-A (arithmetic mean) and AGG-B
  (duration-weighted mean). Neither has an attributable approval, and M1 has none either.
- **Synthetic use:** candidate calculations run on synthetic inputs.
- **Stored observations:** the summary is withheld, and every blocker is named.
- **Not approvable:** energy-weighted prices and settlement amounts have no record, because the
  quantities they need do not exist in this application.

## 1. Sources and findings

**Types:** OD = official definition, OC = official calculation rule, OR = operational report
behavior, AF = actual-file observation, MI = mathematical implication, TA = project teaching
assumption.

| Id | Type | Source (version) | Section | Proposition | Scope / ambiguity |
|---|---|---|---|---|---|
| OFF-2 | OD | Nodal Protocols Section 4 (Aug 1, 2026) | §4.1(3) | Real-Time SPPs are calculated "for a 15-minute Settlement Interval"; DAM for a one-hour Settlement Interval. | Interval length for settlement; not report labels. |
| OFF-11 | OC | Section 6 (Aug 28, 2026); Section 3 (Aug 1, 2026) | §6.6.1.1; §3.5.2.1(4) | The RT SPP is "the time-weighted average" of SCED prices within the 15-minute Settlement Interval: weights TLMP y = "the duration of the portion of the SCED interval y within the 15-minute Settlement Interval" (seconds). The hub price is floored at −$251 after the adder. | Each 15-minute price is already time-weighted. Nothing defines an hourly figure. |
| OFF-12 | OC | Section 16 (Aug 1, 2026) | §16.11.4.3.3(1)(d) | HRSAP = (1/nhrh) Σ_hrh Σ_{i=1..4} RTSPP(hrh, i, rhub)/4. i is "a 15-minute interval that is part of an Operating Hour"; rhub is the ERCOT North Hub. | **Credit** (forward adjustment factor), not settlement, and not a published price. It shows ERCOT itself uses an equal-weight mean of an hour's four RT SPPs in one formula. |
| OFF-3 | OC | Section 6 (Aug 28, 2026) | §6.6.3.3 | Hub energy imbalance per 15-minute interval = (−1) × RTSPP × (quantities × ¼). The quantities are QSE-specific (self-schedules, DAM awards, trades). | Settlement uses participant quantities. None is public or held here. |
| OFF-8 | OD | Sections 4 and 6 | §4.5.2(6), §6.3(7) | RT prices are final at 1600 of the 2nd Business Day; Board review is still possible. | Finality is not determined by the app. |
| OFF-10 | OC | Section 11 (Jun 1, 2026) | §11.4.4.2 | DST adjust: −4 / +4 fifteen-minute intervals. | Load profiling only. |
| OFF-9 | OR | EMIL product pages | — | NP6-905-CD posts 15-minute SPPs; NP6-785-ER compiles them by year; NP4-197-M reports RTM price corrections. | **No hourly real-time SPP product was found** among the reviewed products (not an exhaustive catalog search). |
| ACT-1/2 | AF | NP6-785-ER 2025–2026; NP6-905-CD | — | Every ordinary hour has intervals 1–4. The repeated fall hour appears as hour 2 N and hour 2 Y (four intervals each). | The reports' own DST documents have not been observed. |
| — | MI | — | — | With equal durations Di, Σ(Pi·Di)/ΣDi = ΣPi/n. Weighting by elapsed time cannot reproduce weighting by energy unless energy is proportional to time. | Algebra. |
| M1, AGG-A/B | TA | project records | — | The label mapping (M1) and the choice of an hourly summary are review-gated assumptions. | Not official definitions. |

**Inaccessible or not found:**
- The 2011 list notice on DST flags (GAP-1, a redirect loop; not bypassed).
- No public interval-level settlement quantities for `HB_NORTH` exist. A hub has no meter.

## 2. Candidates

| Candidate | Formula | Classification |
|---|---|---|
| **A. Arithmetic mean** (AGG-A 1.0.0) | (P1 + P2 + P3 + P4) / 4 | **Mathematically valid.** Source-recognized form (OFF-12, credit context); no ERCOT hourly RT SPP. Review-approved: **no**. Production-active: **no**. Prohibited for settlement, final-price, spread, backtest, or Finance use. |
| **B. Duration-weighted mean** (AGG-B 1.0.0) | Σ(Pi × Di) / ΣDi | **Mathematically valid.** Durations source-supported for DSTFlag N (DUR-15: OFF-2, OFF-11). Review-approved: **no**. Production-active: **no**. Prohibited for the same uses; it is not energy-weighted. |
| **C. Energy-weighted price** | Σ(Pi × Ei) / ΣEi | Mathematically valid; undefined when ΣEi = 0. **Not implementable:** no compatible interval quantities. **Prohibited** in production. |
| **D. Settlement amount** | Σ(Pi × Ei) | Mathematically valid. **An amount in $, not a price.** It omits every other §6.6 charge. **Prohibited** in production. |

**A, arithmetic mean:**
- **Uses:** describes an hour's typical posted price level.
- **Missing interval:** withheld; never averaged over three.
- **DST:** the repeated hour is two separate hours (N and Y), each with four intervals under
  M1. A spring-forward missing hour has no intervals, so there is nothing to summarize.
- **Revisions:** uses the selected revision of each interval under the named policy. A changed
  revision makes snapshots stale.

**B, duration-weighted mean:**
- **Durations needed:** Di comes from DUR-15 (15 minutes) only for DSTFlag N intervals.
  DSTFlag Y is `duration_unsupported`, and 0.25 h is never substituted.
- **Relation to A:** with four verified equal durations it equals A numerically, which adds
  nothing but explicit duration evidence.
- **Unequal durations:** they would differ from A. That occurs only in synthetic examples;
  ERCOT's report intervals are not unequal.

**C, energy-weighted price:**
- **Inputs:** interval energies Ei in MWh with sign conventions (purchase versus sale), for the
  same settlement point and intervals.
- **Not present here:** the app holds no such quantities.
- **EIA-930 demand is invalid:** it is a balancing-authority hourly demand in MWh, not a
  settlement quantity at a hub, and its intervals and time basis differ (no join allowed).
- **Zero total energy:** undefined, never 0.

**D, settlement amount:**
- **Inputs:** participant settlement quantities; Protocols multiply MW quantities by ¼ to get
  15-minute MWh.
- **Output:** $ (currency), so it is not a price.
- **Omits:** every other charge (congestion, ancillary services, uplift, and more).

## 3. Dimensional analysis

| Quantity | Unit | Meaning |
|---|---|---|
| Pi | $/MWh | a price |
| Di | h | elapsed duration (15 min = 0.25 h by DUR-15) |
| Ei | MWh | energy (= MW × h) |
| Power | MW | a rate, not energy |
| A, B outputs | $/MWh | price summaries (A: equal weight per interval; B: weight per elapsed hour) |
| C output | $/MWh | the effective price of an energy quantity |
| D output | $ | a currency amount |

- **A stays a price summary:** a mean of four prices remains a price summary. Each interval
  lasting 15 minutes does not turn it into an energy settlement price, because no energy
  enters the formula.
- **A = B does not make B energy-weighted:** with equal durations, A = B because the weights
  cancel. Both still ignore how much energy flowed in each interval. Energy-weighted (C)
  equals them only when energy is equal in every interval.

## 4–7. Records, approvals, activation, completeness

- **Records:** see `docs/assumption-register.md` ("Aggregation records").
- **Approvals:** recorded with `mambo aggregation approve <id> --version … --scope …
  --accept-limitations … --reviewer … --role … --evidence … --approved-on … --execute` (a dry
  run without `--execute`).

**Production activation requires every one of the following**; otherwise the summary is
withheld with each blocker named:
1. the M1 basis selected explicitly;
2. an active M1 1.0.0 approval for the same scope;
3. a current record whose `depends_on` matches M1's version and scope;
4. an active approval of **that** record (no fallback to another record);
5. a supported revision policy;
6. no unresolved duplicate revisions;
7. complete M1 alignment (four expected intervals);
8. one current Stage 23 alignment snapshot whose selected revisions equal the alignment;
9. duration evidence (B only);
10. a published price for every selected interval revision;
11. successful validation.

**Status precedence:** unsupported_method → alignment_approval_missing → approval_missing →
revision_unavailable → conflicting_revisions → alignment_incomplete → stale_snapshot →
duration_unsupported → invalid_input. The result lists every blocker, not just the first.

**Synthetic approvals:**
- **Where they count:** an approval marked `synthetic` counts only in a data directory that
  contains `SYNTHETIC-ENVIRONMENT`.
- **Where they don't:** in the real data directory they are invalid, so scratch-test approvals
  can never produce a summary from real observations.

**Separate concepts:** collection coverage, M1 alignment completeness, aggregation input
completeness, revision availability, price finality, and correction-feed coverage. **A complete
summary is not a final ERCOT price.**

## 8. Benchmarks (hand-worked; tests/test_aggregation.py)

| Case | Inputs | Expected |
|---|---|---|
| Arithmetic | P = 20, 40, 60, 80 | 200 / 4 = **50 $/MWh** |
| Duration, equal | same, D = 0.25 h × 4 | (5 + 10 + 15 + 20) / 1 = **50 $/MWh** |
| Not energy-weighted | same, E = 10, 10, 10, 70 MWh | (200 + 400 + 600 + 5600) / 100 = **68 $/MWh** |
| Unequal duration (synthetic) | P = 20, 80; D = 0.25, 0.75 | A = 50; B = 5 + 60 = **65 $/MWh** |
| Energy-weighted | P = 20, 80; E = 75, 25 MWh | 3500 / 100 = **35 $/MWh** |
| Settlement amount | same | **3,500 $** |
| Negative prices | −10, −30, 20, 0 | −20 / 4 = **−5 $/MWh** |
| Equal / zero prices | 42.17 × 4; 0 × 4 | **42.17**; **0** |
| Zero total energy | E = 10, −10 | **undefined** (not 0) |
| Fixture hour 3 (UI) | 24.00, 24.25, 24.50, 24.75 | 97.5 / 4 = **24.375 $/MWh** |

**Gating cases also tested:**
- a missing interval;
- a conflicting duplicate revision;
- a stale alignment snapshot;
- unsupported duration (DSTFlag Y, method B; method A still completes);
- missing, revoked, and mismatched approvals;
- the authoritative basis;
- synthetic approvals in an unmarked directory.

## 9. Snapshots

Aggregation snapshots (`<data>/aggregation/snapshots.jsonl`, explicit button, append-only) hold:
- the alignment snapshot reference and its state;
- M1 version, scope, and approval;
- the record version and scope, and its approval;
- the revision policy and the interval revisions and documents;
- a duration-evidence fingerprint;
- the formula and validation versions;
- the output, input prices, and limitations.

A snapshot is **stale** when any of these changes, and **superseded** by a later snapshot of the
same hour, record, and policy. Snapshots are never deleted or overwritten.

## 10. Stage 25 prerequisites (a day-ahead/real-time comparison)

| Prerequisite | Status |
|---|---|
| Active M1 1.0.0 approval (attributable, local) | **missing** (BL-11) |
| Active approval of one aggregation record | **missing** (BL-13) |
| Complete M1 alignment for each hour used | per hour; available |
| Complete aggregation inputs and a current alignment snapshot | per hour; available |
| An explicit revision policy | available (latest- or first-retrieved) |
| The non-settlement limitation displayed | implemented |
| **A separately defined day-ahead-versus-real-time comparison formula**, with its own record and review | **not defined** (BL-14) |

Still unresolved:
- official report-label definitions;
- price finality;
- correction feeds (NP4-196-M/NP4-197-M);
- publication and license;
- human lesson and content review.
