# 0017 — ERCOT real-time Settlement Point Price at HB_NORTH (15-minute intervals)

- **Status:** Accepted
- **Date:** 2026-10-12

## Context

Stage 19 added the day-ahead price at HB_NORTH. The real-time counterpart has different risks:
- substituting an LMP report because it also lists HB_NORTH;
- inventing UTC boundaries for 15-minute intervals;
- assuming 96 intervals per day;
- quietly overloading ercot.com, because one document covers one interval.

## Decision

1. **Product:** NP6-905-CD (report type 12301), "Settlement Point Price for each Settlement
   Point, produced from SCED LMPs every 15 minutes". These are real-time **Settlement Point
   Prices**, not SCED LMPs. Location: `HB_NORTH`, type `HU` (the North 345 kV Hub, ADR 0016).
2. **Price definition:** Protocols §3.5.2.1(4) adds the Real-Time Reliability Deployment
   Price for energy to the time-weighted Hub Bus prices and applies a −$251/MWh floor. The
   unit is $/MWh.
3. **Interval contract:**
   - **Identity:** DeliveryDate, DeliveryHour, DeliveryInterval, and DSTFlag, as written.
   - **Duration:** 15 minutes (verified).
   - **No UTC:** no clock time or UTC boundary; the day-ahead conventions are not borrowed.
   - **No assumed day length:** no fixed interval count per day.
4. **Client:** the ERCOT client accepts a FriendlyName pattern for per-interval documents.
   The archive limits for this report are small (100 KB zipped, 500 KB unzipped).
5. **Parsing:** each document must cover exactly one interval. Rows are unique by (name,
   type), as observed live. Only `HB_NORTH`/`HU` is stored, and the downloaded scope is
   recorded separately.
6. **Store:** `ercot-np6-905-cd`, distinct from the day-ahead store. Re-downloads are
   idempotent, and a changed value becomes a revision.
7. **Finality:** not determined. Protocols §6.3(7) sets 1600 on the second Business Day,
   with later Board review possible. Corrections report NP4-197-M is not collected.
8. **Refresh:** opt-in dataset `ercot-rt-spp`.
   - **Settings:** window 4, catch-up cap 8, budget 10, collection interval 1 h, freshness
     2 h by publication time.
   - **Planned from the public list, not a clock:** the collector reports intervals not yet
     published, published but not requested, and the oldest listed.
   - **Shared cap:** counts against the shared ercot.com cap, which stays **18 and is not
     raised**. With load (12) and day-ahead (6) enabled, real-time is skipped with a
     host-budget reason. Enabling all three needs an explicit cap change in a local plan.
9. **Views:** an Explore source and lesson 15.
   - **Chart:** ordinal source-label axis (`H07 I3 N`) in publication order, with a zero rule
     and a tooltip.
   - **Interval viewer:** a selectbox with a detail table.
   - **Also shown:** the all-interval table, coverage (including hours with fewer than four
     stored intervals), revision provenance, the price definition, and what the price is
     not (LMP, day-ahead, invoice).
10. **No comparison:** the day-ahead/real-time comparison prerequisites are documented in
    `docs/calculations.md` and nothing is implemented.

## Consequences

- At most 16 intervals per collection and a 7-day public list: the app holds a few hours or
  days of real-time prices, not a history.
- DST representation is still unobserved.
- No spread, settlement reconstruction, or Finance import.
- Publication and license review pending; content unreviewed.
