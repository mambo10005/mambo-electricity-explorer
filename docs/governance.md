# Governance workspace (Stage 26)

How a human reviewer inspects, approves, rejects, revokes, or supersedes the five governed
records, and how an operator sets what production may use. Decision: ADR 0023. Code:
`ercot/governance.py`, `governance_cli.py`, `governance_view.py`, `ercot/approvals.py`.
AI-authored; not human-reviewed.

## Records and dependencies

| Record | Role | Depends on |
|---|---|---|
| M1 1.0.0 | which RT intervals align with a DAM hour | — |
| AGG-A 1.0.0 | arithmetic hourly summary | M1 |
| AGG-B 1.0.0 | duration-weighted hourly summary | M1 |
| CMP-A 1.0.0 | RT summary minus DAM | M1 and one of AGG-A, AGG-B |
| CMP-B 1.0.0 | DAM minus RT summary | M1 and one of AGG-A, AGG-B |

A downstream record becomes operationally active only when its approval is active, every
upstream record is active, the scope fingerprints match, and, for AGG/CMP records, the governed
setting selects it. Approving before the dependencies is allowed; the record is then
`approved_but_inactive_due_to_dependencies` until they are, and never activates silently.

## States

| State | Meaning |
|---|---|
| missing | no decision recorded |
| under_review | an explicit no-decision was recorded |
| approved_inactive | approved; dependencies missing, not selected, or no governed policy |
| active | approved and operationally usable |
| rejected / revision_requested | the latest decision |
| revoked | the latest approval was revoked |
| superseded | a supersession names a replacement record and version |
| incompatible | the approval is invalid (for example synthetic in a real directory) |
| re_review_required | the approval binds to another version, scope, or limitations version |

The evidence column is separate: available, evidence_unavailable (a recorded local file is
gone; the approval is preserved), reference-only, or none.

## Commands (every mutation previews; `--execute` writes)

```powershell
mambo governance list
mambo governance status                       # states, settings, active set, stale snapshots
mambo governance review CMP-A                 # the package plus the exact approve command
mambo governance show CMP-A                   # the full review package (JSON)
mambo governance approve CMP-A --version 1.0.0 --scope <fp> --accept-limitations <fp> `
    --acknowledge CMP-A-L1,CMP-A-L2,CMP-A-L3,CMP-A-L4,CMP-A-L5 --approved-scope HB_NORTH `
    --triggers record --reviewer "<name>" --role "<role>" --date YYYY-MM-DD `
    --evidence "<path or reference>" [--evidence-verified-note "<how>"] --rationale "<why>" [--execute]
mambo governance reject AGG-B --reviewer … --role … --date … --rationale … --issue … [--execute]
mambo governance request-revision M1 … --issue … [--execute]
mambo governance revoke M1 --record APR-M1-xxxxxxxx --effective-on YYYY-MM-DD --reviewer … --role … --date … --rationale … [--execute]
mambo governance supersede AGG-B --replacement-id AGG-B --replacement-version 1.1.0 --migration "…" --reviewer … --role … --date … --rationale … [--execute]
mambo governance no-decision CMP-B --reviewer … --role … --date … --rationale … [--execute]
mambo governance set-aggregation --value AGG-A --reviewer "<operator>" --role … --date … --rationale … [--execute]
mambo governance set-convention --value CMP-A …
mambo governance set-revision-policy --value latest-retrieved …
mambo governance audit
```

Rules:
- **Required fields** are never filled in. The person running the command is not assumed to
  be the reviewer, and no role is read from Git or GitHub.
- **Acknowledgment** must name every limitation id (`review` prints them); `all` is refused.
  The ids and their version are stored with the approval.
- **Evidence** may be a local path, an identifier, a signed-record id, a meeting-note
  reference, or a description. Nothing is copied into the repository. A path is checksummed
  and checked for existence at recording time; `verified` is set only with
  `--evidence-verified-note`.
- **Restoring** a revoked approval is a new approval with `--restores <revoked id>`.
- **Files** (`<MAMBO_DATA_DIR>/assumptions/`, gitignored): `approvals.jsonl` (decisions),
  `governance-settings.jsonl` (settings), `audit.jsonl` (executed actions). Appends are atomic
  (temporary file + replace); earlier lines are never changed.
- **Privacy:** `status`, `audit`, and the Governance page never print a reviewer's name; the
  local files hold it. Learner pages show approval states only.
- **Synthetic approvals** (tests, scratch checks) count only in a directory containing
  `SYNTHETIC-ENVIRONMENT`; never create that file in the real data directory.

## Governed settings

| Setting | Values | Effect of a change |
|---|---|---|
| active_comparison_convention | CMP-A or CMP-B (at most one) | comparison snapshots stale; the other convention withheld; signs never reversed |
| active_aggregation_method | AGG-A or AGG-B (exactly one) | aggregation and comparison snapshots stale; no fallback (AGG-B without duration evidence withholds) |
| revision_policy | latest-retrieved or first-retrieved | alignment, aggregation, and comparison snapshots stale |

Neither policy is ever called final, corrected, historically known, or settlement-approved.
Unset settings withhold output; CMP-A and AGG-A are not defaults.

## Review package contents

Identifier and version; rule or formula; sign convention; scope and fingerprint; dependencies;
record-specific facts (for example, for M1: HB_NORTH only, same date label, same numeric hour,
same verbatim DSTFlag, intervals 1–4, hour 24 stays on its date, the repeated fall hour stays
distinct by flag, ERCOT has not defined the labels, HU is unresolved); authoritative and
empirical evidence; project assumptions; unresolved semantics; allowed and prohibited uses;
itemized limitations with version; validation evidence (test files); known failure modes;
re-review triggers; current state, activation, blockers, acknowledgment, evidence state, and
downstream records.

## Downstream effects

`mambo governance status` and the Governance page show, per snapshot kind, how many recorded
snapshots are stale under the current settings. Stale snapshots are kept; the diagnostic page
withholds production output until a new snapshot is recorded under the current governance.
