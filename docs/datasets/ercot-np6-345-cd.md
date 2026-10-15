# Dataset contract: ERCOT NP6-345-CD — Actual System Load by Weather Zone

Implemented in `src/mambo_explorer/ercot/` (DATA-04). Source review:
`docs/source-register.md` (ERCOT section). Decision record: ADR 0005.
Status: **live-verified 2026-10-11**.

## Identity

| Item | Value | Evidence |
|---|---|---|
| Report | NP6-345-CD, "Actual System Load by Weather Zone" | ERCOT product page / EMIL |
| Report type ID | 13101 | EMIL; document listing `ReportTypeID` |
| Description | "Report of Actual hourly load data by weather zone and ERCOT total." | product page |
| Rule | Nodal Protocols §6.3.2(4): post "no later than 0600 … for each hour of the previous Operating Day" | Protocols (April 1, 2026) |
| Audience / security | Public / Public (`SecurityStatus` "P") | EMIL; listing |
| Public retention | about 31 days (EMIL "Display Duration 31") | EMIL; live listing had 32 CSV docs |
| Store namespace | `ercot-np6-345-cd` (separate directory, catalog, lock, and schema from EIA) | `ercot/dataset.py` |

## Access (one transport)

ercot.com public report listing plus document download. No login, and no
credential of any kind.

1. `GET https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId=13101` returns
   JSON at `ListDocsByRptTypeRes.DocumentList[].Document`. Only
   `FriendlyName == ACTUALSYSLOADWZNP6345_csv` is used. The XML twin is ignored.
2. `GET https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=<DocID>` returns a
   ZIP with exactly one CSV member.

These are the URLs that ERCOT's own product page uses. **ERCOT does not document them
as a developer API**, so they may change. Any change fails validation; there is no
scraping fallback. ERCOT's documented Public API needs registration, a subscription
key, and an ID token, so it is not used (blocked: no account).

Limits enforced:
- 30 s timeout, at most 2 retries (429, 5xx, network), 1 s pause between requests
- request budget of 10, at most 7 documents per run
- listing ≤ 1 MB
- ZIP ≤ 500 KB with 1 `.csv` member ≤ 200 KB, read in memory with path and size checks
  (`safe_zip.py`)
- an HTML or non-ZIP response is rejected

## File schema (validated exactly)

`OperDay,HourEnding,COAST,EAST,FAR_WEST,NORTH,NORTH_C,SOUTHERN,SOUTH_C,WEST,TOTAL,DSTFlag`

- Any missing, extra, renamed, or reordered column is rejected as a schema change.
- `OperDay` is `MM/DD/YYYY`.
- `HourEnding` is `HH:00`, 01–24.
- `DSTFlag` is `Y` or `N`.
- A file holds one OperDay and at most 25 rows. Duplicate (OperDay, HourEnding,
  DSTFlag) rows are rejected.
- Values are kept as the original text (`value_raw`) plus the parsed number. An empty
  value is flagged `missing`, an unparseable one `non_numeric`, a negative one
  `negative`. Nothing is imputed.

## Zones and total

- Zones: `COAST`, `EAST`, `FAR_WEST`, `NORTH`, `NORTH_C`, `SOUTHERN`, `SOUTH_C`,
  `WEST`, plus `TOTAL`.
- **TOTAL is provided by ERCOT. It is not calculated here.** No ERCOT text found
  defines it as the sum of the zones.
- `zone_sum_minus_total` is stored on TOTAL rows as a diagnostic only. In the live
  data (72 hours) the maximum |difference| was 0.02, consistent with rounding.

## Units

**Not stated** in the file, EMIL, or the XSD. Stored as `"not stated by source"`.
ERCOT load reports are commonly read as MW, but that is not assumed.

## Time fields (never converted)

| Field | Meaning here | Notes |
|---|---|---|
| `oper_day` | ERCOT OperDay text, as written | also `oper_date` (calendar date only) |
| `hour_ending` | ERCOT HourEnding text, `01:00`…`24:00` | **time zone not stated**; not converted to UTC |
| `dst_flag` | ERCOT DSTFlag text | part of the observation identity |
| `row_order` | position in the source file | keeps ERCOT's order for repeated hours |
| `publish_time_raw` / `publication_time_utc` | listing `PublishDate`, e.g. `2026-10-11T05:50:00-05:00` | has an explicit offset, so UTC conversion is unambiguous |
| `retrieved_at_utc` | when this computer downloaded the document | not publication time |

**DST: unverified.** How this report represents the fall-back repeated hour and the
spring-forward missing hour has not been observed. All live rows so far have
`DSTFlag = N`. The design keeps every row:
- `DSTFlag` is in the identity, so two `02:00` rows with different flags are distinct
  observations.
- Rows are never merged.
- An absent hour is never invented.
- Days with ≠ 24 rows are flagged in the UI.

Next verification point: OperDay 2026-11-01 (posted about 2026-11-02, inside the public
window until about 2026-12-02).

## Identity, revisions, idempotence

- Identity: (source, dataset, entity, metric, oper_day, hour_ending, dst_flag).
- Re-collecting the same document gives no new rows.
- A reposted document (new DocID) with a different value becomes `revision + 1`, with
  its own doc_id, publish time, run, and archive lineage.
- No correction or repost policy has been found, and none observed so far.

## Archive

Each downloaded ZIP is stored **byte-identical** (no credential, so no sanitizing)
under `raw/run=<id>/<DocID>.zip` with its sha256. Repeat runs archive their own copy
(about 1–2 KB per document).

## Not compatible with EIA-930 (yet)

See "EIA vs. ERCOT: unresolved differences" in the source register. The two are shown
as separate sources and are never joined.
