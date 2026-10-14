# Dataset contract: ERCOT NP4-190-CD — DAM Settlement Point Prices (HB_NORTH only)

Implemented in `src/mambo_explorer/ercot/prices.py` (DATA-06). Source review:
`docs/source-register.md` (ERCOT NP4-190-CD review). Decision record: ADR 0016.
Status: **live-verified 2026-10-12**.

## Identity

| Item | Value | Evidence |
|---|---|---|
| Report | NP4-190-CD, "DAM Settlement Point Prices" | ERCOT product page |
| Report type ID | 12331 | product page; listing `ReportTypeID` |
| Description | "The Settlement Point Prices for all Resource Nodes, Load Zones, and Trading Hubs from the Day-Ahead Market." | product page |
| Posting | "Event - Per DAM Run"; protocol rule NP4.5.3(2)(b); DAM results posted "no later than 1330" in the Day-Ahead (Protocols §4.5.3(2)) | product page; Protocols |
| Audience / security | Public / Public | product page; listing `SecurityStatus` "P" |
| Retention | display duration 31; the live list held 32 CSV documents (2026-09-11 .. 2026-10-12) | product page; listing |
| Market stage | Day-Ahead Market; ERCOT calls it "a voluntary, financially-binding forward energy market" | ERCOT DAM page |
| Store namespace | `ercot-np4-190-cd` (own directory, catalog, writer lock, schema, identity) | `ercot/prices.py` |

## Access (one transport)

The same public listing and download as NP6-345-CD (ADR 0005): listing JSON for report type
12331, `FriendlyName == DAMSPNP4190_csv` (the XML twin is ignored), then the document
download. No login and no credential. ERCOT's registered API is not used. No terms were
accepted automatically. Requests are paced at 1 s and bounded by the client budget.

## File

- One ZIP per DAM run with one CSV member (live: about 187 KB zipped, about 1.0 MB of CSV).
- Header (validated exactly): `DeliveryDate, HourEnding, SettlementPoint,
  SettlementPointPrice, DSTFlag`.
- Live 2026-10-12: 27,120 rows = 1,130 settlement points × 24 hours for one DeliveryDate.
  The settlement points included 7 hubs: HB_BUSAVG, HB_HOUSTON, HB_HUBAVG, HB_NORTH, HB_PAN,
  HB_SOUTH, HB_WEST.
- Values are written with a leading space (e.g. `" 28.27"`); the stored `value_raw` is the
  trimmed text.

## Location

- `HB_NORTH` is ERCOT's settlement point name.
- ERCOT's settlement-point list (NP4-160-SG, report type 10008, document dated
  2026-10-01) maps 75 hub buses to `HUB = HB_NORTH`, all at 345 kV. Every one appears in the
  table of Nodal Protocols §3.5.2.1, "North 345 kV Hub (North 345)" (Aug 1, 2026). The other
  hubs match their own sections the same way: South 31/31, Houston 20/20, West 17/17,
  Panhandle 12/12.
- Day-Ahead hub price: "uses the aggregated Shift Factors of the Hub Buses for each hour"
  (§3.5.2.1(2)). DASPP for a Hub follows the Hub's definition (§4.6.1.3).

## Units, time, finality

| Item | Finding | Handling |
|---|---|---|
| Unit | Not in the file. Protocols §4.5.3(5) states DAM Settlement Point Price changes in $/MWh. | stored `"$/MWh"` with that basis in `UNIT_TEXT` |
| Time labels | DeliveryDate `MM/DD/YYYY`, HourEnding `01:00` .. `24:00`, DSTFlag `N`/`Y`. No time zone in the file. Protocols: Operating Day = hours ending 0100 to 2400; CPT is defined but not stated for this report. | kept raw; no UTC; ordinal display in file order; DSTFlag is part of the identity |
| DST days | not observed (live data: all `N`) | 23 or 25 rows are accepted (at most 25 per day); nothing merged or invented |
| Publication time | listing `PublishDate` with offset (e.g. `2026-10-12T12:46:27-05:00`) | stored raw and as UTC |
| Retrieval time | when this computer downloaded it | stored separately; never used as publication time |
| Finality | Protocols §4.5.3(6): "final at 1000 of the second Business Day after the Operating Day" | **not determined** by the app (no Business-Day calendar) |
| Corrections | §4.5.3(3)–(5): ERCOT corrects invalid prices (thresholds include $0.02/MWh at a Load Zone or Hub before finality); DAM Price Corrections report NP4-196-M (report type 13044, display 180) | NP4-196-M **not collected**; a re-posted NP4-190-CD document with a changed value becomes revision n + 1 |
| Missing | blank price | stored missing (`quality_flags = missing`), never zero |
| Negative | allowed | stored signed (`negative` flag) |

## Identity and scope

- **Identity:** source, dataset, market_stage (`day-ahead`), location (`HB_NORTH`),
  DeliveryDate (raw), HourEnding, DSTFlag.
- **Downloaded scope vs stored scope:** each document is archived byte-identically (all
  settlement points). Every row is validated (header, formats, duplicates). Only `HB_NORTH`
  rows are stored. `downloaded_rows` and `downloaded_settlement_points` are kept on each
  stored row and in the run summary.

## What it is not

Not a bus LMP (NP4-183-CD), not a modeled nodal price (Model Labs), not a retail tariff or
bill, not a forward price, not a real-time price, and not a forecast. It is never joined with
EIA-930 demand or generation until the two sources' interval mapping is independently
verified.

## Live verification (2026-10-12, scratch storage, no credential)

- **Review (scratch):** 1 listing request (64 entries: 32 CSV and 32 XML), 1 list + 1
  download for the schema, and 1 list + 1 download of NP4-160-SG.
- **`collect --source ercot-dam-spp --latest 2`:** 3 requests. Documents 1285202649
  (published 2026-10-11T13:07:00-05:00, DeliveryDate 10/12/2026) and 1285595200 (published
  2026-10-12T12:46:27-05:00, DeliveryDate 10/13/2026).
  - Downloaded 54,240 rows (1,130 settlement points each); stored 48 rows (24 per day).
  - All 48 stored values match the archived ZIPs.
  - 10/12: min 16.84, max 70.22. 10/13: min 22.77, max 92.61. No negatives; all DSTFlag `N`.
- **Repeat:** 3 requests; 0 new, 0 revised, 48 unchanged. `validate` ok.

## Interval alignment with the NP6-905-CD real-time report (Stage 22, ADR 0019)

- **Status:** no mapping to NP6-905-CD real-time labels is accepted. Evidence record:
  `docs/interval-alignment.md`.
- **Official materials:**
  - They define the settlement concept: each 15-minute real-time Settlement Interval belongs
    to one day-ahead hour (Protocols §6.6.3.3).
  - They do not define this report's DeliveryDate/HourEnding/DSTFlag labels. The Current Day Reports XSD documents
    `DSTFlag` only as "DST Flag", and the product page lists no user guide.
- **Historical compilation** (NP4-180-ER, 2025–2026, scratch only): spring days have 23 hours with `03:00` absent; the fall day has 25 with `02:00 N` and `02:00 Y`; hour 24 stays under its DeliveryDate. The flag column there is named "Repeated Hour Flag". 48 NP4-190-CD hours (10/06–10/07/2026) match it exactly.
- **Identity:** this report's stored identity is unchanged, and `DSTFlag` is kept as
  published.
- **Diagnostic:** Explore → interval-alignment diagnostic reads its labels and whether each
  price is present, never the value.
