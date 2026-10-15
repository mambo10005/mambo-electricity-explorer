# 0014 — EIA-930 net generation by energy source (ERCO) and a generation-mix lesson

- **Status:** Accepted
- **Date:** 2026-10-12

## Context

The platform collected demand and the day-ahead forecast (EIA-930 `region-data`) and
ERCOT load. Beginners next need to see what was generating, by energy source. EIA
publishes that on a sibling route of the same survey. Three things can go wrong:
inventing route or category names, flattening signed storage values into a "mix" pie, and
calling a partial category sum the system total.

## Source review (2026-10-12)

- **API metadata, read with the local key (4 requests):** the parent listing
  `electricity/rto` names `fuel-type-data` ("Hourly Generation by Energy Source"); the
  route has facets `respondent` and `fueltype`, data column `value` ("Net Generation",
  `megawatthours`), frequency `hourly` (UTC), `startPeriod` 2019-01-01T00. The `fueltype`
  facet lists 16 ids.
- **Form EIA-930 instructions (OMB 1905-0129):** 15 energy-source codes; storage sign
  rules; OTH masking; dual-fuel rules; the by-source sum equals the total only "to the
  extent possible"; blanks, not zeros, for anomalies; 30-day resubmission of errors.
- **About the EIA-930 data:** net generation definition; hourly BA data published without
  imputation; EIA asked BAs to count pumped-storage charging as demand, and accepts
  battery-charging negatives where a BA says so. The Grid Monitor "about" page itself is
  script-rendered and returned only navigation; it was not used.
- **Local use:** the same EIA API terms as `region-data` apply (attribution, no
  endorsement, rate guidance). The route's description names only Form EIA-930 as the
  source, so no third-party content was found. **Publication** of this dataset remains
  unreviewed, as for every EIA route.

## Decision

1. **One client, a second dataset.** `EIAClient.fetch_series(route, facet, …)`
   generalizes the existing fetch; `fetch_region_data` is a thin wrapper. Redaction,
   paging, budgets, archives, checksums, Parquet, SQLite, revision lineage, writer lock,
   and recovery are reused unchanged by `generation.py`.
2. **Own store namespace** `eia930-fuel-type`, with identity
   (source, dataset, route, frequency, entity, metric `NG`, **energy_source**, period).
   Demand and forecast observations cannot be touched by a generation run.
3. **Categories are never dropped.** The fetch sends no `fueltype` filter. Codes outside
   the reviewed list are stored with the flag `unreviewed_category` and shown as such.
   More than 24 categories in one fetch is refused as out of scope.
4. **Values stay as published.** Signed values (net storage is negative), original units,
   missing stays missing, no zero-filling, interval boundaries still null.
5. **Refresh.** A third dataset `eia-generation` in `refresh.yaml`, **disabled by
   default** and optional in a plan file (a missing section means disabled). It has its
   own budget; the refresh record reports `eia_api_requests_budgeted` (demand +
   generation) so the combined load on EIA's API is visible before a run. Its success,
   coverage, and health are tracked from its own store: a demand refresh says nothing
   about generation.
6. **Calculation `generation_mix` v1.0.0.** Per-category signed sums of valid values and
   coverage; per-hour sums labeled "sum of reported categories"; an hour is complete only
   when every category seen in the window has a valid value; shares are offered only over
   complete hours with no negative value, with the denominator stated; otherwise withheld
   with a reason. No total system generation, no generation = demand, no interchange or
   losses from a difference.
7. **Views.** Explore source "EIA-930 … net generation by energy source": a stacked signed
   bar chart with a category multiselect, coverage by category, totals with completeness,
   definitions (net generation vs capacity vs fuel vs marginal), limitations. No pie chart.
8. **Lesson 13** uses the lesson engine with a `generation` exercise kind whose snapshot
   is the generation observations' fingerprint, so a revision, a new category, or a new
   window regenerates questions. Content is agent-authored and unreviewed.

## Consequences

- One balancing authority and one new route. No plant-level data, capacity factors,
  emissions, fuel prices, or dispatch reconstruction.
- Whether ERCOT reports storage charging as negative generation or inside demand is
  disclosed as unknown, not resolved.
- Publication of EIA data remains unreviewed (PUB-01).
