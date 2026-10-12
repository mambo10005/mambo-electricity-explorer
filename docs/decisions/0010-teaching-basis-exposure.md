# 0010 — Basis exposure with a simplified fixed-price hedge (teaching cash flows)

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

After lesson 8 (energy settlement), a beginner needs to see why a financial hedge priced at
one location leaves exposure when the energy is bought at another. The learning sequence's
financial-contracts stage (PRD R-10/R-11) has no content yet.

## Source boundary (concepts only)

FERC's market-assessment glossary (checked in a browser on 2026-10-11) defines:
- **basis:** the price difference between otherwise identical products in different
  markets;
- **swaps:** with fixed-for-floating as the common type, in which one party pays a fixed
  price and receives a changing price;
- **hedging:** protecting value with instruments whose price changes are expected to
  offset a loss.

The glossary's context is natural gas. The CFTC glossary could not be checked, because it
showed a human-verification page. Nothing here describes a real contract, exchange, or
legal classification.

## Decision

`basis.py` (formula v1.0.0), separate from `settlement.py`:

    basis          = P_L − P_H                    (this app's sign)
    physical cost  = Q × P_L
    hedge receipt  = H × (P_H − K)                (negative = the buyer pays)
    net buyer cost = Q × P_L − H × (P_H − K)      (negative = a credit to the buyer)
                   = Q·K + Q·(P_L − P_H) + (Q − H)·(P_H − K)

- **Decomposition.** The three components are computed independently and must reproduce
  the net cost; otherwise the result is refused. The identities H = Q → Q·(K + basis) and
  P_L = P_H → Q·K are stated as properties of this teaching contract only.
- **Inputs.** Q and H are nonnegative MWh, up to 100,000. Prices and K are finite, from
  −1,000 to 10,000. Q = 0 with H > 0 is accepted and described as a financial position
  without physical consumption.
- **Modeled prices.** Optional: P_L and P_H can be imported **together** from **one**
  verified economic-dispatch run at **two different buses**, with the same checks as
  Stage 11. Two modeled prices from different runs are refused. Editing one price makes it
  synthetic again, and the other keeps its label. K is never taken from a run, and buses
  are not hubs. Stage 11's rule against one run supplying both day-ahead and real-time
  prices is unchanged: that compares two **market stages**, while this compares two
  **locations** in one modeled state.
- **UI.** The Finance page and lesson 9 show the cash flows, readings, decomposition, the
  basis, and whether the hedge raised or lowered cost in the scenario. Nothing is stored
  beyond lesson progress.

## Not done (by design)

Contract valuation, forward curves, futures margin, options, congestion-rights (FTR/CRR)
settlement, credit, collateral, fees, timing, and trading. FIN-04 is a simplified
hedge cash-flow exercise only. Forwards, swaps, futures, and PPAs remain unimplemented.
