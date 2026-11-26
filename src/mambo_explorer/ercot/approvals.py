"""Local, append-only approval records for assumption records (Stage 23, ADR 0020).

Records live in `<MAMBO_DATA_DIR>/assumptions/approvals.jsonl` (gitignored, never committed).
Each line is one event: an approval, or a revocation of an earlier approval. Nothing is
deleted or rewritten. A record is attributable only when a reviewer name, role, evidence
reference, and approval date were actually supplied; nothing is filled in automatically, and
the person running the command is never assumed to be the reviewer.

Statuses (`status()`): missing, approved, revoked, superseded, incompatible, invalid.

Stage 24 (ADR 0021) adds aggregation records: their approvals must also carry the record's
limitations fingerprint (`accepted_limitations`). A revoked approval is restored only by a
new attributable approval that names it (`restores`). An approval marked `synthetic` (tests
and scratch checks) counts only in a data directory marked synthetic (`SYNTHETIC_MARKER`).

Stage 26 (ADR 0023) adds review decisions as further event kinds (rejection,
revision_request, supersession, no_decision), itemized limitation acknowledgments, evidence
metadata (kind, local availability, checksum, whether the reviewer stated it was verified;
never inferred), rationale, and an atomic rewrite-on-append so a crash never truncates the
file. Earlier events keep parsing: every new field is optional.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from mambo_explorer.ercot.m1_policy import AssumptionRecord

DIRNAME = "assumptions"
SYNTHETIC_MARKER = "SYNTHETIC-ENVIRONMENT"  # a file whose presence marks a scratch data dir
FILENAME = "approvals.jsonl"
FIELDS = ("reviewer", "role", "evidence", "approved_on")
_SECRETISH = re.compile(
    r"(api[_-]?key|token|password|passwd|secret|bearer\s|authorization:|EIA_API_KEY|[A-Za-z0-9]{32,})",
    re.I,
)

MISSING = "missing"
APPROVED = "approved"
REVOKED = "revoked"
SUPERSEDED = "superseded"
INCOMPATIBLE = "incompatible"
INVALID = "invalid"
REJECTED = "rejected"
REVISION_REQUESTED = "revision_requested"
UNDER_REVIEW = "under_review"

KIND_APPROVAL = "approval"
KIND_REVOCATION = "revocation"
KIND_REJECTION = "rejection"
KIND_REVISION_REQUEST = "revision_request"
KIND_SUPERSESSION = "supersession"
KIND_NO_DECISION = "no_decision"
DECISION_KINDS = (KIND_APPROVAL, KIND_REJECTION, KIND_REVISION_REQUEST, KIND_NO_DECISION)
EVIDENCE_PATH = "local-path"
EVIDENCE_REFERENCE = "reference"


class ApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class Event:
    record_id: str
    kind: str  # "approval" | "revocation"
    assumption_id: str
    assumption_version: str
    scope_fingerprint: str
    reviewer: str | None = None
    role: str | None = None
    evidence: str | None = None  # a reference to where the approval is documented
    approved_on: str | None = None  # YYYY-MM-DD as supplied by the reviewer
    revokes: str | None = None
    reason: str | None = None
    recorded_at_utc: str = ""
    recorded_with: str = "mambo assumption (local CLI)"
    accepted_limitations: str | None = None  # aggregation records: limitations fingerprint
    restores: str | None = None  # a revoked approval this one reinstates
    synthetic: bool | None = None  # test/scratch approvals; never honored in a real data dir
    # Stage 26 decision fields (all optional so earlier events keep parsing)
    rationale: str | None = None
    acknowledged_limitations: list | None = None  # itemized limitation ids
    limitations_version: str | None = None  # fingerprint of the acknowledged items
    approved_scope: str | None = None
    re_review_triggers: list | None = None
    issue: str | None = None  # rejection / revision request
    effective_on: str | None = None  # revocation
    replacement_id: str | None = None  # supersession
    replacement_version: str | None = None
    migration: str | None = None
    evidence_kind: str | None = None  # local-path | reference
    evidence_available_locally: bool | None = None  # at recording time
    evidence_checksum: str | None = None  # sha256 of a local file, when one existed
    evidence_verified: bool | None = None  # only when the reviewer stated how it was verified
    evidence_verification_note: str | None = None


@dataclass(frozen=True)
class Approval:
    status: str
    assumption_id: str
    assumption_version: str
    record: Event | None
    detail: str

    @property
    def reference(self) -> str | None:
        return self.record.record_id if self.record else None

    @property
    def active(self) -> bool:
        return self.status == APPROVED

    @property
    def evidence_available(self) -> bool | None:
        """None when the evidence is a reference (not a file); False when a recorded local
        file is gone. The approval itself is preserved either way."""
        if not self.record or self.record.evidence_kind != EVIDENCE_PATH:
            return None
        return Path(self.record.evidence).is_file()


def recorded_now() -> str:
    """When this computer records a local event (approval, revocation, or snapshot).

    Record metadata only: never used to interpret, convert, or order any ERCOT label."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def synthetic_environment(data_dir: Path) -> bool:
    """True only for a data directory explicitly marked as synthetic (scratch checks)."""
    return (Path(data_dir) / SYNTHETIC_MARKER).is_file()


def path(data_dir: Path) -> Path:
    return Path(data_dir) / DIRNAME / FILENAME


def events(data_dir: Path) -> list[Event]:
    """Every recorded event, oldest first. Read-only; never creates the file."""
    p = path(data_dir)
    if not p.exists():
        return []
    out = []
    for n, line in enumerate(p.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            out.append(Event(**{k: raw.get(k) for k in Event.__dataclass_fields__}))
        except (ValueError, TypeError) as exc:
            raise ApprovalError(f"{p}: line {n} is not a valid approval event ({exc})") from None
    return out


def evidence_metadata(reference: str) -> dict:
    """What can be recorded about an evidence reference without reading its content:
    whether it names a local file right now, and that file's checksum. Never 'verified'."""
    candidate = Path(reference.strip())
    try:
        is_file = candidate.is_file()
    except OSError:
        is_file = False
    if not is_file:
        return {
            "evidence_kind": EVIDENCE_REFERENCE,
            "evidence_available_locally": False,
            "evidence_checksum": None,
        }
    return {
        "evidence_kind": EVIDENCE_PATH,
        "evidence_available_locally": True,
        "evidence_checksum": hashlib.sha256(candidate.read_bytes()).hexdigest()[:16],
    }


def _check_text(name: str, value: str | None) -> None:
    if value is None:
        return
    if not value.strip():
        raise ApprovalError(f"{name} is empty")
    if len(value) > 300:
        raise ApprovalError(f"{name} is longer than 300 characters")
    if _SECRETISH.search(value):
        raise ApprovalError(
            f"{name} looks like it contains a credential; approval records never do"
        )


def new_approval(
    assumption: AssumptionRecord,
    *,
    reviewer: str,
    role: str,
    evidence: str,
    approved_on: str,
    now: datetime | None = None,
    accepted_limitations: str | None = None,
    restores: str | None = None,
    synthetic: bool = False,
    rationale: str | None = None,
    acknowledged_limitations: list | None = None,
    approved_scope: str | None = None,
    re_review_triggers: list | None = None,
    evidence_verification_note: str | None = None,
) -> Event:
    """Build (not write) an approval event; every attributable field must be supplied."""
    for name, value in (
        ("rationale", rationale),
        ("verification note", evidence_verification_note),
    ):
        _check_text(name, value)
    needs = getattr(assumption, "limitations_fingerprint", None)
    if needs and accepted_limitations != needs():
        raise ApprovalError(
            "accepted limitations must equal the record's limitations fingerprint "
            f"({needs()}); read them with `show` first"
        )
    for name, value in (("reviewer", reviewer), ("role", role), ("evidence", evidence)):
        if value is None:
            raise ApprovalError(f"{name} is required; it is never filled in automatically")
        _check_text(name, value)
    try:
        day = date.fromisoformat(approved_on or "")
    except ValueError:
        raise ApprovalError("approved_on must be the actual approval date, YYYY-MM-DD") from None
    now = now or datetime.now(UTC)
    if day > now.date():
        raise ApprovalError("approved_on is in the future")
    return Event(
        record_id=f"APR-{assumption.id}-{uuid.uuid4().hex[:8]}",
        kind="approval",
        assumption_id=assumption.id,
        assumption_version=assumption.version,
        scope_fingerprint=assumption.scope_fingerprint(),
        reviewer=reviewer.strip(),
        role=role.strip(),
        evidence=evidence.strip(),
        approved_on=day.isoformat(),
        recorded_at_utc=now.astimezone(UTC).isoformat(timespec="seconds"),
        accepted_limitations=accepted_limitations,
        restores=restores,
        synthetic=True if synthetic else None,
        rationale=rationale.strip() if rationale else None,
        acknowledged_limitations=list(acknowledged_limitations)
        if acknowledged_limitations
        else None,
        limitations_version=accepted_limitations if acknowledged_limitations else None,
        approved_scope=approved_scope,
        re_review_triggers=list(re_review_triggers) if re_review_triggers else None,
        evidence_verified=True if evidence_verification_note else None,
        evidence_verification_note=(
            evidence_verification_note.strip() if evidence_verification_note else None
        ),
        **evidence_metadata(evidence),
    )


def new_revocation(
    assumption: AssumptionRecord,
    revokes: str,
    reason: str,
    now: datetime | None = None,
    *,
    reviewer: str | None = None,
    role: str | None = None,
    effective_on: str | None = None,
) -> Event:
    _check_text("reason", reason)
    for name, value in (("reviewer", reviewer), ("role", role)):
        _check_text(name, value)
    if effective_on is not None:
        try:
            date.fromisoformat(effective_on)
        except ValueError:
            raise ApprovalError("effective_on must be a date, YYYY-MM-DD") from None
    now = now or datetime.now(UTC)
    return Event(
        record_id=f"REV-{assumption.id}-{uuid.uuid4().hex[:8]}",
        kind="revocation",
        assumption_id=assumption.id,
        assumption_version=assumption.version,
        scope_fingerprint=assumption.scope_fingerprint(),
        revokes=revokes,
        reason=reason.strip(),
        reviewer=reviewer.strip() if reviewer else None,
        role=role.strip() if role else None,
        effective_on=effective_on,
        recorded_at_utc=now.astimezone(UTC).isoformat(timespec="seconds"),
    )


def new_decision(
    assumption: AssumptionRecord,
    kind: str,
    *,
    reviewer: str,
    role: str,
    decided_on: str,
    rationale: str,
    issue: str | None = None,
    replacement_id: str | None = None,
    replacement_version: str | None = None,
    migration: str | None = None,
    now: datetime | None = None,
    synthetic: bool = False,
) -> Event:
    """A rejection, revision request, supersession, or explicit no-decision (not written)."""
    if kind not in (KIND_REJECTION, KIND_REVISION_REQUEST, KIND_SUPERSESSION, KIND_NO_DECISION):
        raise ApprovalError(f"unknown decision kind {kind!r}")
    for name, value in (("reviewer", reviewer), ("role", role), ("rationale", rationale)):
        if not value:
            raise ApprovalError(f"{name} is required; it is never filled in automatically")
        _check_text(name, value)
    if kind in (KIND_REJECTION, KIND_REVISION_REQUEST) and not issue:
        raise ApprovalError("the identified issue is required")
    if kind == KIND_SUPERSESSION and not (replacement_id and replacement_version and migration):
        raise ApprovalError("supersession needs the replacement id, version, and migration")
    for name, value in (("issue", issue), ("migration", migration)):
        _check_text(name, value)
    try:
        day = date.fromisoformat(decided_on or "")
    except ValueError:
        raise ApprovalError("the decision date must be YYYY-MM-DD") from None
    now = now or datetime.now(UTC)
    if day > now.date():
        raise ApprovalError("the decision date is in the future")
    prefix = {
        KIND_REJECTION: "REJ",
        KIND_REVISION_REQUEST: "RRQ",
        KIND_SUPERSESSION: "SUP",
        KIND_NO_DECISION: "NOD",
    }[kind]
    return Event(
        record_id=f"{prefix}-{assumption.id}-{uuid.uuid4().hex[:8]}",
        kind=kind,
        assumption_id=assumption.id,
        assumption_version=assumption.version,
        scope_fingerprint=assumption.scope_fingerprint(),
        reviewer=reviewer.strip(),
        role=role.strip(),
        approved_on=day.isoformat(),  # the decision date, for every kind
        rationale=rationale.strip(),
        issue=issue.strip() if issue else None,
        replacement_id=replacement_id,
        replacement_version=replacement_version,
        migration=migration.strip() if migration else None,
        recorded_at_utc=now.astimezone(UTC).isoformat(timespec="seconds"),
        synthetic=True if synthetic else None,
    )


def append(data_dir: Path, event: Event) -> Path:
    """Append one event (the only write). Earlier lines are never changed."""
    known = events(data_dir)
    if event.kind == "revocation" and event.revokes not in {e.record_id for e in known}:
        raise ApprovalError(f"no recorded approval {event.revokes!r} to revoke")
    if event.restores:
        revoked = {e.revokes for e in known if e.kind == "revocation"}
        if event.restores not in revoked:
            raise ApprovalError(f"{event.restores!r} is not a revoked approval to restore")
    for name in ("reviewer", "role", "evidence", "reason", "rationale", "issue", "migration"):
        _check_text(name, getattr(event, name))
    return append_line(path(data_dir), json.dumps(asdict(event), sort_keys=True))


def append_line(p: Path, line: str) -> Path:
    """Append one line atomically: the whole file is rewritten to a temporary file in the same
    directory and swapped in with os.replace, so an interrupted write never truncates or
    corrupts the earlier records. Earlier lines are copied byte for byte."""
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = p.read_text("utf-8") if p.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(existing + line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return p


def status(data_dir: Path, assumption: AssumptionRecord) -> Approval:
    """The approval state of `assumption` from the recorded events (read-only)."""

    def result(state, record, detail):
        return Approval(state, assumption.id, assumption.version, record, detail)

    if assumption.status != "current":
        return result(SUPERSEDED, None, f"assumption record {assumption.id} is {assumption.status}")
    try:
        evs = [e for e in events(data_dir) if e.assumption_id == assumption.id]
    except ApprovalError as exc:
        return result(INVALID, None, str(exc))
    revoked = {e.revokes for e in evs if e.kind == "revocation"}
    supersessions = [e for e in evs if e.kind == KIND_SUPERSESSION]
    if supersessions:
        s = supersessions[-1]
        return result(
            SUPERSEDED,
            s,
            f"superseded by {s.replacement_id} {s.replacement_version} ({s.record_id})",
        )
    decisions = [e for e in evs if e.kind in DECISION_KINDS]
    if not decisions:
        return result(MISSING, None, "no decision has been recorded for this assumption")
    latest = decisions[-1]  # deterministic: file order is recording order
    if latest.kind == KIND_REJECTION:
        return result(REJECTED, latest, f"rejected ({latest.record_id}): {latest.issue}")
    if latest.kind == KIND_REVISION_REQUEST:
        return result(
            REVISION_REQUESTED, latest, f"revision requested ({latest.record_id}): {latest.issue}"
        )
    if latest.kind == KIND_NO_DECISION:
        return result(UNDER_REVIEW, latest, f"under review; no decision yet ({latest.record_id})")
    if latest.record_id in revoked:
        return result(REVOKED, latest, f"approval {latest.record_id} was revoked")
    if latest.assumption_version != assumption.version:
        return result(
            INCOMPATIBLE,
            latest,
            f"approval {latest.record_id} is for version {latest.assumption_version}, not "
            f"{assumption.version}; re-review is required",
        )
    if latest.scope_fingerprint != assumption.scope_fingerprint():
        return result(
            INCOMPATIBLE,
            latest,
            f"approval {latest.record_id} was given for a different scope or schema "
            f"({latest.scope_fingerprint}); re-review is required",
        )
    missing = [f for f in FIELDS if not getattr(latest, f)]
    if missing:
        return result(INVALID, latest, f"approval {latest.record_id} lacks {', '.join(missing)}")
    needs = getattr(assumption, "limitations_fingerprint", None)
    if needs and latest.accepted_limitations != needs():
        return result(
            INCOMPATIBLE,
            latest,
            f"approval {latest.record_id} accepted other limitations; re-review is required",
        )
    if latest.synthetic and not synthetic_environment(data_dir):
        return result(
            INVALID,
            latest,
            f"approval {latest.record_id} is synthetic; synthetic approvals count only in a "
            "data directory marked synthetic",
        )
    return result(
        APPROVED,
        latest,
        f"approved by {latest.reviewer} ({latest.role}) on {latest.approved_on}; "
        f"evidence: {latest.evidence}",
    )


def superseded_records(data_dir: Path, assumption: AssumptionRecord) -> list[str]:
    """Earlier approvals replaced by a later one (kept in the file, never deleted)."""
    approvals = [
        e for e in events(data_dir) if e.assumption_id == assumption.id and e.kind == "approval"
    ]
    return [e.record_id for e in approvals[:-1]]


def latest_approval(data_dir: Path, assumption: AssumptionRecord) -> Event | None:
    approvals = [
        e for e in events(data_dir) if e.assumption_id == assumption.id and e.kind == KIND_APPROVAL
    ]
    return approvals[-1] if approvals else None
