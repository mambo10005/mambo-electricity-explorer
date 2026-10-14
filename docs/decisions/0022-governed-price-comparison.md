# 0022 — Governed comparison of a day-ahead SPP with an approved RT analytical summary

- **Status:** Accepted
- **Date:** 2026-10-13

## Context

Three independent decisions now stand between two stored prices and a comparison:
1. **M1:** which real-time intervals align with a day-ahead hour (ADR 0020);
2. **AGG-A/AGG-B:** how four aligned interval prices may be summarized (ADR 0021);
3. **This stage:** whether and how the day-ahead SPP and the summary may be compared.

ERCOT defines no day-ahead/real-time price difference in the reviewed Protocols. "DART" appears
only as a variable prefix (§4.6.3, a locational day-ahead difference). Real-time settlement prices
participant quantities, and the credit formulas use day-ahead and real-time averages as ratios.

## Decision

1. **Two versioned, approvable records** (`ercot/comparison_policy.py`):
   - **CMP-A 1.0.0** (S_RT − P_DAM) and **CMP-B 1.0.0** (P_DAM − S_RT).
   - Each holds: explicit ±1 coefficients with a checked sign convention, inputs, both datasets,
     the HB_NORTH scope, the M1 dependency, the accepted AGG records (fingerprints), policies,
     the output name "Analytical DAM-to-RT price difference (…)", $/MWh, allowed uses,
     prohibited interpretations, evidence, limitations, and triggers.
   - **Not approvable:** absolute and percentage differences (candidates only).
2. **No silent sign:**
   - The record selector starts empty.
   - An approval covers one record, and there is no fallback between records.
   - Inconsistent sign metadata gives `invalid_input`.
3. **Approvals** (`mambo comparison …`) reuse the append-only local workflow:
   - They additionally require the M1 version, the accepted aggregation records, and the
     location, restated explicitly.
   - `status` never prints the reviewer.
   - Synthetic approvals count only in a `SYNTHETIC-ENVIRONMENT` data directory.
4. **Production** (`comparison.compare`): computes one hour only when every prerequisite in
   `docs/comparison-evidence.md` §4–7 holds:
   - an explicit mode;
   - three active approvals;
   - complete alignment;
   - a current alignment snapshot;
   - an approved complete aggregation with a current matching snapshot;
   - the selected DAM revision of the same identity;
   - $/MWh on both sides.

   Otherwise it withholds the value with one of 17 statuses and every blocker. The output is
   $/MWh, multiplied only by the record's ±1 coefficients. Finality is always "not determined".
5. **Snapshots:** append-only comparison snapshots go stale on any input, approval, method,
   policy, formula, or validation change.
6. **UI:** a separate "Comparison investigation" section, one hour at a time:
   - no chart and no time series;
   - mode off and no record chosen by default;
   - the persistent notice: "This is an analytical price comparison under review-approved
     assumptions. It is not an ERCOT settlement, profit-and-loss result, trading backtest, or
     forecast evaluation."
7. **Guards:**
   - no money, trading, quantity, forecast, or DART identifiers in the comparison modules;
   - no unnegated claims;
   - multiplication only by the sign coefficients (and in the percentage candidate);
   - production never uses the percentage or absolute candidates;
   - imported only by the diagnostic and the CLI (never refresh, collection, or Finance).
8. **Stage 24 guards, kept and narrowed:**
   - The identifier guard (no `rt_minus`/`da_minus`) is kept unchanged. The governed
     difference uses neutral names (`difference_rt_first`, `difference_dam_first`).
   - The aggregation-import allow-list gains exactly `comparison.py`, `comparison_policy.py`,
     and `comparison_view.py`.

## Consequences

- **No production comparison exists** until three attributable approvals are recorded locally.
  Even then, only complete governed hours are compared.
- **Stage 26** (the learner lesson) needs those approvals plus human review of the lesson
  content.

## Alternatives considered

- **Label the output "DART":** rejected. It is not an ERCOT-defined term for this, and external
  usage has inconsistent signs.
- **Default to one sign convention:** rejected. That would silently choose the meaning of
  "positive".
- **Percentage difference in production:** rejected. It is undefined at zero and misleading with
  negative prices; it needs its own governed record.
- **Multiply by load to show money:** rejected. There is no participant quantity, and doing so
  would turn an analytical price difference into a pseudo-settlement.
