"""Opt-in alignment under a review-approved assumption record (Stage 23, ADR 0020).

Two bases, never mixed:
- **authoritative-only** (default): `alignment.align`, which returns unsupported_semantics
  because ERCOT does not define the report labels;
- **review-approved assumption** (opt-in): M1 from `ercot/m1_policy.py`, usable only when the
  caller explicitly selects it, the recorded approval (`ercot/approvals.py`) is active and
  matches the record's version and scope, and the revision policy is supported.

Results expose their basis, the assumption id/version, the approval reference, and
`authoritative_semantics_status = "unresolved"`. They carry labels, revision references, and
price presence only: never a price value, aggregate, spread, clock time, or UTC.

Snapshots (`snapshot`, `record_snapshot`, `snapshot_states`) record the selected revisions and
the inputs; a snapshot whose inputs, policy, assumption version or scope, approval, or
validation version no longer match is reported stale. Nothing is deleted.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from mambo_explorer.ercot import alignment as al
from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot.m1_policy import BANNER, AssumptionRecord, current

VALIDATION_VERSION = "23.1"  # bump when the matching or completeness logic changes

AUTHORITATIVE = "authoritative-only"
ASSUMPTION = "review-approved-assumption"
BASES = (AUTHORITATIVE, ASSUMPTION)

# Outcomes added by this basis (the Stage 22 statuses are reused otherwise).
APPROVAL_MISSING = "approval_missing"
APPROVAL_REVOKED = "approval_revoked"
APPROVAL_SUPERSEDED = "approval_superseded"
APPROVAL_INCOMPATIBLE = "approval_incompatible"
APPROVAL_INVALID = "approval_invalid"
NOT_SELECTED = "assumption_not_selected"
UNSUPPORTED_SCOPE = "unsupported_scope"
CONFLICTING_REVISIONS = "conflicting_revisions"
COMPLETE_UNDER = "aligned_complete_under_assumption"
INCOMPLETE_UNDER = "aligned_incomplete_under_assumption"
_APPROVAL_OUTCOME = {
    ap.MISSING: APPROVAL_MISSING,
    ap.REVOKED: APPROVAL_REVOKED,
    ap.SUPERSEDED: APPROVAL_SUPERSEDED,
    ap.INCOMPATIBLE: APPROVAL_INCOMPATIBLE,
    ap.INVALID: APPROVAL_INVALID,
}

COMPLETE = "complete_under_assumption"
INCOMPLETE = "incomplete"
NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class AssumedResult:
    alignment_basis: str
    assumption_id: str | None
    assumption_version: str | None
    approval_status: str | None
    approval_reference: str | None
    authoritative_semantics_status: str
    alignment_status: str
    completeness_status: str
    revision_policy: str
    dam_identity: dict
    dam_revision: dict | None
    matched: tuple[dict, ...]
    expected_intervals: tuple[str, ...]  # under the assumption only; () when not evaluated
    observed_intervals: tuple[str, ...]
    missing_intervals: tuple[str, ...]
    duplicate_intervals: tuple[str, ...]
    revision_conflicts: tuple[dict, ...]
    excluded: tuple[dict, ...]
    dst: dict
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]
    banner: str | None  # shown persistently whenever alignment ran under the assumption


def _candidate(assumption: AssumptionRecord, scope) -> al.Candidate:
    return al.Candidate(
        f"{assumption.id}@{assumption.version}",
        assumption.rule,
        al.ASSUMPTION_GOVERNED,
        assumption.supporting_evidence,
        (),
        (),
        (),
        assumption.unresolved_definitions,
        "operational assumption",
        expected_intervals=assumption.expected_intervals,
        compatible_types=frozenset({(scope.day_ahead_location_type, scope.real_time_type)}),
    )


def _hour(dam) -> al.DamHour:
    return dam.hour if isinstance(dam, al.DamObservation) else dam


def align_with_basis(
    basis: str,
    dam: al.DamObservation | al.DamHour,
    rt_candidates: Sequence[al.RtObservation],
    *,
    revision_policy: str,
    approval: ap.Approval | None = None,
    dam_revisions: Sequence[al.DamObservation] = (),
    assumption: AssumptionRecord | None = None,
) -> AssumedResult:
    """Align under an explicitly chosen basis. `approval` must come from `approvals.status`."""
    assumption = assumption or current("M1")
    hour = _hour(dam)

    def out(status, completeness=NOT_EVALUATED, inner: al.AlignmentResult | None = None, **kw):
        fields = {
            "alignment_basis": basis,
            "assumption_id": assumption.id if basis == ASSUMPTION else None,
            "assumption_version": assumption.version if basis == ASSUMPTION else None,
            "approval_status": approval.status if approval else None,
            "approval_reference": approval.reference if approval else None,
            "authoritative_semantics_status": assumption.official_status,
            "alignment_status": status,
            "completeness_status": completeness,
            "revision_policy": revision_policy,
            "dam_identity": inner.dam_identity if inner else al._dam_dict(hour),
            "dam_revision": inner.dam_revision if inner else None,
            "matched": inner.matched if inner else (),
            "expected_intervals": (),
            "observed_intervals": tuple(m["DeliveryInterval"] for m in inner.matched)
            if inner
            else (),
            "missing_intervals": inner.missing_intervals if inner else (),
            "duplicate_intervals": inner.duplicate_intervals if inner else (),
            "revision_conflicts": inner.revision_conflicts if inner else (),
            "excluded": inner.excluded if inner else (),
            "dst": inner.dst if inner else {},
            "reasons": inner.reasons if inner else (),
            "limitations": assumption.limitations if basis == ASSUMPTION else al.LIMITATIONS,
            "banner": None,
        }
        fields.update(kw)
        return AssumedResult(**fields)

    if basis not in BASES:
        return out(al.INVALID_INPUT, reasons=(f"unknown alignment basis {basis!r}",))
    if basis == AUTHORITATIVE:
        inner = al.align(
            dam, rt_candidates, revision_policy=revision_policy, dam_revisions=dam_revisions
        )
        return out(inner.status, inner=inner)

    # Assumption basis: every gate is checked before anything is matched.
    if revision_policy not in al.REVISION_POLICIES:
        return out(al.INVALID_INPUT, reasons=(f"unknown revision policy {revision_policy!r}",))
    if revision_policy not in al.SUPPORTED_REVISION_POLICIES:
        return out(al.UNAVAILABLE_REVISION, reasons=(al.REVISION_POLICIES[revision_policy],))
    if approval is None or approval.assumption_id != assumption.id:
        return out(
            APPROVAL_MISSING, reasons=("no approval status was supplied for this assumption",)
        )
    if not approval.active:
        return out(
            _APPROVAL_OUTCOME.get(approval.status, APPROVAL_INVALID), reasons=(approval.detail,)
        )
    if approval.assumption_version != assumption.version:
        return out(APPROVAL_INCOMPATIBLE, reasons=("the approval is for another version",))
    scope = assumption.location_for(hour.settlement_point, hour.location_type)
    if scope is None:
        return out(
            UNSUPPORTED_SCOPE,
            reasons=(
                f"{hour.settlement_point} ({hour.location_type}) is outside the approved scope "
                f"of {assumption.id} {assumption.version}",
            ),
        )
    inner = al._evaluate(
        _candidate(assumption, scope),
        dam,
        rt_candidates,
        revision_policy,
        al.STRICT,
        dam_revisions,
        candidate_check=False,
    )
    expected = assumption.expected_intervals
    kw = {"expected_intervals": expected, "banner": BANNER}
    if inner.status == al.ALIGNED_COMPLETE:
        return out(COMPLETE_UNDER, COMPLETE, inner, **kw)
    if inner.status == al.ALIGNED_INCOMPLETE:
        if inner.duplicate_intervals:
            return out(CONFLICTING_REVISIONS, INCOMPLETE, inner, **kw)
        return out(INCOMPLETE_UNDER, INCOMPLETE, inner, **kw)
    if inner.status in (al.MISSING_REAL_TIME, al.MISSING_DAY_AHEAD):
        return out(inner.status, INCOMPLETE, inner, **kw)
    return out(inner.status, NOT_EVALUATED, inner, **kw)


# --- snapshots -----------------------------------------------------------------------------------
SNAPSHOT_DIR = "alignment"
SNAPSHOT_FILE = "snapshots.jsonl"


def _sha(payload) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def inputs_fingerprint(
    dam_observations: Sequence[al.DamObservation], rt_observations: Sequence[al.RtObservation]
) -> str:
    """Identity, revision, document, and price presence of every stored input (no values)."""
    return _sha(
        {
            "dam": sorted(
                [list(o.hour.key()) + [o.hour.location_type, o.revision, o.doc_id, o.price_present]]
                for o in dam_observations
            ),
            "rt": sorted(
                [list(o.interval.key()) + [o.revision, o.doc_id, o.price_present]]
                for o in rt_observations
            ),
        }
    )


def context(
    basis: str,
    dam_identity: dict,
    revision_policy: str,
    stored_dam: Sequence[al.DamObservation],
    stored_rt: Sequence[al.RtObservation],
    approval: ap.Approval | None,
    assumption: AssumptionRecord | None = None,
) -> dict:
    """Everything a snapshot depends on. `stored_*` are all stored revisions of the hour
    (`hour_inputs`), so a snapshot goes stale when any of them changes."""
    assumption = assumption or current("M1")
    governed = basis == ASSUMPTION
    return {
        "basis": basis,
        "dam_identity": dam_identity,
        "revision_policy": revision_policy,
        "inputs": inputs_fingerprint(stored_dam, stored_rt),
        "assumption": (
            f"{assumption.id}@{assumption.version}:{assumption.scope_fingerprint()}"
            if governed
            else None
        ),
        "approval": (f"{approval.reference}:{approval.status}" if governed and approval else None),
        "validation_version": VALIDATION_VERSION,
    }


def hour_inputs(
    dam: Sequence[al.DamObservation], rtl: Sequence[al.RtObservation], hour: al.DamHour
) -> tuple[list, list]:
    """All stored revisions of the day-ahead hour and of real-time intervals with the same
    DeliveryDate and DeliveryHour number (every flag), the inputs a snapshot depends on."""
    number = str(int(hour.hour_ending[:2]))
    return (
        [o for o in dam if o.hour == hour],
        [
            o
            for o in rtl
            if o.interval.delivery_date_raw == hour.delivery_date_raw
            and o.interval.delivery_hour == number
        ],
    )


def snapshot(result: AssumedResult, ctx: dict, recorded_at_utc: str) -> dict:
    return {
        "snapshot_id": "aln-" + _sha([ctx, result.alignment_status, recorded_at_utc]),
        "recorded_at_utc": recorded_at_utc,
        "context": ctx,
        "alignment_status": result.alignment_status,
        "completeness_status": result.completeness_status,
        "assumption": (
            f"{result.assumption_id} {result.assumption_version}" if result.assumption_id else None
        ),
        "approval_reference": result.approval_reference,
        "dam_revision": result.dam_revision,
        "selected_real_time": [
            {k: m[k] for k in ("DeliveryHour", "DeliveryInterval", "DSTFlag", "revision", "doc_id")}
            for m in result.matched
        ],
    }


def snapshot_path(data_dir: Path) -> Path:
    return Path(data_dir) / SNAPSHOT_DIR / SNAPSHOT_FILE


def record_snapshot(data_dir: Path, snap: dict) -> Path:
    """Append one snapshot (explicit user action only); earlier lines are never changed."""
    p = snapshot_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snap, sort_keys=True) + "\n")
    return p


def snapshots(data_dir: Path) -> list[dict]:
    p = snapshot_path(data_dir)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


def snapshot_states(
    snaps: Sequence[dict], current_contexts: dict
) -> list[tuple[dict, str, list[str]]]:
    """(snapshot, state, reasons) for each recorded snapshot; nothing is removed.

    `current_contexts` maps a snapshot key (`snapshot_key(ctx)`) to the context recomputed now.
    States: current; stale (inputs, policy, assumption, approval, or validation changed);
    superseded (a later snapshot exists for the same key); unknown (not recomputed).
    """
    latest: dict[str, str] = {}
    for s in snaps:
        latest[snapshot_key(s["context"])] = s["snapshot_id"]
    out = []
    for s in snaps:
        key = snapshot_key(s["context"])
        now = current_contexts.get(key)
        if latest[key] != s["snapshot_id"]:
            out.append((s, "superseded", ["a later snapshot exists for the same hour and basis"]))
            continue
        if now is None:
            out.append((s, "unknown", ["the hour was not recomputed"]))
            continue
        changed = [k for k in sorted(now) if now[k] != s["context"].get(k)]
        out.append((s, "stale" if changed else "current", [f"{k} changed" for k in changed]))
    return out


def snapshot_key(ctx: dict) -> str:
    return _sha([ctx["basis"], ctx["dam_identity"], ctx["revision_policy"]])


def as_dict(result: AssumedResult) -> dict:
    return asdict(result)
