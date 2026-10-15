---
lesson_id: real-time-price
title: Reading an actual real-time settlement-point price
order: 15
sequence_stage: regional-markets
prerequisites: [day-ahead-price]
objectives:
  - Name the product, market stage, location, unit, and interval length of the price shown.
  - Read ERCOT's interval labels (DeliveryDate, DeliveryHour, DeliveryInterval, DSTFlag) without turning them into clock times.
  - Tell a real-time Settlement Point Price apart from a SCED LMP, and say what ERCOT adds for the hub.
  - Read negative prices, missing prices, absent intervals, and revisions correctly.
  - Explain why these prices alone are not a settlement invoice, and why finality is not decided here.
content_version: 1.0.0
effective_date: 2026-10-12
authored_by: Claude (AI agent)
authored_at: 2026-10-12
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources:
  - id: ercot-np6-905-cd
    title: ERCOT data product NP6-905-CD, Settlement Point Prices at Resource Nodes, Hubs and Load Zones (report type 12301)
    url: https://www.ercot.com/mp/data-products/data-product-details?id=NP6-905-CD
    accessed: 2026-10-12
  - id: ercot-nodal-protocols
    title: ERCOT Nodal Protocols — Sections 3.5.2.1 (North 345 kV Hub, real-time hub price), 6.3 (price correction, finality), 6.6.1 (Real-Time Settlement Point Prices)
    url: https://www.ercot.com/mktrules/nprotocols/current
    accessed: 2026-10-12
  - id: ercot-np4-197-m
    title: ERCOT data product NP4-197-M, RTM Price Corrections (report type 13045)
    url: https://www.ercot.com/mp/data-products/data-product-details?id=NP4-197-M
    accessed: 2026-10-12
  - id: ercot-prices
    title: ERCOT, Market Prices (real-time price products)
    url: https://www.ercot.com/mktinfo/prices
    accessed: 2026-10-12
dataset_bindings:
  - dataset: NP6-905-CD
    route: ercot.com public report listing, report type 12301
    entity: HB_NORTH
    metrics: [settlement_point_price]
calculation_ids: [rt_price_reading]
data_panels: [rt_price]
exercises:
  - exercise_id: highest-interval
    kind: rtprice
    generator: highest_interval
    calculation_id: rt_price_reading
  - exercise_id: negative-count
    kind: rtprice
    generator: negative_count
    calculation_id: rt_price_reading
  - exercise_id: absent-interval
    kind: rtprice
    generator: absent_interval
    calculation_id: rt_price_reading
  - exercise_id: spp-vs-lmp
    kind: rtprice
    generator: spp_vs_lmp
    calculation_id: rt_price_reading
  - exercise_id: not-invoice
    kind: rtprice
    generator: not_invoice
    calculation_id: rt_price_reading
glossary_terms: [Real-time Settlement Point Price, Settlement Interval, SCED, Price adder, Price floor, Settlement Point Price, Trading hub, Price finality, Revision]
limitations:
  - One market stage (real-time) at one settlement point (HB_NORTH). Other hubs, load zones, resource nodes, and LMP reports are not shown.
  - ERCOT's file states no time zone. Interval labels are shown as written; no clock time or UTC boundary is derived, and the number of intervals on a daylight-saving day is not assumed.
  - Only the intervals collected on this computer are shown; ERCOT's public list keeps about 7 days, and a refresh takes at most a few hours of intervals.
  - Finality is not determined by this app. Price corrections are a separate ERCOT report that is not collected.
  - This lesson does not explain why a price was high or low, does not compare real-time with day-ahead prices, and never joins prices with EIA data.
  - Agent-authored; not yet reviewed by a person.
implementation_status: implemented
---

## Beginner

**What you are looking at.** ERCOT also sets prices in **real time**, as electricity actually
flows. Its report NP6-905-CD publishes a **Settlement Point Price** for every settlement point
for each **15-minute Settlement Interval**. ERCOT describes these prices as "produced from SCED
LMPs every 15 minutes". This lesson uses the same location as the day-ahead lesson:
**HB_NORTH**, the North 345 kV Hub.

**The interval labels.** Each value comes with four labels: **DeliveryDate**, **DeliveryHour**
(1 to 24), **DeliveryInterval** (1 to 4, the quarter of that hour), and **DSTFlag**. The app shows
them as `H07 I3 N`: hour 7, third interval, DST flag N. The file does not say which time zone
these labels use, so the app does not turn them into clock times. It also does not assume that
every day has exactly 96 intervals, because daylight-saving days may differ and this has not
been observed yet.

**The unit and how the price is made.** Prices are in **dollars per megawatt-hour ($/MWh)**.
SCED, ERCOT's dispatch software, runs every few minutes and produces **LMPs** (locational
marginal prices). The real-time Settlement Point Price is **not** one of those LMPs. For the North
Hub, ERCOT's Protocols take a time-weighted average of the hub's bus prices over the 15
minutes, add a **reliability deployment price adder** (an amount that reflects certain
reliability actions), and apply a **floor of −$251/MWh**.

**Negative and missing values.** A price can be negative, down to that floor; the app keeps the
sign. A blank price is shown as missing. An interval that is **not stored at all** is different
again: it may not be published yet, it may not have been collected, or it may be older than
ERCOT's public list (about 7 days). The app never fills either kind of gap.

**Revisions and finality.** ERCOT can correct real-time prices; its Protocols say they are final
at 16:00 on the second Business Day after the Operating Day, with a further Board review path.
Corrections come in a separate report that is not collected here. If ERCOT re-posts an interval
with a different price, the app keeps both as revisions. A successful download does not make a
price final.

**What this is not.** It is not a settlement invoice: what a market participant pays or receives
also depends on metered energy, day-ahead positions, ancillary services, and other charges. It is
not the day-ahead price (lesson 14), and this lesson does not compare the two. It is not a
forecast or a retail price.

## Technical detail

- **Source:** ERCOT NP6-905-CD "Settlement Point Prices at Resource Nodes, Hubs and Load Zones"
  (report type 12301), "Chron - 15 Minutes", public, display duration 7; protocol reference
  NP6.3.2(2). Accessed through ERCOT's public report listing and document download (no login).
  Each document has its own FriendlyName, e.g. `SPPHLZNP6905_20261013_0015_csv`.
- **File:** one ZIP with one CSV per interval. The header is `DeliveryDate, DeliveryHour,
  DeliveryInterval, SettlementPointName, SettlementPointType, SettlementPointPrice, DSTFlag`.
  On 2026-10-12, one document held 1,130 settlement points for exactly one interval, and
  `HB_NORTH` had type `HU`. The app checks that each document covers exactly one interval and
  keeps only `HB_NORTH`.
- **Hub price (Protocols §3.5.2.1(4)):** `RTSPP North345 = Max[−$251, (RTRDP + time-weighted
  Hub Bus prices)]` for each 15-minute Settlement Interval. RTRDP is the Real-Time Reliability
  Deployment Price for energy (§6.5.7.3.1, §6.6.1).
- **Identity:** source, dataset, market stage, location, DeliveryDate, DeliveryHour,
  DeliveryInterval, DSTFlag. A changed value for the same identity becomes revision n + 1.
- **Corrections and finality:** §6.3(4)–(7). Prices are final at 1600 on the second Business
  Day after the Operating Day. The RTM Price Corrections report (NP4-197-M, type 13045) is not
  collected.
- **Exercises** come from the intervals stored for the chosen DeliveryDate. Their snapshot is a
  fingerprint of the labels, revisions, and raw values, so a newly collected interval or a
  revision gives new questions.
