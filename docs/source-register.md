# Source Register

Every data source must pass an access and redistribution review **before**
any data is ingested (PRD R-27). "Review pending" means nothing about that
source's terms has been verified yet. No source is connected in Stage 1.

Review columns:

- **Access**: how data is obtained (API, file download) and the credential needed.
- **Terms**: link to and summary of the terms of use, verified on a recorded date.
- **Redistribution**: whether data, or derivatives of it, may be republished
  (this decides PUB-01).
- **Revisions**: how the source publishes corrections.

| Source | Kind | Planned order | Access | Terms | Redistribution | Revisions | Review status | Connected |
|--------|------|---------------|--------|-------|----------------|-----------|---------------|-----------|
| EIA (U.S. Energy Information Administration) Open Data API | Federal statistics | 1 | API key (`EIA_API_KEY`) | Review pending | Review pending | Review pending | Pending | No |
| ERCOT | ISO/RTO | After EIA (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| CAISO | ISO/RTO | After EIA (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| PJM | ISO/RTO | After EIA (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| MISO | ISO/RTO | After EIA (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| SPP | ISO/RTO | After EIA (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| NYISO | ISO/RTO | After EIA (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| ISO-NE | ISO/RTO | After EIA (U-3) | Review pending | Review pending | Review pending | Review pending | Pending | No |
| Non-ISO balancing authorities | Utilities / BAs | TBD by U-7 | Review pending | Review pending | Review pending | Review pending | Pending | No |
| FERC | Regulator | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |
| NERC and regional entities | Reliability | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |
| State PUCs/PSCs | Regulators | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |
| CFTC | Regulator | After operators | Review pending | Review pending | Review pending | Review pending | Pending | No |

## Review record

Add an entry for each completed review: date, reviewer, URLs checked,
findings, and any conditions on use.

_No reviews completed yet._
