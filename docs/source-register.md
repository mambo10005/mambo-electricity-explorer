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
| ERCOT — NP6-345-CD Actual System Load by Weather Zone | ISO/RTO | 2 (PRD R-29) | ercot.com public listing + download, no login (ERCOT Public API needs registration; not used) | Reviewed 2026-10-11, see below | Terms permit raw-data reuse in compilations, charts, and analyses; **project publication review pending** | No correction policy found; reposts handled as revisions | Cleared for local collection/use; publication review pending | Yes, locally (live-verified 2026-10-11) |
| CAISO | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| PJM | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| MISO | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| SPP | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| NYISO | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| ISO-NE | ISO/RTO | After ERCOT (U-3) | Review pending | Review pending | Review pending | Review pending | Data review pending. Three public pages are cited (paraphrased) in lesson 8; see "Reference documents" | No (no data ingested) |
| Non-ISO balancing authorities | Utilities / BAs | Decided by U-7 | Review pending | Review pending | Review pending | Review pending | Pending | No |
| FERC | Regulator | After operators | Review pending | Review pending | Review pending | Review pending | Data review pending. Glossary cited (paraphrased) in lesson 9; see "Reference documents". On 2026-10-11 (Stage 13) the glossary page showed a human-verification page and was not re-checked | No (no data ingested) |
| NERC and regional entities | Reliability | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |
| State PUCs/PSCs | Regulators | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |
| CFTC | Regulator | After operators | Review pending | Review pending | Review pending | Review pending | Pending. Glossary not checked: the site showed a human-verification page (2026-10-11) | No |

## Reference documents cited in lessons (not data sources)

These pages are cited and **paraphrased** in lesson text. Nothing is downloaded, stored,
or redistributed from them, and no data is ingested. Short paraphrases with links are the
only use. A data-source review (terms, redistribution) is still required before any data
from these organizations is collected.

| Reference | Used in | What it supports | Checked |
|---|---|---|---|
| ISO New England, [Day-Ahead and Real-Time Energy Markets](https://www.iso-ne.com/markets-operations/markets/da-rt-energy-markets) | Lesson 8, `settlement.py` | Day-ahead commitments settled; real-time settles differences from them at the RT LMP; "multi-settlement" | 2026-10-11 |
| ISO New England, [bill item: Day-Ahead (DA) Energy](https://www.iso-ne.com/markets-operations/settlements/understand-bill/item-descriptions/da-energy) | Lesson 8 | Net cleared quantity per location, hourly, at the DA LMP; ISO-NE's invoice nets credits and charges with its own sign convention | 2026-10-11 |
| ISO New England, [bill item: Real-Time (RT) Energy](https://www.iso-ne.com/markets-operations/settlements/understand-bill/item-descriptions/rt-energy) | Lesson 8 | Net deviation per location at the RT LMP, five-minute intervals; invoices include other allocations | 2026-10-11 |
| PJM, [Manual 11, Revision 137](https://www.pjm.com/-/media/DotCom/documents/manuals/m11.pdf) | Lesson 6 | PJM LMP = system energy price + congestion price + loss price (Section 1 overview) | 2026-10-11 |
| FERC, [market-assessment glossary](https://www.ferc.gov/industries-data/market-assessments/overview/glossary) | Lesson 9, `basis.py` | Basis (price difference between otherwise identical products in different markets), fixed-for-floating swaps, hedging. Natural-gas context; concepts only | 2026-10-11 (browser) |
| EIA, [Today in Energy: Texas Heat Wave, August 2011](https://www.eia.gov/todayinenergy/detail.php?id=3010) (2011-09-09) | Lesson 10, `shape.py` | A 16-hour weekday on-peak block (ERCOT, 2011) in which afternoon super-peak hours traded far above morning hours, and block prices averaged high and low hours. Context only; no numbers used | 2026-10-11 |
| GovInfo, [16 U.S.C. 824 (FPA §201)](https://www.govinfo.gov/content/pkg/USCODE-2023-title16/html/USCODE-2023-title16-chap12-subchapII-sec824.htm) and [16 U.S.C. 824o (FPA §215)](https://www.govinfo.gov/content/pkg/USCODE-2023-title16/html/USCODE-2023-title16-chap12-subchapII-sec824o.htm), U.S. Code 2023 ed. | Lesson 11, Compliance explorer | Wholesale sales and interstate transmission (§201(b)(1), (d)); ERO certification, standards approval, penalties review, no construction authority, Alaska/Hawaii exclusion (§215) | 2026-10-11 |
| GovInfo, [7 U.S.C. 2 (CEA §2)](https://www.govinfo.gov/content/pkg/USCODE-2023-title7/html/USCODE-2023-title7-chap1-sec2.htm), U.S. Code 2023 ed. | Lesson 11, Compliance explorer | CFTC exclusive jurisdiction over swaps and futures (a)(1)(A); FERC/state savings clause and CFTC's retained authority (a)(1)(I) | 2026-10-11 |
| eCFR, [18 CFR 40.1](https://www.ecfr.gov/current/title-18/chapter-I/subchapter-B/part-40/section-40.1) (text as of 2026-10-01) | Lessons 11–12, Compliance explorer | Reliability rules apply to users, owners, and operators of the bulk-power system (other than Alaska or Hawaii); each standard identifies its subset | 2026-10-11 |
| Federal Register via GovInfo: [2025-18396](https://www.govinfo.gov/content/pkg/FR-2025-09-23/html/2025-18396.htm) (CIP-003-11 proposal), [2026-05711](https://www.govinfo.gov/content/pkg/FR-2026-03-24/html/2026-05711.htm) (Order No. 918), [2023-18729](https://www.govinfo.gov/content/pkg/FR-2023-08-30/html/2023-18729.htm) (DOE-417 notice) | Lessons 11–12, Compliance explorer | Proposal vs final rule (effective 2026-05-26; the standard's own date follows its implementation plan, not read); DOE-417 purpose and proposed changes (respondents and mandatory status not stated) | 2026-10-11 (also FR API metadata) |
| CPUC, [About](https://www.cpuc.ca.gov/about-cpuc) and [Resource Adequacy](https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/electric-power-procurement/resource-adequacy-homepage) | Lesson 11, Compliance explorer | California-specific: mission (safe, reliable service at reasonable rates); RA covers CPUC-jurisdictional load-serving entities; CAISO studies inform local and flexible RA | 2026-10-11 |
| ERCOT, [About](https://www.ercot.com/about) | Lesson 11, Compliance explorer | ERCOT's own description: schedules power, settles the competitive wholesale market, administers retail switching; oversight by the PUCT and the Texas Legislature. No FERC/NERC statement | 2026-10-11 |
| ISO New England, [Tariff index](https://www.iso-ne.com/participate/rules-procedures/tariff) | Lesson 11, Compliance explorer | Tariff sections; Market Rule 1 governs New England wholesale markets. Index page only | 2026-10-11 |
| EIA, [Form EIA-930 instructions](https://www.eia.gov/survey/form/eia_930/instructions.pdf) | Lesson 1 | "Hourly integrated values in megawatts by hour ending time" (General Instructions, p. 3) | 2026-10-11 |

**Compliance sources not readable on 2026-10-11** (not bypassed; content narrowed, ADR 0012):
- ferc.gov returned HTTP 403;
- nerc.com and texasre.org returned no readable content;
- cftc.gov showed a human-verification page;
- DOE OE-417 pages returned a missing page or a DNS failure;
- puc.texas.gov returned HTTP 402;
- federalregister.gov document pages redirected to a verification page (GovInfo copies and the FR API were used instead).

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

**Not yet reviewed:** how EIA publishes revisions (Revisions column) beyond the
resubmission rules in the form instructions, and the source notes of routes not yet used.

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

### ERCOT NP6-345-CD Actual System Load by Weather Zone — 2026-10-11

**Pages read (2026-10-11, no login).**

- Product page / EMIL: https://www.ercot.com/mp/data-products/data-product-details?id=NP6-345-CD
  (EMIL last updated 2-24-2026)
- Public report list: https://www.ercot.com/misapp/GetReports.do?reportTypeId=13101
- Terms of Use: https://www.ercot.com/help/terms (last updated 07/20/2023)
- API / Data Portal terms: https://www.ercot.com/help/terms/data-portal (no date shown)
- Public API docs:
  https://developer.ercot.com/applications/pubapi/user-guide/registration-and-authentication/
  and https://developer.ercot.com/applications/pubapi/known-limits/
- CDR XSD: https://www.ercot.com/files/docs/2026/07/10/Current-Day-Reporting-CDR-XSD.txt
- Nodal Protocols §6.3.2(4) (April 1, 2026)

Failed: developer.ercot.com `/pubapi/user-guide/` and `/pubapi/faq/` (404);
lists.ercot.com DST notice (302).

**Access.**
- The Public API requires an ERCOT API Explorer account, an
  `Ocp-Apim-Subscription-Key`, and an Azure B2C ID token. Unauthenticated requests
  return 401.
- The API terms say: "Users must create an account to access the ERCOT API… Accounts
  registered by 'bots' or other automated methods are not permitted."
- **No account was created and no terms were accepted.**
- The ercot.com public listing and download work without login. These URLs are the
  ones ERCOT's own product page uses; they are not documented as a developer API
  (ADR 0005).

**Terms (Terms of Use, last updated 07/20/2023). Quotes, not legal advice.**
- §5: "The publicly available contents of this website may be used, reproduced, and
  redistributed, provided that the contents are not modified and that you maintain
  all copyright and other notices… raw data provided in public portions of this
  website may be used, reproduced, and redistributed in compilations, charts, and
  analyses without maintaining such notices."
- §6: "Use of this website in a manner that negatively affects the performance of this
  website or other ERCOT systems is prohibited."
- §2: content "AS IS", no warranties.
- §9: no use of the ERCOT logo or name without permission.
- §10: the terms may change without notice.

**Local collection and use: CLEARED** for this report via the public download.
Conditions:
- low volume: at most 7 documents and 10 requests per run, with a 1 s pause
- no implied endorsement, and no ERCOT logo
- recheck the terms before any change in collection pattern

**Public redistribution: NOT REVIEWED FOR THIS PROJECT.** §5 is permissive for raw data
in compilations, charts, and analyses, but publication (PUB-01) still needs the owner's
review, an attribution style, and a recheck of the terms on the publication date. Public
accessibility is not treated as permission. **No ERCOT file is committed to the
repository.** The test fixtures are synthetic.

**Dataset facts and gaps:** see `docs/datasets/ercot-np6-345-cd.md`.
- Unverified: units, time zone of the labels, DST representation, and the TOTAL
  definition.
- Posting: daily for the previous OperDay ("no later than 0600"). The live listing
  showed PublishDate 05:50 −05:00.

**Live verification (2026-10-11, no credential, 1 + 4 + 4 requests):**
- Listing: 32 public CSV documents, published 2026-09-10 to 2026-10-11.
- `collect --latest 3`: documents 1284301100, 1284697188, and 1285079459 (OperDays
  10/08, 10/09, and 10/10/2026), each 24 rows.
  - 648 values; all `DSTFlag = N`; 0 null values
  - max |zone sum − TOTAL| = 0.02
- Every stored value matches the archived ZIP CSVs (648/648). The archive sha256 values
  match the catalog.
- The repeat collection was idempotent: 648 unchanged, 0 new, 0 revised.
- `validate`: ok.
- The EIA store was unchanged: identical catalog sha256 and the same counts before
  and after.

### EIA-930 hourly net generation by energy source (`electricity/rto/fuel-type-data`) — 2026-10-12

Scope reviewed: one balancing authority (ERCO) and one measure, net generation by energy
source. Contract: `docs/datasets/eia930-fuel-type-data.md`. Decision: ADR 0014.

**Pages and calls (2026-10-12).**
- Live API metadata with the local key (4 requests, URLs never shown): parent listing
  `electricity/rto`, route metadata, facet `fueltype`, facet `respondent`.
- Form EIA-930 instructions (OMB 1905-0129, expiration 07/31/2029), text extracted locally.
- "About the EIA-930 data": https://www.eia.gov/electricity/930-content/about.html
- The Grid Monitor "about" page returned only navigation (script-rendered); not used.

| Item | Finding | Status |
|---|---|---|
| Route | `fuel-type-data`, "Hourly Generation by Energy Source"; facets `respondent`, `fueltype`; `value` alias "Net Generation", `megawatthours`, SUM; `hourly` = UTC | Live metadata |
| Codes | 15 in the instructions (COL, NG, NUC, OIL, WAT, PS, SUN, SNB, WND, WNB, BAT, OES, GEO, OTH, UNK) plus `UES` in the API facet (undefined in the instructions read) | Instructions; live facet |
| Sign | Net storage reported as negative net generation per category; combined hydro may be negative; About page: EIA asked BAs to report pumped-storage charging as demand instead, and accepts battery-charging negatives where a BA says so | **ERCOT's convention not stated per BA**; values kept signed |
| Totals | By-source sum equals the reported total "to the extent possible"; the SYS total is on `region-data` and is not collected | No total shown |
| Missing | Anomalies left blank, "Do not report zeros … unless they are valid zeros" | Absent/null kept; never zero |
| Imputation | Hourly BA data published "exactly as reported without imputation" | None applied |
| Revisions | Errors > 10 MWh resubmitted within 30 days; demand collected twice | Lineage kept; lookback |
| History | API `startPeriod` 2019-01-01T00; by-source data from 2018-07-01 in EIA files | Not bulk-collected |
| Third-party content | Route description names only Form EIA-930; no vendor or license notice found | None found |

**Local collection and use: CLEARED** on the same basis as `region-data` (general EIA
terms, EIA-930 public-information statement, no third-party notice; attribution, no
endorsement, rate guidance). This review does not extend the demand review by
assumption: the route's own metadata and description were read.

**Public redistribution: NOT REVIEWED** (PUB-01), as for every EIA route.

**Live verification (2026-10-12, scratch storage, 1 + 1 + 3 requests):** 232 rows (8 categories × 29 hours), all matching the archived response; repeat idempotent; `validate` ok. Details in `docs/datasets/eia930-fuel-type-data.md`.

### EIA vs. ERCOT: unresolved differences (no join, no reconciliation yet)

| Aspect | EIA-930 `ERCO` `D` | ERCOT NP6-345-CD `TOTAL` |
|---|---|---|
| Quantity | BA "actual demand"; excludes electricity used to store energy (Form EIA-930) | "actual hourly load … ERCOT total"; inclusions not documented |
| Units | `megawatthours` (EIA: hourly integrated values) | not stated |
| Time labels | UTC `period` labels; hour-ending not stated for the API field | OperDay + HourEnding (01–24) + DSTFlag; time zone not stated |
| Revisions | resubmitted within 3 or 30 days; no per-value flag | no correction policy found |
| Publication time | not provided | listing PublishDate (with offset) |

A future reconciliation would need all of the following:
1. documented units for NP6-345-CD
2. a documented time zone, and the DST representation observed on a transition day
3. EIA's label convention confirmed for the API field
4. an ERCOT definition of TOTAL to compare with EIA-930 demand

Until then the sources are shown separately and never compared numerically.
