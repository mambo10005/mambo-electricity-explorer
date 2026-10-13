# Dataset contract: EIA-930 hourly net generation by energy source (`electricity/rto/fuel-type-data`)

Implemented in `src/mambo_explorer/generation.py` and `eia/dataset.py` (DATA-05). Source
review: `docs/source-register.md` (EIA-930 fuel-type-data section). Decision record: ADR
0014. Status: **live-verified 2026-10-12** (see below).

## Identity (read from the live API metadata on 2026-10-12, 4 keyed requests)

| Item | Value | Evidence |
|---|---|---|
| Route | `electricity/rto/fuel-type-data`, "Hourly Generation by Energy Source" | parent route listing `electricity/rto` |
| Description | "Hourly net generation by balancing authority and energy source. Source: Form EIA-930" | route metadata |
| Frequencies | `hourly` ("One data point for each hour in UTC time", format `YYYY-MM-DD"T"HH24`); `local-hourly` not used | route metadata |
| Facets | `respondent` ("Balancing Authority / Region"), `fueltype` ("Energy Source") | route metadata |
| Data column | `value`, alias "Net Generation", units `megawatthours`, aggregation SUM | route metadata |
| History | `startPeriod` 2019-01-01T00 (API); by-source data begins 2018-07-01 in EIA's files | route metadata; About page |
| Entity | `ERCO` = "Electric Reliability Council of Texas, Inc." | facet `respondent` |
| Store namespace | `eia930-fuel-type` (own directory, catalog, writer lock, schema, identity) | `eia/dataset.py` |
| Identity | source, dataset, route, frequency, entity, metric (`NG`), **energy_source**, period | `generation.py` |

## Energy-source codes

From the Form EIA-930 instructions (OMB 1905-0129, expiration 07/31/2029), "Data Code"
for data type NG: COL, NG, NUC, OIL, WAT, PS, SUN, SNB, WND, WNB, BAT, OES, GEO, OTH,
UNK. The API facet list (2026-10-12) also contains `UES` ("Unknown Energy" / "Unknown
energy storage"), which the instructions read do not define. Facet values repeat some ids
with alternate names (PS, SNB, BAT, UES).

Rules in the instructions:
- Hydro: if pumped storage cannot be separated, combine it into WAT.
- OTH is also used to mask a category with three or fewer generators when tariffs require.
- Dual-fuel units are reported under the fuel used if known, else the primary fuel; not
  as UNK.

The collector requests **no** `fueltype` filter, so a code outside this list is stored
with the quality flag `unreviewed_category` rather than dropped.

## Values and sign

- Net generation "should usually be positive. However, negative values may be reported for
  hours when there is net energy storage"; station use above gross output also gives a
  negative value (instructions, Data Type NG).
- Pumped storage, batteries, and other storage: net storage in an hour is reported as
  negative net generation for that category. Combined hydro may be negative. Total net
  generation may be negative when storage exceeds system generation.
- The "About the EIA-930 data" page says EIA has asked BAs to count pumped-storage negative
  generation as demand instead, and accepts negative values where a BA says it reports
  battery charging. **Which convention ERCOT uses is not stated per BA.**
- The app stores `value_raw` and the parsed `value` unchanged: no clipping, no zero for
  missing, flags `missing`, `non_numeric`, `negative`, `unreviewed_category`.
- Anomalous values are to be left blank by respondents; "Do not report zeros for any energy
  values unless they are valid zeros." Absent rows are therefore not zeros.

## Period semantics

Same as demand: UTC period labels; EIA documents hour-ending for EIA-930 but not for the
API field, so `interval_start_utc`/`interval_end_utc` stay null (`INTERVAL_CONVENTION`).

## Totals and balance

- "The sum of the values reported for net generation by energy source is expected to equal
  reported total net generation each hour" **to the extent possible**; discrepancies are
  allowed with an explanation (instructions, "Net generation").
- The total (data code SYS) lives on route `region-data` type `NG` and is **not collected**.
  The app never calls a category sum total system generation.
- Energy balance (demand + net tie-line flow = net generation) is a reporting expectation,
  not a rule the app applies: generation is never equated with demand, and interchange or
  losses are never inferred.

## Revisions

Unexpected errors above 10 MWh in an hour are resubmitted within 30 days (instructions);
demand is collected hourly and again the next day, and values "may or not be the same"
(About page). Revisions are kept with lineage; the refresh plan re-requests a lookback.

## Live verification (2026-10-12, scratch storage)

- Metadata: route, facets, entity, units confirmed; no codes outside the reviewed list.
- `collect --days 2 --lookback-days 0`: 1 request; 232 rows = 8 categories × 29 hours
  (2026-10-11T00 .. 2026-10-12T04). Row fields: `period`, `respondent`,
  `respondent-name`, `fueltype`, `type-name`, `value`, `value-units`. Stored values
  matched the archived response 232/232. BAT negative in 16 hours (min −7,907 MWh).
- Repeat of the same window: 1 request; 232 unchanged, 0 revised (idempotent).
- `validate` ok. Status: **live-verified 2026-10-12**.
