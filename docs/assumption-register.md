# Assumption register

Operational assumptions the application may use **only** when a recorded, attributable approval
is active and the user explicitly selects them. An assumption is not an official definition. Its
official-evidence status stays as found, whatever a reviewer decides. Decision: ADR 0020.
AI-authored; not human-reviewed.

## M1 — day-ahead hour to real-time intervals (version 1.0.0)

Source of truth: `src/mambo_explorer/ercot/m1_policy.py` (`M1`). `mambo assumption show` prints
it with its fingerprints.

| Field | Value |
|---|---|
| Identifier / version | M1 / 1.0.0 (record status: current) |
| Rule | Match one NP4-190-CD day-ahead hour (DeliveryDate D, HourEnding `hh:00`, DSTFlag F, SettlementPoint P) to the NP6-905-CD observations with the same DeliveryDate label D, DeliveryHour = the number hh, the same verbatim DSTFlag F, the in-scope settlement point and type for P, and DeliveryInterval labels 1–4. Hour 24 stays on its published DeliveryDate. Repeated hours are matched per flag and never merged. |
| Datasets | NP4-190-CD (day-ahead SPP), NP6-905-CD (real-time SPP) |
| Location scope | day-ahead `HB_NORTH` (store type `hub`, from NP4-160-SG) ↔ real-time `HB_NORTH` / `HU`. **Observed association:** HB_NORTH appears once per interval as type HU in the live files. The HU code is not officially defined. |
| Expected intervals | `1, 2, 3, 4`: **part of M1**, not an independently verified rule. This is the only place in the code where the expectation exists (guard test). |
| Flags | `N`, `Y` matched verbatim. Any other value gives `ambiguous_dst`. N is never read as standard time, nor Y as daylight time. |
| Schema fingerprint | sha256 of both reports' headers and stored identities (`schema_fingerprint()`) |
| Scope fingerprint | sha256 of id, version, rule, datasets, locations, intervals, flags, and the schema fingerprint. **An approval binds to it.** |
| Supporting evidence | OFF-1, OFF-2, OFF-3, OFF-5 (official, concept and field names); ACT-1, ACT-2, ACT-3 (actual files). See `docs/interval-alignment.md`. |
| Official status | **unresolved** |

**Unresolved definitions** (none can be settled by accepting M1):
1. HourEnding and DeliveryHour: no official definition that they name the same Operating Hour.
2. DeliveryInterval: no official definition that 1–4 are the hour's 15-minute Settlement
   Intervals in order.
3. DSTFlag: documented only as "DST Flag"; the meanings of N and Y are not defined.
4. DeliveryDate: not officially stated to be the Operating Day.
5. SettlementPointType `HU`: not officially defined as the hub type.

**Limitations:**
- Not ERCOT-verified, and not a legal or regulatory approval.
- A complete alignment does not prove a complete Operating Day, final prices, or correct
  official semantics.
- Labels and price presence only. Nothing is aggregated, compared, or converted to a clock time
  or UTC.
- Revisions are those this computer retrieved; none is called final.

**Re-review triggers:**
- ERCOT publishes field definitions, a user guide, or a schema change.
- A change to either header or stored identity (the schema fingerprint changes).
- A DSTFlag other than N/Y, or labels that contradict M1.
- Observation of a DST-day NP4-190-CD/NP6-905-CD document (BL-8).
- Adding a settlement point or type.
- Any new version of the record.

### Status of M1 — four separate things

| Kind | Status | Evidence |
|---|---|---|
| Authorization to implement | **given** | The Stage 23 request (2026-10-13) authorizes proceeding with M1 as a documented, review-approved operational assumption. |
| Reported reviewer acceptance | **reported, not attributable** | The request calls M1 review-approved but names no reviewer, role, date, or artifact. |
| Recorded, attributable approval | **none recorded** | No approval record exists in the repository or the real data directory. Activation is **pending**. |
| Official ERCOT verification | **unresolved** | No official label definitions (`docs/interval-alignment.md` §1). |

No reviewer, signature, date, or approval artifact has been invented, and the user is not
assumed to be the reviewer.

## Approval workflow (local, append-only)

Records live in `<MAMBO_DATA_DIR>/assumptions/approvals.jsonl`. That is gitignored, so they are
never committed and never shown outside this computer. Each line is one event.

```powershell
# 1. Read the record and its fingerprints.
.venvs/py314/Scripts/mambo assumption show
# 2. Current approval state (missing / approved / revoked / superseded / incompatible / invalid).
.venvs/py314/Scripts/mambo assumption status
# 3. Record an approval the reviewer actually gave (a dry run first; --execute appends).
.venvs/py314/Scripts/mambo assumption approve --reviewer "<name>" --role "<role>" `
    --evidence "<where the approval is documented>" --approved-on YYYY-MM-DD
.venvs/py314/Scripts/mambo assumption approve ... --execute
# 4. Revoke it later (also a dry run without --execute).
.venvs/py314/Scripts/mambo assumption revoke --record APR-M1-xxxxxxxx --reason "<why>" --execute
```

**Rules:**
- **Required fields:** reviewer, role, evidence reference, and the actual approval date. None is
  filled in automatically, and future dates are refused.
- **No credentials:** text that looks like a credential (key/token/password patterns, or
  32+-character tokens) is refused.
- **Append-only:** nothing is deleted or rewritten. A later approval supersedes an earlier one,
  which stays in the file. A revocation references the approval it revokes.
- **Binding:** an approval matches only its assumption version **and** scope fingerprint. A new
  version, a scope change, or a schema change makes it `incompatible` until re-reviewed.

**Activation** happens only when all of these hold:
1. the user selects "Use review-approved assumption M1" (per session; every session starts
   authoritative-only);
2. the approval status is `approved` for this version and scope;
3. the revision policy is `latest-retrieved` or `first-retrieved`.

The page and every result then show: "Aligned under review-approved assumption M1. ERCOT
report-label definitions remain unverified."

## Aggregation records (Stage 24, ADR 0021)

Source of truth: `src/mambo_explorer/ercot/aggregation_policy.py`. `mambo aggregation list`
lists the records and `mambo aggregation show <id>` prints each one with its fingerprints. Full
evidence: `docs/aggregation-evidence.md`.

| Field | AGG-A 1.0.0 | AGG-B 1.0.0 |
|---|---|---|
| Method | arithmetic mean | duration-weighted mean |
| Formula (version) | S = (P1 + P2 + P3 + P4) / 4 (A.1) | S = Σ(Pi × Di) / ΣDi (B.1) |
| Output name / units | "Hourly analytical RT SPP summary (arithmetic mean)", $/MWh | "Hourly analytical RT SPP summary (duration-weighted mean)", $/MWh |
| Dataset / location | NP6-905-CD, `HB_NORTH`/`HU` | same |
| Depends on | M1 1.0.0 and its scope fingerprint | same |
| Completeness | one current M1 alignment snapshot: four intervals, one selected revision each, published prices, no unresolved duplicates | same, plus duration evidence for every interval |
| Duration evidence | not used | DUR-15: 15 minutes, DSTFlag N only (OFF-2, OFF-11). DSTFlag Y gives `duration_unsupported`. |
| Revision policies | latest-retrieved, first-retrieved | same |
| Allowed use | describing an hour's typical posted RT SPP level in learning and diagnostic views | same |
| Prohibited | an ERCOT settlement price for the hour, a final price, a spread or DART, a settlement amount, P&L or a backtest, energy weighting, Finance input | same |
| Evidence | OFF-2, OFF-12 (HRSAP, a credit formula) | OFF-2, OFF-11, OFF-12 |
| Official status | no ERCOT-defined hourly real-time SPP | same |
| Reviewer / role / date / evidence | **none recorded** | **none recorded** |
| Approval status | **missing**, so production is inactive | **missing**, so production is inactive |
| Record status | current | current |

**Re-review triggers:**
- a new M1 or record version, or a change to M1's scope;
- ERCOT publishing an hourly real-time SPP or label definitions;
- an NP6-905-CD header, identity, or interval-length change;
- extending a record to another point or to DSTFlag Y.

**Not approvable:**
- **energy-weighted price:** no compatible quantities; EIA-930 demand must not stand in;
- **settlement amount:** an amount, not a price, and it needs participant quantities.

**Status of each record, four separate things:**
- **Authorization to build:** given (Stage 24 request).
- **Reported acceptance:** none.
- **Recorded, attributable approval:** none.
- **Official definition:** none exists.

### Approving an aggregation record (local, append-only)

```powershell
.venvs/py314/Scripts/mambo aggregation list
.venvs/py314/Scripts/mambo aggregation show AGG-A          # version, scope and limitations fingerprints
.venvs/py314/Scripts/mambo aggregation approve AGG-A --version 1.0.0 --scope <scope_fingerprint> `
    --accept-limitations <limitations_fingerprint> --reviewer "<name>" --role "<role>" `
    --evidence "<where documented>" --approved-on YYYY-MM-DD            # dry run
.venvs/py314/Scripts/mambo aggregation approve AGG-A ... --execute
.venvs/py314/Scripts/mambo aggregation status AGG-A          # never prints the reviewer
.venvs/py314/Scripts/mambo aggregation revoke AGG-A --record APR-AGG-A-xxxxxxxx --reason "<why>" --execute
.venvs/py314/Scripts/mambo aggregation restore AGG-A --record APR-AGG-A-xxxxxxxx --version 1.0.0 `
    --scope <...> --accept-limitations <...> --reviewer ... --role ... --evidence ... --approved-on ... --execute
```

- **Which approvals count:** an aggregation summary needs **both** an active M1 approval and an
  active approval of the chosen record.
- **Synthetic approvals** (tests and scratch checks) are marked `synthetic`. They count only
  where the data directory contains a `SYNTHETIC-ENVIRONMENT` file; never create that file in
  the real data directory.
