---
lesson_id: day-ahead-price
title: Reading an actual day-ahead electricity price
order: 14
sequence_stage: regional-markets
prerequisites: [power-vs-energy, location-prices]
objectives:
  - Name the market stage, location, and unit of the price shown.
  - Read how the day-ahead price varies across ERCOT's hour labels for one delivery date.
  - Read a negative price as a published value, not an error.
  - Explain why a missing price is not zero.
  - Explain revisions and why this app does not call a price final.
  - Explain why a day-ahead hub price is not a retail bill, a real-time price, or a forecast.
content_version: 1.0.0
effective_date: 2026-10-12
authored_by: Claude (AI agent)
authored_at: 2026-10-12
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: ercot-np4-190-cd
    title: ERCOT data product NP4-190-CD, DAM Settlement Point Prices (report type 12331)
    url: https://www.ercot.com/mp/data-products/data-product-details?id=NP4-190-CD
    accessed: 2026-10-12
  - id: ercot-dam
    title: ERCOT, Day-Ahead Market overview
    url: https://www.ercot.com/mktinfo/dam
    accessed: 2026-10-12
  - id: ercot-nodal-protocols
    title: ERCOT Nodal Protocols (Aug 1, 2026) — Sections 2 (definitions), 3.5.2.1 (North 345 kV Hub), 4.5.3 (DAM results, price corrections, finality)
    url: https://www.ercot.com/mktrules/nprotocols/current
    accessed: 2026-10-12
  - id: ercot-np4-160-sg
    title: ERCOT data product NP4-160-SG, Settlement Points List and Electrical Buses Mapping
    url: https://www.ercot.com/mp/data-products/data-product-details?id=NP4-160-SG
    accessed: 2026-10-12
dataset_bindings:
  - dataset: NP4-190-CD
    route: ercot.com public report listing, report type 12331
    entity: HB_NORTH
    metrics: [settlement_point_price]
calculation_ids: [dam_price_reading]
data_panels: [dam_price]
exercises:
  - exercise_id: highest-hour
    kind: price
    generator: highest_hour
    calculation_id: dam_price_reading
  - exercise_id: negative-count
    kind: price
    generator: negative_count
    calculation_id: dam_price_reading
  - exercise_id: missing-not-zero
    kind: price
    generator: missing_not_zero
    calculation_id: dam_price_reading
  - exercise_id: not-a-bill
    kind: price
    generator: not_a_bill
    calculation_id: dam_price_reading
  - exercise_id: finality-unknown
    kind: price
    generator: finality_unknown
    calculation_id: dam_price_reading
glossary_terms: [Day-Ahead Market, Settlement Point Price, Trading hub, Delivery date, Price finality, Revision, ERCOT, Modeled nodal price]
limitations:
  - One market stage (day-ahead) at one settlement point (HB_NORTH, the North 345 kV Hub). Other hubs, load zones, resource nodes, and real-time prices are not shown.
  - ERCOT's file states no time zone. DeliveryDate, HourEnding, and DSTFlag are shown as written and never converted to UTC; how DST days appear in this report has not been observed.
  - The unit ($/MWh) comes from ERCOT's Nodal Protocols, not from the file itself.
  - Finality is not determined by this app. Price corrections are a separate ERCOT report that is not collected.
  - This lesson does not explain why a price was high or low, and these prices are never joined with EIA demand or generation.
  - Values are the latest revision collected on this computer; a revision changes the exercises.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

**What you are looking at.** ERCOT runs a **Day-Ahead Market (DAM)**. ERCOT calls it a
voluntary, financially binding forward energy market: the day before electricity flows,
buyers and sellers are matched for each hour of the next day. For every hour the DAM
publishes a **Settlement Point Price** at each settlement point: resource nodes, load zones,
and trading hubs.

This lesson uses one of them: **HB_NORTH**, the **North 345 kV Hub**. A hub is a settlement
point defined in ERCOT's Protocols as a group of high-voltage buses with a fixed price
method. The North Hub's day-ahead price is computed from its hub buses, which ERCOT lists in
Section 3.5.2.1 of its Protocols.

**The unit.** The file does not print a unit. ERCOT's Protocols express day-ahead settlement
point prices in **dollars per megawatt-hour ($/MWh)**. A price of 30 means 30 dollars for each
MWh in that hour at that hub.

**Hour labels.** Each row has a **DeliveryDate**, an **HourEnding** from 01:00 to 24:00, and a
**DSTFlag**. ERCOT's Protocols define an Operating Day as hours ending 0100 to 2400. The file
does not say which time zone the labels use, so the app shows them exactly as written and does
not turn them into clock times. Prices usually differ from hour to hour because the market
clears each hour separately.

**Negative prices.** Some hours can have a price below zero. That is a published value, not a
mistake, and the app keeps the sign. **Why** a price was low, high, or negative is not in this
data, so the lesson does not guess.

**Missing prices.** If a row has no price, it is shown as missing. Missing is not zero, and the
app never fills it in.

**Revisions and finality.** ERCOT can correct day-ahead prices for a short time; its Protocols
say they are final at 10:00 on the second Business Day after the Operating Day. Corrections
are published in a separate report that this app does not collect. If ERCOT re-posts this
report with a changed price, the app stores it as a new **revision** and keeps the old one. A
successful download does not make a price final, so the app shows finality as "not
determined".

**What this price is not.**
- Not your electricity bill: retail prices add delivery and other charges and contract terms.
- Not the real-time price: the real-time market sets its own prices later.
- Not a forecast, and not a forward price for a future month.
- Not the same as a bus price (LMP) or the **modeled** prices from the Model Labs lessons.

## Technical detail

- **Source:** ERCOT NP4-190-CD "DAM Settlement Point Prices" (report type 12331), "the
  Settlement Point Prices for all Resource Nodes, Load Zones, and Trading Hubs from the
  Day-Ahead Market"; posted per DAM run; public; display duration 31 (EMIL). Accessed through
  ERCOT's public report listing and document download (no login), the same method as the load
  report.
- **File:** one ZIP with one CSV per DAM run; header `DeliveryDate, HourEnding,
  SettlementPoint, SettlementPointPrice, DSTFlag`. On 2026-10-12 one document held 1,130
  settlement points × 24 hours. The app validates every row, keeps only `HB_NORTH`, and records
  the downloaded scope (rows and settlement points) separately from the stored rows.
- **Location identity:** the code `HB_NORTH` is ERCOT's settlement point name. ERCOT's
  settlement point list (NP4-160-SG) maps 75 hub buses to `HB_NORTH`; every one appears in the
  Protocols' North 345 kV Hub table (Section 3.5.2.1). The Day-Ahead hub price "uses the
  aggregated Shift Factors of the Hub Buses for each hour".
- **Identity of a stored price:** source, dataset, market stage, location, DeliveryDate,
  HourEnding, DSTFlag. A changed value for the same identity becomes revision n + 1.
- **Corrections:** Protocols Section 4.5.3 lists when ERCOT corrects DAM prices (for example a
  change above $0.02/MWh at a Load Zone or Hub before 1000 on the second Business Day) and
  says prices are final at that time. The DAM price-correction report (NP4-196-M) is not
  collected.
- **Exercises** come from the stored prices for the chosen DeliveryDate; their snapshot is a
  fingerprint of that day's labels, revisions, and raw values, so a revision or another day
  gives new questions.
