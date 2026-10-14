# 0021 — Governed hourly real-time price aggregation (investigation; nothing active)

- **Status:** Accepted
- **Date:** 2026-10-13

## Context

A later day-ahead/real-time comparison needs one hour-level real-time figure. ERCOT
publishes 15-minute real-time SPPs and, in the reviewed materials, **no hourly real-time SPP**.

What the Protocols do say:
- Each 15-minute SPP is a time-weighted average of SCED prices (§6.6.1.1).
- Settlement multiplies 15-minute prices by participant quantities × ¼ (§6.6.3).
- A credit formula, HRSAP (§16.11.4.3.3), averages an Operating Hour's four North Hub RT SPPs
  with equal weight.

M1, which aligns the labels, is itself inactive until an attributable approval is recorded.

## Decision

1. **Four candidates are researched separately** (`docs/aggregation-evidence.md`):
   - arithmetic mean;
   - duration-weighted mean;
   - energy-weighted price;
   - settlement amount.

   Each has its own formula, units, and classification. None is called an "hourly RT price".
2. **Two versioned, approvable records** (`ercot/aggregation_policy.py`):
   - **AGG-A 1.0.0** (arithmetic) and **AGG-B 1.0.0** (duration-weighted, using DUR-15:
     15 minutes for DSTFlag N only).
   - Each holds: the formula and its version, the output name "Hourly analytical RT SPP
     summary (…)", $/MWh, `HB_NORTH`/HU, its M1 dependency (version and scope fingerprint),
     completeness and revision rules, allowed and prohibited uses, evidence, limitations, and
     re-review triggers.
   - **Not approvable:** energy-weighted prices and settlement amounts (no quantities).
3. **Approvals reuse the local, append-only workflow** (`mambo aggregation …`):
   - An approval requires reviewer, role, evidence reference, and date, plus the version,
     scope fingerprint, and limitations fingerprint exactly as `show` prints them.
   - Revoke and restore are new events.
   - `status` never prints the reviewer.
   - Approvals marked `synthetic` count only in a data directory marked
     `SYNTHETIC-ENVIRONMENT`.
4. **Production aggregation** (`aggregation.aggregate`) runs only when every prerequisite in
   `docs/aggregation-evidence.md` §4–7 holds:
   - two approvals;
   - M1 selected;
   - complete alignment;
   - one current alignment snapshot with matching revisions;
   - supported policy;
   - no conflicts;
   - duration evidence for B;
   - published prices.

   Otherwise it withholds the value with a status (11 values) and every blocker. There is no
   fallback to another method. Arithmetic is exact (Decimal on published text).
5. **Candidate calculations** (`aggregation.candidate`) run on synthetic inputs only and
   report `candidate_only`.
6. **Snapshots** of aggregation results are append-only and go stale on any change of:
   - inputs or alignment snapshot;
   - M1 or its approval;
   - the record or its approval;
   - duration evidence;
   - formula version or validation version.
7. **UI:** the alignment diagnostic gains an "Aggregation investigation" section. It shows
   formulas, dimensions, the classification, synthetic benchmarks, approval states, and the
   governed or withheld result for stored observations, with this persistent text: "This is an
   analytical summary under review-approved assumptions. It is not an ERCOT-defined hourly
   settlement price, settlement, or trading backtest."
8. **Guards:** no spread, DART, P&L, profit, or backtest identifiers anywhere. The aggregation
   modules never import the day-ahead module. Aggregation is used only from the diagnostic.
   No claim is unnegated. No four-interval or clock constants appear in the new modules. The
   Stage 22 and 23 guards are unchanged.

## Consequences

- **No production summary exists** until a reviewer approves M1 and one aggregation record;
  even then, it covers only complete hours.
- **Stage 25** needs, in addition, a separately defined and reviewed day-ahead-versus-real-time
  comparison formula.

## Alternatives considered

- **Treat the HRSAP credit formula as an official hourly price:** rejected. It is a credit
  calculation, not a published or settlement price.
- **Use EIA-930 demand as weights:** rejected. It is not a settlement quantity at HB_NORTH.
- **Substitute 0.25 h for DSTFlag Y intervals:** rejected. There is no duration evidence for
  that case.
