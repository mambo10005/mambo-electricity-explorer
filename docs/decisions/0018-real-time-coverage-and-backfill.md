# 0018 — Coverage-aware real-time price collection and bounded catch-up

- **Status:** Accepted
- **Date:** 2026-10-13

## Context

ERCOT publishes one NP6-905-CD document per 15-minute Settlement Interval (about 96 a day),
and its public list keeps about 7 days. Stage 20 (ADR 0017) collected at most 8 of the
newest uncollected documents per refresh, inside a shared ercot.com cap of 18 that the
default load (12) and day-ahead (6) datasets already use up. The collector could not keep pace
with publication. It also did not record which published documents it had left, and a
"fresh" newest interval said nothing about the intervals before it.

## Decision

1. **Capacity audit.** Every real-time refresh plan carries a `capacity` block:
   - nominal publication (about 4 per hour, about 96 per day; daylight-saving days not
     assumed);
   - the last recorded listing and the list horizon (about 7 days);
   - request costs (1 list + 1 per document; retries count);
   - documents per refresh, budget, configured interval, and the optional daily task;
   - the shared-host allocation;
   - a verdict, which never claims complete history (`complete_history_claimed: false`).

   Throughput assumes a refresh really runs at the configured interval; a computer that is
   off or asleep misses runs.
2. **Published-document inventory.** A separate SQLite file
   (`ercot-np6-905-cd/inventory.sqlite`) records every DocID seen in a listing, with:
   - first and last listing time, and whether the latest listing still shows it;
   - the last outcome, attempts, and downloads.

   Statuses: discovered, collected, failed, deferred, interval-row-absent, superseded, and
   (orthogonal) not listed. **Collected is derived from committed observations**, so the
   inventory can never claim more than the store holds. Three cases are kept apart:
   - a document not collected;
   - an interval missing inside a downloaded document (interval-row-absent; the archive is
     kept);
   - an interval with no document in any listing (not known to have been published; not
     counted).

   A document leaving the list is not proof that ERCOT or another authorized archive lost it.
3. **Explicit modes.**
   - **Snapshot** (default) takes the newest uncollected documents.
   - **Coverage** takes the **oldest** uncollected documents whose PublishDate label (the
     first ten characters of ERCOT's PublishDate as written; no conversion) is in a selected
     range, so repeated bounded runs make progress.
   - In both modes, never-requested and deferred documents come before previously failed
     ones.
   - A separate **revision-recheck** allocation re-downloads already-collected documents,
     least recently downloaded first, and never superseded ones. With an allocation of 0,
     the plan and System Health say revisions are **not monitored**.
4. **Bounded backfill.**
   - **Command:** `mambo collect --source ercot-rt-spp --coverage-from D [--coverage-to D]
     [--latest N] [--recheck K] [--dry-run]`.
   - **Bounds:** at most 16 documents plus rechecks; budget = 1 list + documents + rechecks
     + 1 retry, rejected if it exceeds the shared ercot.com cap of the plan in use.
   - **Execution:** sequential, 1 s pause.
   - **Dry run:** previews from the last recorded listing and sends nothing.
   - **Per-document failures** (404, non-ZIP, format) are recorded and the run continues.
   - **Budget exhaustion or an access refusal** stops the run, commits what was downloaded,
     and records the rest as deferred.
   - **Resume** has no duplicate observations (identity + revision rules).
   - **Reports:** remaining uncollected documents and the parts of the range that this
     access method cannot reach.
   - Nothing loops until history is downloaded.
5. **Refresh.**
   - **Settings:** `ercot-rt-spp` gains `mode` and `coverage_from`/`coverage_to`. Its
     `revision_lookback_documents` is the recheck allocation, budgeted on top of the
     catch-up.
   - **Status:** a run with document failures or an early stop is `partial` (exit 3).
   - **Allocation:** the dry run shows the explicit per-host order and allocation
     (`host_allocation`; the `--source` order, else the fixed SOURCES order; nothing is
     reordered).
   - **Warnings:** a warning appears when earlier datasets always reserve the cap first.
   - **Example plan:** `docs/examples/refresh-rt-catchup.yaml` enables only real-time
     prices in coverage mode within the unchanged cap of 18.
6. **Request accounting.** The ERCOT client counts every HTTP attempt as a request and
   splits the same attempts into list, download, and other, with retries included.
7. **Health.** Real-time System Health keeps freshness (newest publication time) apart from:
   - **Completeness:** a separate line. "Complete" is said only for the documents ERCOT
     listed in a selected coverage range, as a document count, never from an assumed 96
     intervals.
   - **Collection coverage:** range, last listing, per-status counts, backlog, not-listed
     uncollected, revision-recheck coverage, and the unavailable part of the range.
   - **Incomplete hours:** hours with fewer than four stored intervals are counted; they
     cannot support future comparisons.

## Consequences

- The default plan still cannot keep pace (real-time is opt-in and, with load and
  day-ahead enabled, never fits the cap). Closing a gap is a deliberate series of bounded
  backfill runs, each one previewed.
- The ERCOT load and day-ahead collectors are unchanged apart from request accounting.
- Still unresolved: time alignment and DST representation, finality (not computed), the
  NP4-197-M corrections feed (not collected), publication and license review, and human
  content review.
