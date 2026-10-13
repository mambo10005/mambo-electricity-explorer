# 0016 — First actual price series: ERCOT DAM Settlement Point Price at HB_NORTH

- **Status:** Accepted
- **Date:** 2026-10-12

## Context

Every price in the app so far was synthetic or modeled. Beginners need to read one actual
wholesale price. The risks are:
- guessing report or location codes;
- borrowing the load report's time conventions;
- calling a downloaded price final;
- quietly piping actual prices into the synthetic finance calculators.

## Decision

1. **Dataset:** ERCOT NP4-190-CD "DAM Settlement Point Prices" (report type 12331),
   discovered from ERCOT's product pages and live listing, one location: `HB_NORTH`. The
   code is tied to Protocols §3.5.2.1 "North 345 kV Hub" by evidence: all 75 hub buses ERCOT's
   settlement-point list (NP4-160-SG) assigns to `HB_NORTH` appear in that section's table.
2. **One access method:** the existing ercot.com public listing and download. The client
   now takes a `Report` (type id, CSV friendly name, archive limits). This report's limits
   are about 600 KB zipped and 4 MB unzipped; the load report's limits are unchanged.
3. **Contract** (`ercot/prices.py`, `docs/datasets/ercot-np4-190-cd.md`):
   - **Unit:** $/MWh, from the Protocols (the file states none).
   - **Labels:** DeliveryDate, HourEnding, and DSTFlag kept raw, with no UTC mapping.
   - **Identity:** source, dataset, market stage, location, DeliveryDate, HourEnding,
     DSTFlag.
   - **Values:** signed values kept; missing stays missing.
   - **Scope:** downloaded and stored scope recorded separately.
   - **Revisions:** a repost with a changed value becomes a revision.
   - **Finality:** not determined, because Business Days are not computed and the
     corrections report is not collected.
4. **Refresh:** a fourth dataset `ercot-dam-spp`.
   - **Opt-in:** disabled by default and optional in plan files.
   - **Planning:** from stored DeliveryDates. The newest expected date is tomorrow, since
     the DAM posts the day before.
   - **Shared host cap:** a new `hosts` section caps requests per refresh per host
     (`ercot.com: 18` by default, which equals load 12 + prices 6). A dataset that would
     exceed the cap is skipped with a reason, and a dataset budget above its host cap is
     rejected. Dry runs show `host_requests_budgeted`.
5. **Views:** an Explore source and lesson 14 "Reading an actual day-ahead electricity
   price".
   - **Chart:** ordinal source-label axis (HourEnding + DSTFlag) with a zero rule; the
     tooltip and table use the same labels.
   - **Also shown:** coverage, publication and retrieval times, a revision provenance table,
     and definitions separating this price from bus LMPs, modeled prices, retail tariffs,
     forward prices, and real-time prices.
   - **Exercises:** keyed on a fingerprint of the day's labels, revisions, and raw values.
6. **Finance boundary:** actual prices are **not** injected into any calculator. A future
   explicit import must name the market stage, location, units, an interval-compatibility
   check, the revision reference, and observation provenance. A day-ahead price must never
   stand in for a real-time price or imply a contract fixed price (`docs/calculations.md`).

## Consequences

- One hub and one market stage. No real-time prices, DART spread, settlement
  reconstruction, forward curve, congestion attribution, or trading.
- No join with EIA demand or generation until interval mapping is verified.
- DST representation in this report is unobserved; at most 25 rows per day are accepted
  and nothing is merged.
- Publication and license decisions stay pending, as for all ERCOT data.
