# Dataset contract: ERCOT NP6-905-CD — real-time Settlement Point Prices (HB_NORTH only)

Implemented in `src/mambo_explorer/ercot/rt_prices.py` (DATA-07). Source review:
`docs/source-register.md` (ERCOT NP6-905-CD review). Decision record: ADR 0017.
Status: **live-verified 2026-10-12** (one earlier attempt failed validation; see below).

## Identity

| Item | Value | Evidence |
|---|---|---|
| Report | NP6-905-CD, "Settlement Point Prices at Resource Nodes, Hubs and Load Zones" | ERCOT product page |
| Report type ID | 12301 | product page; listing `ReportTypeID` |
| Description | "Settlement Point Price for each Settlement Point, produced from SCED LMPs every 15 minutes." | product page |
| Price type | **Real-time Settlement Point Prices** — not SCED LMPs (LMP products are separate, e.g. NP6-788-CD, NP6-787-CD) | product page; ERCOT prices page |
| Posting | "Chron - 15 Minutes"; protocol NP6.3.2(2); live: published about 2 minutes after each quarter hour | product page; live listing |
| Audience / security | Public / Public | product page; listing "P" |
| Retention | display duration 7; live list: 676 CSV documents, oldest published 2026-10-06T00:02:01-05:00 | product page; listing |
| Document naming | one document per interval, FriendlyName `SPPHLZNP6905_YYYYMMDD_HHMM_csv` (XML twins ignored) | live listing |
| Store namespace | `ercot-np6-905-cd` (separate from day-ahead `ercot-np4-190-cd`) | `rt_prices.py` |

## File

- One ZIP (about 8 KB) with one CSV (about 45 KB) per 15-minute interval.
- Header (validated exactly): `DeliveryDate, DeliveryHour, DeliveryInterval,
  SettlementPointName, SettlementPointType, SettlementPointPrice, DSTFlag`.
- Live 2026-10-12: 1,142 rows and 1,130 distinct names. Rows are unique by **(name,
  type)**: 12 load zones and DC ties appear twice with different types (`LZ`/`LZEW`,
  `LZ_DC`/`LZ_DCEW`). Types seen: RN, PCCRN, LCCRN, PUN, LZ, LZEW, LZ_DC, LZ_DCEW, HU, SH, AH.
- `HB_NORTH` appears once per interval, with type `HU`.
- The parser requires that every row describe the same (DeliveryDate, DeliveryHour,
  DeliveryInterval, DSTFlag), and keeps only `HB_NORTH` with type `HU`.

## Price definition

Protocols §3.5.2.1(4) (North 345 kV Hub):

    RTSPP North345 = Max[−$251, (RTRDP + time-weighted Hub Bus prices)]   per 15-minute Settlement Interval

- **RTRDP** is the Real-Time Reliability Deployment Price for energy (§6.5.7.3.1, §6.6.1):
  the adder **is included**.
- **Floor:** −$251/MWh. §6.6.1(1) applies the floor "after adding the Real-Time Reliability
  Deployment Price Adders for Energy".
- **Unit:** $/MWh. The file states no unit.

## Interval contract

| Item | Finding | Handling |
|---|---|---|
| Duration | 15 minutes (product page; "15-minute Settlement Interval" in Protocols §2 and §6.6) | `interval_minutes = 15` |
| Identity | DeliveryDate `MM/DD/YYYY`, DeliveryHour `1`..`24`, DeliveryInterval `1`..`4`, DSTFlag `N`/`Y` | stored raw. Identity: source, dataset, market stage, location, all four fields |
| Time zone / UTC | not stated in the file | **not mapped**; no clock time or UTC boundary is derived |
| DST | not observed (live: all `N`) | DSTFlag in the identity; no fixed count of intervals per day |
| Document name | `…_20261013_0000_csv` held DeliveryDate 10/12 hour 24 interval 4 | recorded raw (`doc_friendly_name`); not used to infer time |
| Publication | listing PublishDate with offset | stored raw and as UTC |
| Retrieval | download time | separate field; never used as publication time |

The day-ahead report's conventions (hour-only labels) are **not** borrowed.

## Finality and corrections

- **Finality:** Protocols §6.3(7): "final at 1600 of the second Business Day after the
  Operating Day". After that, ERCOT may still notify within 30 days and seek Board review.
  The app does not compute Business Days, so finality is **not determined**.
- **Corrections:** §6.3(4)–(6); report **NP4-197-M** (RTM Price Corrections, type 13045,
  display 180) is **not collected**.
- **Reposts:** a re-posted interval document with a changed value becomes revision n + 1.

## Selection and scope

- The newest N CSV documents not already stored, at most 16 per run.
  `--include-stored` re-downloads the newest N to check revisions and idempotence.
- **Reported each run:**
  - listed documents and the oldest/newest listed publish time (available history);
  - documents already stored;
  - documents published but not requested (catch-up limit);
  - "no newer document published yet".
- Downloaded rows and settlement points are recorded separately from the single stored
  row per interval. Archives are kept byte-identical.

## Live verification (2026-10-12, scratch storage, no credential)

- **Review:** 1 listing + 1 download (schema); Protocols Section 6 downloaded to scratch.
- **First attempt (2 runs):** each used 2 requests and was rejected on the first document:
  "duplicate settlement point 'DC_E'". The parser's name-only uniqueness check was an
  unverified assumption. It now keys rows on (name, type), and a regression test covers the
  real pattern. The failed runs wrote no observations.
- **`collect --source ercot-rt-spp --latest 4`:** 5 requests (1 list + 4 downloads).
  - Intervals 10/12/2026 H24 I3, H24 I4, 10/13/2026 H1 I1, H1 I2 (all N).
  - Downloaded 4,568 rows (1,130 settlement points each); stored 4 rows.
  - Values 26.41, 25.92, 27.25, 26.75 $/MWh; 4/4 match the archived ZIPs.
  - Listing: 676 documents, 672 published but not requested.
- **Repeat with `--include-stored`:** 5 requests; 0 new, 0 revised, 4 unchanged.
  `validate` ok.
