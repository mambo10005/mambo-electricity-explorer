# ERCOT NP4-196-M — DAM Price Corrections (HB_NORTH, SPP corrections)

Decision: ADR 0024. Source review: `docs/source-register.md`. Code: `ercot/corrections.py`
(`mambo collect --source ercot-dam-corrections`). Reviewed and sampled live on 2026-11-26.

## What it is

ERCOT's report of corrected Day-Ahead Market prices (report type 13044, EMIL display 180
days). One listing holds several **document kinds**; this app collects only `DAM_SPP`
(`pricecorrection_DAM_SPP_<d>_to_<d>_NP4196_csv`). `DAM_EBLMP` (bus LMP) and `DAM_MCPC`
(ancillary) and every `_xml` twin are never downloaded.

## File contract (live sample, document 1300152768, published 2026-11-18)

`DeliveryDate,DeliveryHour,SettlementPoint,SPPOriginal,SPPCorrected,PriceCorrectionTime,DSTFlag`

| Observation | Value |
|---|---|
| Size | about 117 KB zipped, 13,344 rows, 1,135 settlement points |
| Content | **only corrected rows**: one DeliveryDate (11/16/2026), 11 hours for `HB_NORTH` |
| `PriceCorrectionTime` | one value for the file (`11/18/2026 10:00:00`); no time zone stated |
| `DSTFlag` | `N` in the sample; no DST day observed in this report |
| Unit | not in the file; Protocols state SPPs in $/MWh |

## What the app stores

- Store `<MAMBO_DATA_DIR>/ercot-np4-196-m/`, only `HB_NORTH`, one row per correction event.
- Identity: source, dataset, market stage, location, DeliveryDate, DeliveryHour,
  (null) interval, DSTFlag, PriceCorrectionTime. A later correction of the same hour is a
  **separate observation**. A re-posted event with changed prices becomes a revision.
- Original and corrected prices are kept as written (`original_raw`, `corrected_raw`) beside
  parsed numbers. A blank stays missing, never zero.
- A document with no `HB_NORTH` row is valid and is recorded as a run with zero stored rows.
- `DeliveryHour` is not `HourEnding` of NP4-190-CD. The labels are kept raw and never mapped,
  never converted to UTC.

## What it does not do

- It does not change stored NP4-190-CD prices, and no calculator or page uses it.
- A missing row is not proof that no correction exists; a collected correction does not make
  a price final (Protocols §4.5.3(6) finality is recorded, not computed).
- Not part of `mambo refresh` or the System Health page; collected only on request.
- Spring-forward and fall-back days are not observed in this report.

## Limits

At most 3 documents per run; archive limit 3 MB; budget: 1 list request plus one download per
document, under the shared ercot.com pacing (1 s).
