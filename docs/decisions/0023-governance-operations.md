# 0023 — Local governance operations for the price-comparison assumptions

- **Status:** Accepted
- **Date:** 2026-10-14

## Context

Stages 23–25 introduced five versioned, approval-gated records: M1 (alignment), AGG-A and
AGG-B (hourly summary), CMP-A and CMP-B (comparison). Each had its own `approve`/`revoke`
command, approvals accepted a limitations fingerprint, and the diagnostic used whichever
record the viewer selected. Three things were missing: a review workspace that shows a
reviewer everything about a record before deciding; decisions other than approve and revoke;
and governed, attributed choices of **which** convention, method, and revision policy production
may use, so that two opposite sign conventions can never both be active.

## Decision

1. **One approval path.** `mambo governance approve <id>` is the only way to record an
   approval. It requires the reviewer's name and role, the decision date, an evidence
   reference, the record version and scope fingerprint, the approved scope (HB_NORTH), the
   limitations version, **every limitation id acknowledged explicitly** (a generic "all" is
   refused), a rationale, and re-review triggers. The family commands' `approve`/`restore`
   actions now point to it; their `revoke`, `status`, `show`, and `list` still work.
2. **Decisions** are event kinds in the same append-only file: approval, rejection,
   revision_request, revocation (with an effective date), supersession (old and replacement
   record and version, migration implications), and no_decision. Each is attributed and
   reasoned; nothing is inferred from the account running the command.
3. **Itemized limitations** live in `ercot/governance.py` with ids (M1-L1 …, CMP-B-L6) and a
   version. An approval binds to the version; a material change makes the record
   `re_review_required`. Approvals recorded before itemization (fingerprint-only) stay valid
   because they accepted the same limitation text by fingerprint, and the UI labels them.
4. **Evidence metadata.** An evidence reference is stored as a local path (with a checksum and
   whether it exists now) or a reference. `verified` is recorded only when the reviewer states
   how it was verified. If a local file later disappears, the approval is preserved and the
   evidence is shown as currently unavailable. Reviewer names are never printed by the CLI
   `status`/`audit` or shown on pages.
5. **Dependency graph and activation.** AGG-* depend on M1; CMP-* depend on M1 and one AGG. A
   record may be approved before its dependencies; it is then
   `approved_but_inactive_due_to_dependencies` and is activated only after the dependencies and
   the scope fingerprints check out.
6. **Governed settings** (`<data>/assumptions/governance-settings.jsonl`, append-only): the
   active comparison convention (CMP-A or CMP-B, never both), the active aggregation method
   (AGG-A or AGG-B), and the revision policy (latest-retrieved or first-retrieved). Each change
   requires an operator name, role, date, and rationale, and is written only with `--execute`.
   **Nothing is set by default**: an unset setting withholds the corresponding output, and
   CMP-A is not preferred for being listed first.
7. **Production gates widen.** `aggregate()` withholds unless the record is the active method
   and the policy the governed one; `compare()` additionally requires the active convention.
   Signs are never reversed to match a different convention, and there is no fallback.
8. **Snapshots carry the settings.** Alignment, aggregation, and comparison snapshot contexts
   now include the governed values; changing any setting marks dependent snapshots stale (kept,
   never deleted). Validation versions were bumped (aggregation and comparison 26.1).
9. **Audit log** (`<data>/assumptions/audit.jsonl`, append-only): every executed governance
   action with the actor's role, the event id, and the outcome. Previews are not audited.
10. **Atomic writes.** Every event file is rewritten to a temporary file in the same directory
    and swapped in with `os.replace`, so an interrupted write never truncates earlier records.
11. **Governance section** on System Health: records, states, activation, dependencies, governed
    settings, blockers, stale downstream counts, evidence states, and full review packages.
    Read-only; viewing or expanding writes nothing.

## Consequences

- To produce any comparison on stored data, an operator must also set the three governed
  values (`mambo governance set-aggregation|set-convention|set-revision-policy … --execute`).
- Existing real approvals stay in force; the Governance page marks their acknowledgment as
  fingerprint-only. Re-approving through `mambo governance approve` records the itemized
  acknowledgment and supersedes the earlier approval in place (kept).
- Stage 27 (the learner lesson) needs active M1, AGG, and CMP records under the governed
  settings, plus human review of the lesson.

## Alternatives considered

- **Keep per-family approve commands:** rejected; they could not enforce itemized
  acknowledgment uniformly.
- **Default the active convention to the single approved one:** rejected; activation must be
  an explicit, attributed decision.
- **Delete stale snapshots on a settings change:** rejected; provenance stays.
