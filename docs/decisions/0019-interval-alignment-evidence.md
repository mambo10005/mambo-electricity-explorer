# 0019 — Evidence-based alignment of ERCOT day-ahead hours and real-time intervals

- **Status:** Accepted
- **Date:** 2026-10-13

## Context

A future day-ahead/real-time comparison (Stage 23) needs to know which NP6-905-CD real-time
intervals belong to an NP4-190-CD day-ahead hour. Both reports carry source-native labels and
no time zone:
- day-ahead: DeliveryDate, HourEnding `hh:00`, DSTFlag;
- real-time: DeliveryDate, DeliveryHour, DeliveryInterval, DSTFlag.

The obvious rule (hour hh ↔ hour hh, intervals 1–4) had never been checked against
authoritative sources. Calendar DST days had never been observed in either report.

## Decision

1. **Evidence before rules.** Every source is recorded in `ercot/alignment.py` (`EVIDENCE`)
   and `docs/interval-alignment.md`, classified as official, actual-file, or inaccessible.
   Synthetic fixtures are never evidence.
2. **No mapping is accepted.**
   - **Official:** ERCOT's Protocols define the concept: each 15-minute Settlement Interval
     belongs to one day-ahead hour (§6.6.3.3, × ¼).
   - **Not official:** no ERCOT material defines the reports' labels. The XSD documents
     DSTFlag only as "DST Flag", and the product pages list no user guide.
   - **Supporting only:** historical ERCOT compilations (NP4-180-ER/NP6-785-ER, 648 days
     including three DST days) are fully consistent with candidate M1. That is supporting
     evidence, not a definition.
   - **Candidate statuses:** M1 is *partially supported*; M2 (hour-beginning real-time) is
     *rejected* by the actual files.
3. **Service.** `align()` validates inputs and policies, then returns
   `unsupported_semantics` while no candidate is accepted. `check_candidate()` evaluates a
   partially supported candidate for diagnosis only:
   - `asserted = False`;
   - no verified expected count;
   - rejected candidates are never evaluated.
   Results are one of nine statuses and carry source-native identities, revision
   references, DST evidence, and limitations. They never include a price value.
4. **Revision policies are explicit.** Two are available: `latest-retrieved` and
   `first-retrieved`. Two are `unavailable_revision`: `latest-known-before-cutoff` (needs an
   archive of every posting) and `final` (finality not determined).
5. **Completeness is per hour and strict.** It is kept apart from dataset coverage (ADR
   0018) and from revision completeness. Duplicates must be resolved by the policy first; an
   unresolved duplicate counts as missing. Nothing is filled or averaged.
6. **Diagnostic page.** Explore → "Diagnostic: ERCOT day-ahead hour and real-time interval
   labels" reads labels and price presence only, from both stores, and states that no DART
   spread is calculated. The asserted result and the labelled candidate check are shown
   separately, with the evidence record.
7. **Guards.** Tests fail if production code adds:
   - a DART/spread output;
   - an SQL aggregate of prices;
   - clock-time or UTC handling in the alignment modules;
   - a literal four-interval rule outside a candidate's evidence-backed `expected_intervals`.
8. **Unchanged:** stored identities, collectors, and request caps. The investigation used 9
   bounded ercot.com requests into scratch storage.

## Consequences

- **Stage 23 is blocked** on prerequisite 2 (label mapping) until one of the following:
  - official definitions are obtained;
  - a named person reviews and accepts M1;
  - or the owner decides otherwise.
  Everything else is classified in `docs/interval-alignment.md` §9.
- **Accepting a mapping later** is a one-line status change in `CANDIDATES`. The guards and
  tests then exercise the asserted path.
- **Hourly real-time summaries** remain research (§8); none is calculated.

## Alternatives considered

- **Accept M1 on the actual-file evidence:** rejected. The stage forbids treating example
  files as a universal rule without an official definition.
- **Infer from price similarity:** rejected. Prices prove nothing about labels.
- **Map labels to clock times or UTC:** rejected. There is no authoritative label definition,
  and the ambiguity fields are missing.
