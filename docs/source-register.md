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
| EIA (U.S. Energy Information Administration) Open Data API v2 | Federal statistics | 1 | API key (`EIA_API_KEY`), sent as a URL query parameter | Reviewed 2026-10-11, see below | Generally permitted, with exceptions for third-party material (see below) | Not yet reviewed | Terms reviewed; per-dataset source notes pending | No |
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
