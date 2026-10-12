# 0011 — Time-shape exposure under a flat-block hedge (teaching cash flows)

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

Lesson 9 isolated location (basis) exposure in one interval. The next idea a beginner needs
is **time**: a flat hedge in MW against consumption that varies by interval. Equal total
energy can still leave a price-weighted residual cost.

## Source boundary

The EIA Today in Energy article "Texas Heat Wave, August 2011" (2011-09-09) describes:
- a 16-hour weekday on-peak block;
- afternoon "super-peak" hours priced far above the morning hours;
- block prices that average high and low hours together.

It is cited as real-market context only; none of its numbers are used. FERC's glossary
showed a human-verification page on 2026-10-11 and was not used for this stage.

## Decision

`shape.py` (formula v1.0.0, scenario set v1.0.0) works on one location. Intervals are
identifiers with elapsed durations d_t > 0; there are no calendars, time zones, or DST.

    h_t = B·d_t;  physical_t = q_t·p_t;  receipt_t = h_t·(p_t − K)  (negative = buyer pays)
    net_t = physical_t − receipt_t  (negative = credit)
    total net = Σ h_t·K + Σ r_t·p_t                          (decomposition 1, r_t = q_t − h_t)
              = B·D·K + R·p̄ + Σ r_t·(p_t − p̄)               (decomposition 2, p̄ duration-weighted)

- **Checks.** Both decompositions are computed independently and must reproduce the net
  cost (relative 1e-12); otherwise the result is refused.
- **Labels.** The three parts of decomposition 2 are called *fixed hedge component*,
  *aggregate energy mismatch*, and *time-shape component*. The last is an **accounting
  split** under this choice of p̄, not a universal risk metric.
- **Inputs.** 1–24 intervals with unique ids. Durations over 0 and up to 24 h; energy 0 to
  100,000 MWh; B 0 to 100,000 MW; prices and K from −1,000 to 10,000. All finite.
  Physical power is accepted only with the interval's explicit duration.
- **Scenarios.** Ten predefined synthetic scenarios cover every benchmark. Edits are
  recorded as "edited from <scenario> v1.0.0".
- **No model prices.** One-period OPF runs are not stitched into a time series.
- **Accessibility.** Intervals are edited with ordinary widgets (choose an interval, then
  edit its numbers) rather than a canvas data grid. Results are HTML tables, with a narrow
  one-interval viewer because the full table is wide.
- **Feature.** FIN-05 is a teaching cash-flow exercise only. Exchange block products,
  forward curves, futures, and valuation remain unimplemented.

## Consequences

The Finance page now carries three teaching calculators. All share the same rules:
- bounded, finite inputs;
- one signed amount, read by role;
- explicit provenance;
- calculation ids that invalidate old exercise answers;
- nothing stored outside lesson progress.
