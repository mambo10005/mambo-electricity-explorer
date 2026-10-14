# Interval alignment: ERCOT day-ahead hours and real-time intervals (Stage 22)

Evidence record for relating NP4-190-CD day-ahead hours to NP6-905-CD real-time 15-minute
intervals at `HB_NORTH`. Decision: ADR 0019. Code: `src/mambo_explorer/ercot/alignment.py`
(evidence and candidates as data), `src/mambo_explorer/alignment_view.py` (diagnostic).
AI-authored; **not human-reviewed**. Retrieval date for every source: 2026-10-13.

## Decision

**No alignment rule is accepted.**
- **Official text supports the concept:** every real-time 15-minute Settlement Interval
  belongs to exactly one day-ahead hour (§6.6.3.3).
- **No official text defines the report labels:** what `HourEnding`, `DeliveryHour`,
  `DeliveryInterval`, `DeliveryDate`, and `DSTFlag` denote.
- **The actual files are fully consistent with candidate M1,** including three DST days. An
  example file is not a definition, though, and this stage may not infer semantics from field
  names.

So:
- the service (`alignment.align`) returns **`unsupported_semantics`** after validating its
  inputs and policies;
- a separate **candidate check** (`alignment.check_candidate("M1", …)`) shows how the labels
  would relate under M1. Its result carries `asserted = False` and no verified expected count.

Nothing in this stage computes a spread, an hourly real-time figure, a clock time, or UTC.

## 1. Official ERCOT materials (what they say)

Labels: **(a)** stated, **(b)** implied only, **(c)** not found.

| Id | Source (version) | Location | Proposition | Status | Remaining ambiguity |
|---|---|---|---|---|---|
| OFF-1 | Nodal Protocols Section 2 (Aug 1, 2026), [current protocols](https://www.ercot.com/mktrules/nprotocols/current) | Definitions | Operating Day: "The day, including hours ending 0100 to 2400, during which energy flows." Operating Hour: "A full clock hour during which energy flows." CPT: "Either Central Standard Time or Central Daylight Time, in effect in Austin, Texas." | (a) | No definition of DeliveryDate, HourEnding, DeliveryHour, DeliveryInterval, or DSTFlag (searched Sections 1–13, 16, 25). Nothing says the reports' labels are Operating Days/Hours in CPT (b). |
| OFF-2 | Section 4 (Aug 1, 2026) | §4.1(3) | DAM prices "for a one-hour Settlement Interval"; Real-Time prices "for a 15-minute Settlement Interval". | (a) | Interval lengths, not labels. |
| OFF-3 | Section 6 (Aug 28, 2026) | §6.6.3.3 variable table | DAEP/DAES: DAM quantities "for the hour that includes the 15-minute Settlement Interval", each × ¼ in the 15-minute formula. | (a) | A settlement concept; it does not say which labels name the intervals of an hour. |
| OFF-4 | Section 3 (Aug 1, 2026) | §3.5.2.1 North 345 kV Hub | Day-Ahead hub price per Operating Hour (aggregated Shift Factors); Real-Time per 15-minute Settlement Interval (time-weighted Hub Bus prices plus RTRDP, floored). | (a) | Different definitions; neither is an aggregate of the other. |
| OFF-5 | [Current Day Reports XSD](https://www.ercot.com/files/docs/2026/07/10/Current-Day-Reporting-CDR-XSD.txt) (file dated 2026-07-10, release 2026-R8) | NP4-190-CD and NP6-905-CD sequences | Field names and order equal both CSV headers. `DSTFlag`: string, documentation "DST Flag" only. | (a) names; (c) semantics | The meaning of N is not documented. |
| OFF-6 | Market notice M-E092826-01 (Sep 28, 2026; earlier 2017, 2020, 2021), [notice page](https://www.ercot.com/services/comm/mkt_notices/M-E092826-01) | DST test table | Long day hours "0100", "0200 (Normal Hour)", "0200* (Repeated Hour)", "0300"; the repeated clock hour is 1–2 AM. | (a) for the test environment | How the CSV reports encode the repeated hour is not stated (b). |
| OFF-7 | Market notices [M-A030526-01](https://www.ercot.com/services/comm/mkt_notices/M-A030526-01) (Mar 5, 2026) and M-A030625-01 (Mar 6, 2025) | Long description | The "skipped 2:00 a.m. hour"; the real-time price display mislabels an interval ending 0300 as 0200 and repeats 0315. | (a) for dashboards | Dashboards, not reports. Shows labels near a transition can be wrong in displays. |
| OFF-8 | Sections 4 and 6 | §4.5.2(6), §6.3(7) | DAM final at 1000, Real-Time at 1600, of the second Business Day after the Operating Day; Board review after notice within 30 days and PUCT authority remain. | (a) | No Business-Day calendar in the app. |
| OFF-9 | EMIL product pages: NP4-190-CD, NP6-905-CD, NP4-180-ER (13060), NP6-785-ER (13061), NP4-196-M, NP4-197-M | EMIL information | Every page: "User Guide N/A". NP4-180-ER and NP6-785-ER: public historical DAM/RTM hub and load-zone SPPs (weekly, xlsx). NP4-196-M and NP4-197-M: the price-correction reports. | (a) | The NP4-190-CD page cites rule NP4.5.3(2)(b), which the Aug 1, 2026 Section 4 does not contain. |
| OFF-10 | Section 11 (Jun 1, 2026) | §11.4.4.2 | "DST adjust … Spring DST = -4; Fall DST = 4" on counts of 15-minute intervals. | (a) for load profiling | Not the price reports. |

**Inaccessible:**
- **GAP-1:** ERCOT list notice W-A092311-05 (2011) on lists.ercot.com showed a loading stub,
  then a redirect loop. It was not bypassed. Search summaries say it described the flags as
  marking the repeated hour; that is **not** used as evidence.
- ERCOT's registered API and the MIS (login) were not used.

**Specific answers:**
- **HE hh ↔ DeliveryHour hh, intervals 1–4:** (c) at the label level; (a) only for the
  settlement concept.
- **DSTFlag:** no official meaning (c). Related evidence only: other reports in the XSD use
  `RepeatedHourFlag`; the EWS release notes record "DSTFlag changed to RepeatedHourFlag" for
  another report (b).
- **Hour 24:** belongs to the Operating Day (a). That DeliveryDate *is* the Operating Day
  is implied (b).
- **Clock:** CPT is defined (a). That these reports use CPT is implied (b).

## 2. Actual-file observations (supporting evidence only)

Bounded downloads to scratch storage (no credential, 1 s pacing, never committed):

| Request | Count |
|---|---|
| NP4-180-ER and NP6-785-ER listings | 2 |
| DAMLZHBSPP_2025 / _2026, RTMLZHBSPP_2025 / _2026 (2.0, 1.6, 14.0, 10.6 MB zipped) | 4 |
| NP4-190-CD collection (`--publish-date 2026-10-05 --publish-date 2026-10-06`) | 3 |
| **Total ercot.com requests** | **9** |

Findings:
- **ACT-1 (historical compilations):**
  - **Coverage:** HB_NORTH, 01/01/2025 to 10/10/2026, 648 DeliveryDates.
  - **Every day:** each day-ahead (Hour Ending, flag) label appears once. The real-time
    file has the same (Delivery Hour, flag) set, each with Delivery Interval 1, 2, 3, 4.
  - **Ordinary days:** 645 days with 24 hours and 96 intervals.
  - **Spring days** 03/09/2025 and 03/08/2026: 23 hours, `03:00` absent in **both**
    products, 92 intervals.
  - **Fall day** 11/02/2025: 25 hours; `02:00 N` and `02:00 Y` in **both**; 100 intervals.
  - **Flag values:** only N and Y. Day-ahead: 1 Y in 15,551 rows. Real-time: 4 Y in 62,204.
  - **Hour 24** appears under its own DeliveryDate in both.
  - **Column name:** these compilations name the flag column "Repeated Hour Flag".
- **ACT-2 (linkage):**
  - 48 NP4-190-CD hours (10/06–10/07/2026) and 31 NP6-905-CD intervals (10/05–10/06/2026)
    all exist in the compilations with equal values. Three real-time values differ only in
    trailing zeros, e.g. `29.9` vs `29.90`.
  - This links the reports' DSTFlag column to the compilations' Repeated Hour Flag **for N
    labels only**. No DST day is inside either report's public list.
- **ACT-3:** NP6-905-CD document `SPPHLZNP6905_20261013_0000` holds 10/12/2026 H24 I4. Hour
  24 stays under the earlier DeliveryDate.

## 3. Synthetic test behavior (not ERCOT behavior)

`tests/alignment_fixtures.py` uses hand-written labels on 2030 dates with `SYN-` document ids.
Candidate-check results (M1, `latest-retrieved`):

| Fixture | Status |
|---|---|
| ordinary complete hour; hour 24; spring neighbour hour; fall repeated hour N; fall repeated hour Y | aligned_complete |
| conflicting revisions (1 and 2) | aligned_complete, with the conflict and the selected revision listed |
| missing one interval; duplicate interval (same revision); blank real-time price; interval label 5 | aligned_incomplete |
| mismatched settlement point, type, or DeliveryDate | incompatible_identity |
| different DST flags; unknown day-ahead or real-time flag | ambiguous_dst |
| missing day-ahead price; bare identity with no observation | missing_day_ahead |
| no real-time intervals; spring missing hour | missing_real_time |
| `latest-known-before-cutoff`, `final` | unavailable_revision |
| malformed labels, unknown policies | invalid_input |
| rejected candidate M2; `align()` with no accepted mapping | unsupported_semantics |

## 4. Candidate mappings

| Id | Rule | Status | Supporting | Contradicting | Confidence |
|---|---|---|---|---|---|
| M1 | DA (D, `hh:00`, F) ↔ RT (D, DeliveryHour hh, DeliveryInterval 1–4, F), HB_NORTH hub ↔ HB_NORTH/HU | **partially supported, not accepted** | OFF-1, OFF-2, OFF-3, OFF-5, ACT-1, ACT-2, ACT-3 | OFF-7 (display mislabels; not the reports) | moderate |
| M2 | DA hour-ending, RT hour-beginning (RT hh ↔ DA (hh+1):00) | **rejected** | — | ACT-1: RT hours run 1–24 with no 0; both products omit label 3 on spring days. ACT-3. | low |
| M3 | DSTFlag distinguishes the repeated fall hour; never dropped or rewritten | partially supported | OFF-5, OFF-6, ACT-1, ACT-2 | — | moderate |
| M4 | Hour 24 belongs to the stated DeliveryDate | partially supported | OFF-1, ACT-1, ACT-3 | — | moderate-high |

**M1 assumptions, none officially defined:**
1. HourEnding `hh:00` and DeliveryHour `hh` name the same Operating Hour.
2. DeliveryInterval 1–4 are its four 15-minute Settlement Intervals.
3. HU is the hub type of `HB_NORTH`.
4. Equal DSTFlags denote the same occurrence of a repeated hour.

**Unsupported cases:** flags other than N/Y; other settlement points; any official label
definition. **Review:** AI-authored, not human-reviewed. Price similarity, correlation, or
extrema were **not** used for any candidate.

## 5. Daylight saving (separated by evidence type)

- **Official:**
  - A repeated hour "0200*" on the long day (test-environment notice, OFF-6).
  - A "skipped 2:00 a.m. hour" on the short day (dashboard notice, OFF-7).
  - ±4 fifteen-minute intervals in load profiling (OFF-10).
  - No definition of DSTFlag or of how the price reports encode either day.
- **Actual files (compilations):**
  - **Spring:** both products omit label 3 (`03:00` / DeliveryHour 3) and keep 1, 2, 4…24.
  - **Fall:** both repeat label 2 as N then Y.
  - **Day lengths:** 23/25 hours and 92/100 intervals.
  - **Not observed:** any NP4-190-CD/NP6-905-CD document of a DST day (neither public list
    reaches one).
- **Synthetic:** fixtures exercise a missing spring hour, both fall occurrences, mismatched
  flags, and unknown flags. They show the service's behavior, not ERCOT's.
- **Never assumed:**
  - 24 day-ahead or 96 real-time observations per day;
  - four intervals for every day-ahead hour (outside an accepted mapping);
  - DSTFlag N meaning "standard time".

## 6. Revision-selection policies

| Policy | Available | Meaning |
|---|---|---|
| `latest-retrieved` | yes | Highest stored revision: the newest value this computer retrieved, not necessarily ERCOT's newest. |
| `first-retrieved` | yes | Revision 1: the first value this computer stored. An earlier posting may have been replaced before retrieval. |
| `latest-known-before-cutoff` | **no** (`unavailable_revision`) | Needs an archive of every posting and correction with publication times. The store holds only retrieved documents. |
| `final` | **no** (`unavailable_revision`) | Finality is not determined: no Business-Day calendar, and the correction reports are not collected. |

- **Never final:** no value is called final because time passed, a collection succeeded, or
  no new revision was seen.
- **Explicit policy:** the diagnostic always names its revision policy; nothing uses an
  implicit latest-value query.
- **Correction reports:**
  - **NP4-196-M / NP4-197-M** (180-day retention) would let a future policy know that a price
    was corrected and when.
  - **Until then:** a correction is seen only if the corrected document is re-downloaded
    (revision n + 1).
  - Collecting them needs separate authorization.

## 7. Completeness rules

Three separate concepts:
1. **Dataset coverage:** which documents the stores hold (ADR 0018).
2. **Hour-level alignment completeness:** this service.
3. **Revision completeness:** whether the selected revision is the latest ERCOT published.
   Not determinable.

**Strict policy, hour level:**
- **Complete** only if every expected interval identity is present exactly once after the
  revision policy, each with a published price, and the day-ahead price is published.
- **Duplicates:** a duplicate with the same revision number is unresolved and counts as
  missing.
- **Unexpected intervals:** labels outside the expected set make the hour incomplete.
- **Never:** filling, forward-filling, interpolating, or averaging available intervals.
- **Expected count:** reported only under an accepted mapping. Today it is `not verified`; the
  candidate's 4 is shown separately.

## 8. Hourly real-time summaries: research only (not implemented)

| Method | Inputs | Dimension | Supported use | Unsupported use | Missing |
|---|---|---|---|---|---|
| Arithmetic mean of interval SPPs | the hour's verified intervals, all present | $/MWh | a descriptive statistic of posted prices | a settlement price; an hour with missing intervals | an accepted mapping |
| Duration-weighted mean | prices and each interval's duration | $/MWh | the same as the mean when durations are equal (15 min, OFF-2) | calling it energy-weighted | verified durations per label on DST days |
| Energy-weighted price (Σ p·q / Σ q) | prices plus 15-minute quantities | $/MWh | a participant's effective price | for a hub without quantities | quantities (none collected) |
| Settlement amount (Protocols §6.6.3.x, e.g. RTSPP × (DAEP × ¼ …)) | prices, cleared and metered quantities, the rules | $ | ERCOT's own settlement | any app calculation | quantities, rules review |
| Source-defined hourly real-time price | — | — | — | — | none found in the reviewed sources |

None is calculated or displayed. A numerically equal mean is not a settlement price.

## 9. Stage 23 prerequisites

| # | Prerequisite | Status |
|---|---|---|
| 1 | Same verified location (`HB_NORTH` hub ↔ `HB_NORTH`/HU) | **partially verified**: NP4-160-SG mapping and the RT file; HU not officially defined |
| 2 | Compatible operating intervals (label mapping) | **blocked by unavailable evidence**: no official label definition (OFF-5, OFF-9 "User Guide N/A"; GAP-1 inaccessible) |
| 3 | Explicit DST handling | **partially verified**: compilations observed; NP4-190-CD/NP6-905-CD DST days not observed; DSTFlag undefined |
| 4 | Verified price definitions | **verified** (OFF-4; ADRs 0016–0017) |
| 5 | Revision selection | **partially verified**: two retrieval policies; known-before-cutoff and final unavailable |
| 6 | Complete subinterval coverage | **unresolved**: expected count not verified at the label level; coverage collection exists (ADR 0018) |
| 7 | A defined aggregation | **unresolved**: research only (section 8) |
| 8 | Finality and corrections | **unresolved**: no Business-Day calendar; NP4-196-M/NP4-197-M not collected |
| 9 | Publication, license, human review | **unresolved** (PUB-01, BL-3, BL-4) |

Ways to unblock prerequisite 2 (owner's choice; none attempted):
1. Ask ERCOT (Market Information/Client Services) for the field definitions.
2. Have a named person review this record and accept M1 explicitly.
3. Observe NP4-190-CD and NP6-905-CD documents of the 2026-11-01 long day while they are
   listed (backlog BL-8), as supporting evidence.

## 10. Stage 23: M1 as a review-approved operational assumption (ADR 0020)

- **Authorization:** the owner authorized using M1 as an explicitly documented operational
  assumption, recorded in `docs/assumption-register.md` and `ercot/m1_policy.py` (version
  1.0.0).
- **Evidence status unchanged:**
  - sections 1–9 stand;
  - M1 stays *partially supported* in `CANDIDATES`;
  - `align()` still returns `unsupported_semantics`;
  - prerequisite 2 stays blocked by unavailable **official** evidence.
- **Opt-in use:** `assumed_alignment.align_with_basis` with the assumption basis. It requires
  an explicit user selection, an active recorded approval for the same version and scope, an
  in-scope location, and a supported revision policy.
- **Approval:** no attributable approval is recorded, so activation is pending.
