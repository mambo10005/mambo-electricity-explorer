# 0013 — Bounded local refresh orchestration and a truthful System Health page

- **Status:** Accepted
- **Date:** 2026-10-12

## Context

The EIA-930 and ERCOT NP6-345-CD collectors exist (ADRs 0004 and 0005). Each is run by hand
with `mambo collect`. PRD R-13 asks for continuously updated data, and open question U-6
asks how collection is scheduled locally.

Two failure modes need guarding against:
- a scheduler that quietly turns into an unbounded crawler;
- a status page that calls data "fresh" because a request recently succeeded.

## Decision

1. **One orchestration layer, no second ingestion path.** `refresh.py` plans an EIA
   `collect.Plan` or an ERCOT `Selection` and calls the existing `collect()` functions.
   - Their writer locks, atomic writes, revision numbering, idempotence, and
     `validate`-based recovery are unchanged.
   - Sources run sequentially, under a refresh lock (`<data>/refresh/.refresh.lock`). A
     stale lock is reported, never removed automatically.
2. **Validated plan** (`content/refresh.yaml`, or `--config` / `MAMBO_REFRESH_CONFIG`;
   `refresh_config.py`).
   - **Settings:** enabled sources, initial window, revision lookback, catch-up cap,
     request budget, freshness threshold, and log retention.
   - **Bounds:** every value is bounded by the collectors' own per-run maxima (31 EIA days
     including lookback; 7 ERCOT documents).
   - **Cadence vs schedule:** the source's publication cadence (sourced text) is stored
     apart from the owner's collection interval.
   - **No credentials:** credential-like keys are rejected.
3. **Catch-up from committed runs, never from absent rows.**
   - **EIA:** continues after the last committed UTC day, re-requests a lookback, and
     caps new days per refresh, naming any days it skips.
   - **ERCOT:** counts OperDays by calendar label (no conversion to UTC), re-downloads a
     lookback document to detect reposts, caps the documents, and flags anything older
     than the about-31-day public list as outside available history.
   - **Findings** are labeled never-collected, missed-collection (from run times only),
     missing-observations (reported, never filled), source-unavailable,
     outside-available-history, beyond-catch-up-limit, revision-lookback, or no new
     period expected.
4. **Partial success is its own result.**
   - **Isolation:** each source has its own budget and error capture. A failure is
     recorded, and the next source still runs.
   - **Overall result:** complete (exit 0), partial (exit 3), failed (exit 2), or
     nothing-to-do (exit 0). A second refresh while one is running exits 2.
   - **Logs:** diagnostics are redacted with the EIA redactor before printing and before
     the JSON log is written. Logs are pruned by age and count, and only this app's own
     log files are deleted.
5. **System Health is read-only** (`health.py`, `system_health.py`). It never collects,
   repairs, or writes.
   - **Shown separately:** last attempted vs last successful collection; latest
     observation label (as the source writes it); publication time (only when the source
     gives one: ERCOT yes, EIA no); and retrieval time.
   - **Freshness:** taken from the observation label (EIA UTC labels, ±1 h because the
     label convention is unconfirmed) or the source's publication time (ERCOT). It is
     **never** taken from request time. It is **unknown** when stored observations
     cannot be read.
   - **Unchanged data:** a successful run with no new rows is not a failure.
   - **Failures before collection:** the newest refresh-log result per source is shown
     too. A refresh can fail before a collector starts (for example, no EIA key), which
     leaves no catalog run.
   - **Content status:** for lessons and responsibility records, the page shows content
     version, source-review date, human-review status, and "Automatic change monitoring:
     none". It states plainly that regulatory content is an unmaintained snapshot.
6. **Optional Windows task** (`scripts/refresh-task.ps1`).
   - **Default is Preview:** it prints the XML and has Task Scheduler parse it without
     registering. Register, Inspect, Disable, and Remove touch only
     `\mambo-electricity-explorer\refresh`.
   - **Settings:** current user, interactive token (no stored password), least privilege,
     30-minute limit, IgnoreNew, network required, no wake, power settings untouched,
     and missed starts run when available (opt-out).
   - **Command:** absolute interpreter path and explicit working directory; no
     credentials in arguments or XML.
   - **Not registered:** no task was registered in this milestone.

## Consequences

- "Continuously updated" means "as often as the owner runs a refresh while the computer
  and network are available". It is never real-time.
- EIA history beyond the catch-up cap needs a deliberate manual `mambo collect`. ERCOT
  documents older than the public list are not available through the access method this
  app implements (the public report listing); this says nothing about other ERCOT channels.
- No new datasets, cloud services, regulatory crawler, or automatic content approval.
  Compliance content stays a dated snapshot (ADR 0012).
