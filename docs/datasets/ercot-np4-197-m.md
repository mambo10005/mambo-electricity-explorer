# ERCOT NP4-197-M — RTM Price Corrections (HB_NORTH, SPP corrections)

Decision: ADR 0024. Source review: `docs/source-register.md`. Code: `ercot/corrections.py`
(`mambo collect --source ercot-rt-corrections`). Reviewed and sampled live on 2026-11-26.

## What it is

ERCOT's report of corrected Real-Time Market prices (report type 13045, EMIL display 180
days). The live list held 488 documents back to 2026-07-10, in eight document kinds. This app
collects only `RTM_SPP` (`pricecorrection_RTM_SPP_<d>_to_<d>_NP4197_csv`), the correction of
the 15-minute Settlement Point Prices that NP6-905-CD publishes (ADR 0017). The LMP, SOG,
MCPC, and shadow-price kinds and every `_xml` twin are never downloaded. A single day can have
several `RTM_SPP` documents (seven on 2026-07-14), so `--publish-date` is refused if it
matches more than 3.

## File contract (live sample, document 1269374426, published 2026-09-01)

`DeliveryDate,DeliveryHour,DeliveryInterval,SettlementPointName,SettlementPointType,SPPOriginal,SPPCorrected,PriceCorrectionTime,DSTFlag`

| Observation | Value |
|---|---|
| Size | about 15 KB zipped, 2,424 rows, 1,117 settlement points; other documents up to about 760 KB zipped |
| Content | **only corrected rows**: DeliveryDate 08/30/2026, hour 10; `HB_NORTH`/`HU` has intervals 1 and 2 |
| `PriceCorrectionTime` | one value for the file (`09/01/2026 16:00:00`); no time zone stated |
| `DSTFlag` | `N` in the sample; no DST day observed in this report |
| Unit | not in the file; Protocols state SPPs in $/MWh |

## What the app stores

- Store `<MAMBO_DATA_DIR>/ercot-np4-197-m/`, only `HB_NORTH` (type kept as the file states it,
  `HU`), one row per correction event.
- Identity adds DeliveryInterval (1..4, as written) to the day-ahead identity. A later
  correction of the same interval is a **separate observation**; a re-posted event with changed
  prices becomes a revision.
- Original and corrected prices are kept as written beside parsed numbers; blank is missing.
- A document with no `HB_NORTH` row is valid and recorded with zero stored rows.
- Labels are raw: no UTC, no mapping to NP6-905-CD's or NP4-190-CD's labels, and no assumed
  number of intervals.

## What it does not do

- It does not change stored NP6-905-CD prices, and no calculator or page uses it.
- A missing row is not proof that no correction exists; a collected correction does not make
  a price final (Protocols §6.3(7) is recorded, not computed).
- Not part of `mambo refresh` or the System Health page; collected only on request.

## Limits

At most 3 documents per run; archive limit 3 MB; budget: 1 list request (about 255 KB) plus one
download per document, under the shared ercot.com pacing (1 s).
