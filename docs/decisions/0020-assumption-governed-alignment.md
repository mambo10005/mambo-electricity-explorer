# 0020 — Assumption-governed day-ahead/real-time interval alignment (M1)

- **Status:** Accepted
- **Date:** 2026-10-13

## Context

Stage 22 (ADR 0019) found no official definition of the NP4-190-CD and NP6-905-CD time labels,
so it accepted no mapping. Candidate M1 (same date, hour number, verbatim DSTFlag, intervals 1–4)
is consistent with 648 days of ERCOT's historical compilations. The owner authorized proceeding
with M1 as an explicitly documented, review-approved **operational assumption**, while keeping
the official status unresolved.

## Decision

1. **A versioned assumption record** (`ercot/m1_policy.py`, `docs/assumption-register.md`).
   - It holds: the exact rule, datasets, location scope (with the observed HB_NORTH/HU
     association), expected intervals, flags, schema and scope fingerprints, evidence,
     unresolved definitions, limitations, and re-review triggers.
   - It records four statuses separately: authorization to implement, reported acceptance,
     attributable approval, and official verification.
   - The four-interval expectation lives only here (narrowed guard test).
2. **A local, append-only approval workflow** (`ercot/approvals.py`, `mambo assumption`).
   - **Location:** records live in the gitignored data directory.
   - **Contents:** reviewer, role, evidence reference, and date are all required, never filled
     in, and never committed. Credential-like text is refused.
   - **Status:** missing, approved, revoked, superseded, incompatible (version or scope
     mismatch), or invalid.
   - **This stage's approval:** none recorded, so activation is pending.
3. **Explicit activation.** `assumed_alignment.align_with_basis` aligns under M1 only when
   all of the following hold:
   - the caller selects the assumption basis;
   - the approval is active for the same version and scope;
   - the location is in scope;
   - the revision policy is supported.

   The authoritative-only basis (the default, and the Stage 22 `align()`) is unchanged and
   still returns `unsupported_semantics`.
4. **Distinct outcomes:**
   - approval: `approval_missing`, `approval_revoked`, `approval_superseded`,
     `approval_incompatible`, `approval_invalid`;
   - scope and revisions: `unsupported_scope`, `conflicting_revisions` (an equal revision
     number the policy cannot choose between);
   - completeness: `aligned_complete_under_assumption`, `aligned_incomplete_under_assumption`;
   - Stage 22 statuses otherwise.

   Results carry `alignment_basis`, assumption id/version, approval reference,
   `authoritative_semantics_status = "unresolved"`, and a separate `completeness_status`. The
   bare Stage 22 `aligned_complete` is never returned under the assumption.
5. **Revision policies:** `latest-retrieved` / `first-retrieved`, applied to both products.
   - **Ordering:** the stored revision number.
   - **Ties:** never broken. Equal numbers are a conflict.
   - Neither policy is called final or "known at the time".
6. **Snapshots** (`<data>/alignment/snapshots.jsonl`, explicit button only):
   - **Recorded:** the selected revisions and a context. The context covers an input
     fingerprint of every stored revision of the hour (identities, revisions, documents, price
     presence; no values), the policy, the assumption version and scope, the approval reference
     and status, and the validation version.
   - **Staleness:** a snapshot is stale when any of these differ, and superseded by a later
     snapshot of the same hour, basis, and policy.
   - **Retention:** nothing is deleted.
7. **UI:** the alignment panel gains the following:
   - a basis selector (session-only);
   - the approval panel (status, scope, fingerprints, the four statuses, unresolved
     definitions, re-review triggers, workflow commands);
   - the persistent banner;
   - an interval viewer (a narrow Interval/Found/Revision/Document table plus a single-interval
     Item/Value view);
   - snapshots.

   Limitations are always visible.

## Consequences

- **Activation:** M1 can be used only after a real reviewer's approval is recorded locally.
  Nothing activates it at startup.
- **Stage 24 prerequisites:**
  - an active scoped approval;
  - complete alignment under the selected policy;
  - an explicit real-time aggregation definition;
  - non-settlement and non-backtest limitations.

  Official semantics, finality, correction feeds, publication, license, and human content
  review stay unresolved.
- **Re-review:** a schema change or a new record version forces it, through the fingerprints.

## Alternatives considered

- **Mark M1 accepted in Stage 22's `CANDIDATES`:** rejected. It would read as official
  verification.
- **Treat the user's authorization as the reviewer's approval:** rejected. The request names no
  reviewer, date, or artifact.
- **Persist the selected basis between sessions:** rejected. It would activate M1 silently at
  startup.
