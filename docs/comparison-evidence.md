# Day-ahead vs real-time-summary comparison: evidence and candidates (Stage 25)

Governed comparison of ONE ERCOT NP4-190-CD day-ahead SPP at `HB_NORTH` with ONE approved hourly
analytical summary of the M1-aligned NP6-905-CD real-time SPPs of the same source-native hour.
- **Decision:** ADR 0022. **Records:** `src/mambo_explorer/ercot/comparison_policy.py`.
  **Service:** `ercot/comparison.py`. **Panel:** `comparison_view.py`.
- **Retrieval:** 2026-10-13. **Review:** AI-authored; not human-reviewed.

## Decision

**No comparison is production-active.**
- **Records:** CMP-A 1.0.0 (RT summary minus DAM) and CMP-B 1.0.0 (DAM minus RT summary) are
  defined and approvable. Neither is approved, and neither are M1, AGG-A, or AGG-B.
- **Not approvable:** the absolute difference and the percentage difference.
- **Synthetic use:** candidate calculations run on synthetic prices.
- **Stored observations:** the value is withheld, and every blocker is named.

## 1. Sources

**Types:** OD = official definition; OS = official settlement formula; OC = official analytical or
credit formula; PA = project analytical comparison; ET = common external terminology; TI = teaching
interpretation.

| Id | Type | Source (version) | Section | Proposition | Scope / limitation |
|---|---|---|---|---|---|
| OFF-13 | OS | Nodal Protocols Section 4 (Aug 1, 2026) | §4.6.3(1) | DARTOBLAMT = DAOBLPR × RTOBL, DAOBLPR = DASPP(sink) − DASPP(source). "DART" appears only as a variable-name prefix, for a **locational** day-ahead difference. | DAM PTP Obligations; not DA vs RT. |
| OFF-15 | OS | Section 7 (Dec 5, 2025) | §7.9.2.1(2) | DAM-acquired PTP Obligations are settled at "the difference in Real-Time Settlement Point Prices between the sink … and the source …". | Locational. It shows ERCOT states a sign explicitly (sink minus source). |
| OFF-3 | OS | Section 6 (Aug 28, 2026) | §6.6.3.3 | Day-ahead energy positions (DAEP/DAES) enter Real-Time energy imbalance at the RT SPP, × ¼ per 15-minute interval. | Settles participant **quantities**. Defines no price difference. |
| OFF-14 | OC | Section 16 (Aug 1, 2026) | §16.11.4.3.3(1)(e)–(g) | HDSAP (day-ahead) and HRSAP (real-time) averages are used as **ratios** to futures (RFAF = PRFAP/HRSAP, DFAF = PDFAP/HDSAP). | Credit; no DA–RT difference. |
| OFF-8 | OD | Sections 4, 6 | §4.5.2(6), §6.3(7) | DAM prices are final at 1000, RT at 1600, of the 2nd Business Day; corrections reports NP4-196-M / NP4-197-M. | Not determined by the app. |
| — | ET | market usage | — | "DART" (day-ahead minus real-time, or the reverse) is common industry shorthand with **inconsistent sign conventions**. | Not an ERCOT definition in the reviewed sources; **not used** for any output. |
| — | TI | OFF-3 with §4.6 | — | Combining the DAM settlement of a quantity at DASPP with its real-time imbalance at RTSPP suggests why the two prices' difference matters to participants. | A teaching reading only. No quantity is used, so no money is computed. |
| CMP-A/B | PA | project records | — | Signed hourly price difference between the DAM SPP and an approved RT analytical summary. | Requires three separate approvals. |

**Not found:** no ERCOT-defined day-ahead/real-time price difference and no definition of DART,
in the reviewed Sections 1–13, 16, and 25.

**Inaccessible:** the 2011 DST-flag notice (GAP-1; a redirect loop, not bypassed).

## 2. Candidates

| Candidate | Formula | Sign | Classification |
|---|---|---|---|
| **CMP-A** | S_RT − P_DAM | + when the RT summary is higher | mathematically implemented; not ERCOT-defined; **approvable (1.0.0)**; review-approved: **no**; production-active: **no** (withheld) |
| **CMP-B** | P_DAM − S_RT | the exact reversal of CMP-A | the same classification as CMP-A |
| CMP-C absolute | \|S_RT − P_DAM\| | none (direction lost) | candidate only; not approvable |
| CMP-D percentage | (S_RT − P_DAM) / P_DAM × 100 | reads backwards when P_DAM < 0 | candidate only; **not approvable**. Undefined at P_DAM = 0, unstable near 0, depends on the denominator chosen, and can mislead. |

**No default sign:** the UI's record selector starts empty, and the reviewer approves one record
per sign. There is no fallback between them.

## 3. Dimensional and semantic analysis

| Item | CMP-A / CMP-B |
|---|---|
| Inputs | P_DAM ($/MWh, selected revision); S_RT ($/MWh, AGG-A or AGG-B, approved and complete) |
| Output | $/MWh: a difference of prices, **not** money |
| Zero | 0 means numerically equal. P_DAM = 0 is valid (unlike for the percentage). |
| Negative prices | handled by signed arithmetic, e.g. −5 − (−20) = +15 |
| Missing values | withheld: `dam_observation_missing` / `aggregation_incomplete` |
| Revisions | the DAM revision must equal the alignment's selected revision; RT revisions come from the aggregation snapshot |
| Aggregation | only an AGG record listed in the comparison record (fingerprint-bound) |
| Permitted reading | how far the approved RT summary lies above or below the DAM price for one hour |
| Not | a settlement amount, P&L, savings, exposure, hedge value, forecast error, trading signal, or backtest |

Nothing is multiplied by a quantity. EIA demand, ERCOT load, and synthetic quantities are never
used, and a guard test enforces this.

## 4–7. Records, approvals, activation, inputs

- **Records:** the register is in `docs/assumption-register.md` ("Comparison records").
- **Approving:** `mambo comparison approve CMP-A --version … --scope … --accept-limitations …
  --m1-version 1.0.0 --aggregations AGG-A@1.0.0,AGG-B@1.0.0 --location HB_NORTH --reviewer …
  --role … --evidence … --approved-on … --execute` (a dry run without `--execute`).

**Production requires all of the following**:
1. comparison mode selected explicitly;
2. the M1 basis;
3. an active M1 1.0.0 approval;
4. an active approval of the AGG record used, which the comparison record must accept;
5. an active approval of the chosen CMP record;
6. a supported policy;
7. no unresolved duplicates;
8. complete M1 alignment;
9. a current alignment snapshot;
10. `aggregation_approved_complete`;
11. a current aggregation snapshot whose output and revisions match;
12. a selected DAM observation with matching identity, location (HB_NORTH hub), and revision;
13. $/MWh on both sides.

**Status precedence:** unsupported_method → invalid_input → alignment_approval_missing →
aggregation_approval_missing → comparison_approval_missing → revision_unavailable →
conflicting_revisions → alignment_incomplete → stale_alignment_snapshot → aggregation_incomplete →
stale_aggregation_snapshot → dam_observation_missing → incompatible_identity → incompatible_units.
Every blocker is listed.

**Finality:** always shown as "not determined". A complete comparison is not a comparison of
final prices.

## 8. Benchmarks (hand-worked; `tests/test_comparison.py`)

| RT summary | DAM | CMP-A | CMP-B |
|---|---|---|---|
| 40 | 30 | +10 | −10 |
| 20 | 50 | −30 | +30 |
| 20 | −10 | +30 | −30 |
| −10 | 20 | −30 | +30 |
| −5 | −20 | +15 | −15 |
| 42.5 | 42.5 | 0 | 0 |
| 9001.25 | 0.75 | 9000.5 | −9000.5 |
| 0.01 | 0.02 | −0.01 | 0.01 |
| 50 (AGG-A of 20, 40, 60, 80) | 30 | +20 | −20 |
| 24.375 (fixture hour 3) | −2.50 | +26.875 | — |

The percentage candidate on (−5, −20) gives −75 %, although the RT summary is higher. This is why
it is not approvable.

## 9. Snapshots

Comparison snapshots (`<data>/comparison/snapshots.jsonl`, explicit button, append-only) record:
- the method and its scope;
- the DAM identity, revision, and document;
- the alignment and aggregation snapshot references;
- the RT interval revisions;
- the M1 and AGG fingerprints;
- all three approval states;
- the policy, formula version, and validation version (25.1);
- the input prices, output, units, sign, finality, and prohibited readings.

Any change marks a snapshot `stale_comparison_snapshot`. A later snapshot supersedes it. Nothing is
deleted.

## 10. Stage 26 prerequisites (the learner-facing comparison lesson)

| Prerequisite | Status |
|---|---|
| Active M1 1.0.0 approval | **missing** (BL-11) |
| Active AGG-A or AGG-B approval | **missing** (BL-13) |
| Active CMP-A or CMP-B approval | **missing** (BL-15) |
| Complete aligned input hours, with current alignment and aggregation snapshots | per hour; available |
| Explicit revision policy | available |
| Persistent limitations | implemented |
| Human review of the lesson content | **pending** (BL-3 pattern; BL-16) |

Still unresolved:
- official report-label definitions;
- price finality;
- price-correction feeds;
- publication and licensing;
- existing human content review.
