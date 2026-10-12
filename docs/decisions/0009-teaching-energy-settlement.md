# 0009 — A teaching energy-settlement calculator, not a settlement engine

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

The learning sequence has a settlement stage (PRD R-11) but no content. Settlement rules
are market-specific, versioned, and long. A beginner first needs the core idea: a
day-ahead financial commitment, then a separate settlement of the difference from it.

## Source boundary (ISO New England only, checked 2026-10-11)

ISO New England's public pages support:
- a day-ahead settlement of day-ahead commitments;
- a separate real-time settlement of the **differences** from those commitments, at the
  real-time LMP;
- the day-ahead energy item: net cleared quantity at each location, hourly, at the
  day-ahead LMP;
- the real-time energy item: net deviation at each location, at the real-time LMP, in
  five-minute intervals;
- invoices that also carry other allocations.

Nothing here generalizes these rules to other markets. ISO-NE's invoice sign convention
(a positive net amount is a credit) is **not** adopted.

## Decision

`settlement.py` (formula v1.0.0):

    S = scheduled_MWh × day_ahead_price + (actual_MWh − scheduled_MWh) × real_time_price

- **One signed amount.** A buyer pays S and a seller receives S. A negative S is a credit to
  a buyer (or a payment by a seller). Signs are never silently flipped, and both readings
  are shown.
- **Energy (MWh) only.** An optional MW entry requires an explicit duration.
- **Bounded, finite inputs.** Energy 0–100,000 MWh; prices −1,000 to 10,000 per MWh;
  duration over 0 and up to 24 h. Anything else is refused with no result shown.
- **Synthetic inputs.** Optionally, **one** verified teaching-model nodal price can be
  imported into **one** price field, labeled *modeled*. It must come from an optimal run
  whose price check passed, produced by the current checks and the pinned package. The
  label records the run id, scenario, bus, package commit, checks version, and
  verification status. Withheld, failed, infeasible, stale, or unpinned runs are refused,
  and one run cannot supply both prices.
- **Provenance and exercises.** The calculation id hashes every input, each price's
  provenance, and the formula version. Exercises use it as their snapshot, so changing an
  input creates new questions and old verdicts are not shown.
- **Not stored.** Nothing from the calculator is written anywhere except the lesson's
  normal progress record. Observation storage is untouched.
- **Finance page.** FIN-03 delivers the calculator and lesson 8. Futures, options, PPAs,
  hedging, credit, and collateral stay **planned**.

## Not done (by design)

- Market-specific settlement and invoice reconstruction: five-minute intervals, multiple
  locations, losses, uplift, ancillary services, capacity, transmission, fees, bilateral
  and virtual transactions.
- Derivatives valuation, trading, or regulatory filing.
- EIA demand forecasts are never used as day-ahead cleared quantities.
- No ERCOT data is used: its unit and time semantics are unresolved.
