# Source Register

Every data source must pass an access and redistribution review **before**
any data is ingested (PRD R-27). "Review pending" means nothing about that
source's terms has been verified yet. No source is connected yet.

Review columns:

- **Access**: how data is obtained (API, file download) and the credential needed.
- **Terms**: link to and summary of the terms of use, verified on a recorded date.
- **Redistribution**: whether data, or derivatives of it, may be republished
  (this decides PUB-01).
- **Revisions**: how the source publishes corrections.

| Source | Kind | Planned order | Access | Terms | Redistribution | Revisions | Review status | Connected |
|--------|------|---------------|--------|-------|----------------|-----------|---------------|-----------|
| EIA (U.S. Energy Information Administration) Open Data API v2 | Federal statistics | 1 | API key (`EIA_API_KEY`), sent as a URL query parameter | Reviewed 2026-10-11, see below | Generally permitted, with exceptions for third-party material (see below) | EIA-930: revised without per-value flags (see below) | General terms reviewed; EIA-930 `region-data` cleared for local collection/use; other routes' source notes pending; publication review pending | Yes, locally: EIA-930 ERCO D/DF (live-verified 2026-10-11) |
| ERCOT | ISO/RTO | 2 (PRD R-29) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| CAISO | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| PJM | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| MISO | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| SPP | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| NYISO | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| ISO-NE | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| Non-ISO balancing authorities | Utilities / BAs | Decided by U-7 | Review pending | Review pending | Review pending | Review pending | Pending | No |
| FERC | Regulator | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |
| NERC and regional entities | Reliability | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |
| State PUCs/PSCs | Regulators | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |
| CFTC | Regulator | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |

## Review record

### EIA Open Data API — 2026-10-11

**Pages read (all loaded on 2026-10-11).** None of them shows a "last updated"
or effective date. The terms say EIA may change them by reposting, and that
continued use counts as accepting the change, so they must be re-checked
before each connector release.

- Copyright and reuse policy: https://www.eia.gov/about/copyrights_reuse.php
- API terms of service: https://www.eia.gov/opendata/terms-of-service.php
- Registration (repeats the terms): https://www.eia.gov/opendata/register.php
- API documentation: https://www.eia.gov/opendata/documentation.php
- API FAQ: https://www.eia.gov/opendata/faqs.php

**Findings.** Quotes are verbatim from the pages above. Interpretation is
marked as such and is not legal advice.

1. **Public domain, generally.** The copyright page says: "U.S. government
   publications are in the public domain and are not subject to copyright
   protection. You may use and/or distribute any of our data, files,
   databases, reports, graphs, charts, and other information products…"
   *Interpretation:* the pages don't say outright that API responses count
   as "publications". We treat them as covered, subject to item 5.
2. **Attribution.** The copyright page says to use an acknowledgment that
   includes the publication date, e.g. "Source: U.S. Energy Information
   Administration (Oct 2008)". The API terms say: "You should use the 'EIA'
   or the 'U.S. Energy Information Administration' names in order to
   identify the source of API content." Both say "should", not "must".
   **Project rule:** always attribute anyway. Each observed value shows
   "Source: U.S. Energy Information Administration", the API route or
   series, and the retrieval date. API data has no single publication date,
   so we use the retrieval date.
3. **No implied endorsement.** The API terms say: "You may not use the EIA
   names, or the like to imply endorsement or approval of any product,
   service, or entity", and "The EIA logo is trademarked and may not be used
   without written permission". **Project rule:** no EIA logo, and no
   wording that suggests EIA endorses this platform.
4. **Access restrictions.**
   - A key is required. It goes in the URL query string, so **URLs must
     never be logged or displayed** (connector requirement).
   - Using the API counts as accepting the terms.
   - At most 5,000 rows per JSON response (300 in XML); larger results need
     paging with offset/length.
   - Exact throttling limits aren't published. The FAQ says a sustained
     rate under ~9,000 requests/hour and bursts under 5/second won't be
     throttled.
   - Trying to get around the limits can lead to temporary or permanent
     blocking. EIA may end access "at any time for any other reason in its
     sole discretion".
   - Content is provided "as is", with no warranty, and the user indemnifies
     EIA.
   - **Connector requirement:** stay well under the published guidance,
     page the requests, and back off when throttled.
5. **Protected material: not everything is unrestricted.** The copyright
   page says content "contributed or licensed by private individuals,
   companies, or organizations… may be protected by U.S. and foreign
   copyright laws". Reproducing it beyond fair use requires the copyright
   owner's written permission, and website photographs are under private
   licensing agreements. None of the pages read names a specific dataset or
   vendor. **Project rule:** before ingesting any EIA route, read that
   route's "Sources & Notes" or documentation for third-party or licensed
   content and record it here. Until then, mark the route "unreviewed" and
   leave it out of any publication (PUB-01). No electricity route has been
   checked yet.
6. **Modification and derived data.** The API terms say: "You may not modify
   or falsely represent content accessed through the API and still claim the
   source is the EIA." **Project rule:** derived values are labeled
   *derived* (PRD R-15) and never presented as unmodified EIA figures.

**Not yet reviewed:** how EIA publishes revisions (Revisions column), and
the source notes of each route we plan to use.

### EIA-930 hourly demand and forecast (`electricity/rto/region-data`) — 2026-10-11

Scope reviewed: one balancing authority (ERCOT) and two metrics: actual demand
and the day-ahead demand forecast.

**Pages read (2026-10-11).** "Page states" below means a verbatim or near-verbatim
statement on one of these pages. "Unverified" means it needs a keyed API call
that has not been made yet.

- API v2 documentation: https://www.eia.gov/opendata/documentation.php
- Hourly Electric Grid Monitor, about the data: https://www.eia.gov/electricity/gridmonitor/about
- Form EIA-930 instructions (OMB 1905-0129): https://www.eia.gov/survey/form/eia_930/instructions.pdf
- EIA-930 reference tables ("updated 10/11/2026"): https://www.eia.gov/electricity/930-content/EIA930_Reference_Tables.xlsx
- API browser for the route: https://www.eia.gov/opendata/browser/electricity/rto/region-data
- An unauthenticated request to `https://api.eia.gov/v2/electricity/rto/region-data/`
  returned **HTTP 403 `API_KEY_MISSING`**. Metadata and facet lists need a key.

| Item | Finding | Status |
|---|---|---|
| Route | `electricity/rto/region-data`, "Hourly Demand, Demand Forecast, Generation, and Interchange". Facets `respondent`, `type`. Data from 2019-01-01T00. | Seen in EIA's own API-browser traffic. Not fetched by us. |
| Entity | `ERCO` = "Electric Reliability Council of Texas, Inc." (BAs sheet of the reference tables; also on the about page). | Verified from official reference tables. Live facet check pending (`mambo sources --remote`). |
| Metrics | `D` = Demand ("actual demand"), `DF` = Day-ahead demand forecast ("should always be positive"). | Form instructions and grid monitor. Live facet check pending. |
| Units | `megawatthours`; aggregation SUM. "BAs report all data as hourly integrated values … time-weighted hourly averaged values." | Hourly average MW equals MWh over that hour. |
| Interval | Frequency `hourly` = "one data point for each hour in UTC time", format `YYYY-MM-DD"T"HH24`. EIA-930 uses "the hour ending time reporting convention". | **Hour-ending is not stated for the API `period` field.** The app does not derive interval start/end (columns stay null) until a keyed response confirms it. |
| start/end | "only return data after a specific point … end … the latest date". Hourly inclusivity not stated. | The collector validates that every row falls inside the window, and the Explore page counts absent hours. |
| Paging | At most 5,000 rows per JSON response. `offset`/`length` paging. `total` reported as a string. Sort syntax `sort[0][column]`. | Implemented with deterministic sort (period, respondent, type). Truncation fails the run. |
| Values | Returned as strings since API v2.1.6. | Parsed without imputation; `value_raw` kept. |
| Missing values | Not documented for the API. "We publish hourly BA data exactly as reported without imputation." | **Live 2026-10-11: missing hours appear as absent rows** (24 DF hours absent, 0 nulls). Null and empty values are still handled and flagged. The Explore page counts absent hours. |
| Imputation | EIA imputes only in U.S./regional and daily aggregates, not on hourly BA values. | No imputation in this app. |
| Revisions | Demand is collected hourly "and again at 7:00 a.m. the next day … values may or not be the same". Revisions are resubmitted within 3 days (expected) or 30 days (errors > 10 MWh). No per-value publication time or preliminary/final flag found. | Revision history kept. Default 2-day lookback. `publication_time_utc` stays null. |
| Field names | Docs example: `response.{total,dateFormat,frequency,data}` plus a `request` echo whose example `params` include `api_key`. | **Live-verified 2026-10-11:** rows have `period`, `respondent`, `respondent-name`, `type`, `type-name`, `value`, `value-units`. For this route the `request.params` echo had **no `api_key`**, but archives stay redacted in case that changes. |
| Caveats | The day-ahead forecast is "generated in the normal course of business" by the BA. Daylight-saving transition days "are often misreported" (ERCO reports in Central time). "We advise caution when using these data." | Shown as limitations in the app. |
| Dataset terms | "We collect the data from the electricity balancing authorities." "All information reported on Form EIA-930 is public information and may be publicly released in company identifiable form." No dataset-specific copyright or third-party notice found. | See clearance below. |

**Local collection and use: CLEARED** for this route, entity, and these two
metrics. The basis is the general EIA terms (above), the EIA-930 public-information
statement, and no third-party notice. Conditions:
- attribute EIA
- no endorsement claims
- keep under the published rate guidance
- never log or display the key-bearing URL

**Public redistribution: NOT YET REVIEWED.** The terms are permissive, but
publishing (PUB-01) also needs:
- an attribution format decided for derived views
- a recheck of the terms on the publication date (they carry no effective date)
- a decision on publishing archives that contain EIA's request echo

Nothing is published.

**Live verification (2026-10-11, owner-provided key, 5 requests in total):**

- `mambo sources --remote` (3 requests) confirmed:
  - route `region-data`
  - frequency `hourly`
  - `ERCO` = "Electric Reliability Council of Texas, Inc."
  - `D` = "Demand", `DF` = "Day-ahead demand forecast"
- `mambo collect` (1 request) for UTC days 2026-10-04..10, plus a 2-day
  lookback (periods 2026-10-02T00..2026-10-10T23):
  - 408 rows: `D` 216/216, `DF` 192/216
  - `DF` absent for `2026-10-05T06`..`2026-10-06T05`
  - values were strings, units all `megawatthours`, `apiVersion` 2.1.14
  - no warnings; no key in the response
- All 408 stored observations matched the archived response exactly
  (`value_raw` and unit). The archive sha256 matches the catalog.
- An immediate repeat collection (1 request) found 0 new, 0 revised, and 408
  unchanged rows. `mambo validate`: ok.
- **Period convention still not stated by the API.** The absent forecast
  block is exactly one Central-time day *if* periods are hour-ending
  (06 UTC = hour ending 01:00 CDT). That is consistent with the EIA-930
  documentation but is not an explicit API statement, so interval boundaries
  are still not derived.
- No revisions observed yet. Detecting them needs re-collection over the
  days when EIA's documented resubmissions happen (up to 3 or 30 days later).
