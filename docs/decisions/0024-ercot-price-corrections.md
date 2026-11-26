# 0024 — ERCOT SPP price corrections at HB_NORTH (NP4-196-M, NP4-197-M)

- **Status:** Accepted
- **Date:** 2026-11-26

## Context

Backlog BL-10: the day-ahead (ADR 0016) and real-time (ADR 0017) price stores say corrections
are "not collected". Any correction-aware or "known before cutoff" revision policy, and any
finality claim, needs the correction reports first. The owner authorized collection and the
full connector on 2026-11-26. Review and a bounded live sample (4 requests) are in
`docs/source-register.md` and `docs/datasets/ercot-np4-196-m.md` / `ercot-np4-197-m.md`.

Risks:
- each listing mixes many document kinds (LMP, ancillary, shadow price), so a loose match
  downloads the wrong report;
- a document lists only corrected rows, so absence could be mistaken for "no correction";
- a correction could be written into the price series or treated as making a price final;
- the hour field is `DeliveryHour`, not NP4-190-CD's `HourEnding`.

## Decision

1. **Two sources**, `ercot-dam-corrections` (NP4-196-M, type 13044, kind `DAM_SPP`) and
   `ercot-rt-corrections` (NP4-197-M, type 13045, kind `RTM_SPP`), one module
   (`ercot/corrections.py`) with a `Kind` per report.
2. **Exact document match:** the listing is filtered by a full-match FriendlyName pattern for
   the one SPP `_csv` family. An empty match fails the run (naming may have changed) instead of
   committing nothing.
3. **Scope:** `HB_NORTH` only; the downloaded scope is recorded. A document without the hub is
   valid and recorded with zero stored rows.
4. **Own stores:** `ercot-np4-196-m` and `ercot-np4-197-m`. Never merged into the price stores.
5. **Identity:** the correction event: DeliveryDate, DeliveryHour, DeliveryInterval (real-time
   only), DSTFlag, PriceCorrectionTime, all raw. A later correction of the same interval is a
   separate observation. A re-posted event with changed original or corrected price is a
   revision.
6. **Raw values and labels:** original and corrected prices are kept as written beside parsed
   numbers (blank is missing, never zero). No unit is in the files, so $/MWh is recorded with
   the Protocols basis. No time zone is stated, so nothing is converted to UTC, and the labels
   are never mapped to another report's labels.
7. **No application of corrections:** stored prices, calculators, comparison, aggregation, and
   alignment are unchanged. A correction never makes a price final; absence is not proof of no
   correction.
8. **Opt-in only:** collected by `mambo collect` on request; not in `refresh`, System Health,
   or any page. Budget: 1 list request + one download per document, at most 3 documents per
   run, 3 MB archive limit, shared 1 s pacing.

## Consequences

- Revision-policy prerequisite 5 and finality prerequisite 8 in `docs/interval-alignment.md`
  remain open: the data now exists locally but no policy uses it and no Business-Day calendar
  exists.
- Coverage is partial by design (a few documents per run; no inventory, no backfill).
- DST days are not observed in either report.
- Publication and license review pending, as for the other ERCOT reports.
