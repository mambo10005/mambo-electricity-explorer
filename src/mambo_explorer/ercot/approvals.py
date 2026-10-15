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
"""

from __future__ import annotations

import json
import re
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
) -> Event:
    """Build (not write) an approval event; every attributable field must be supplied."""
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
    )


def new_revocation(
    assumption: AssumptionRecord, revokes: str, reason: str, now: datetime | None = None
) -> Event:
    _check_text("reason", reason)
    now = now or datetime.now(UTC)
    return Event(
        record_id=f"REV-{assumption.id}-{uuid.uuid4().hex[:8]}",
        kind="revocation",
        assumption_id=assumption.id,
        assumption_version=assumption.version,
        scope_fingerprint=assumption.scope_fingerprint(),
        revokes=revokes,
        reason=reason.strip(),
        recorded_at_utc=now.astimezone(UTC).isoformat(timespec="seconds"),
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
    for name in ("reviewer", "role", "evidence", "reason"):
        _check_text(name, getattr(event, name))
    p = path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(event), sort_keys=True) + "\n")
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
    approvals = [e for e in evs if e.kind == "approval"]
    if not approvals:
        return result(MISSING, None, "no approval has been recorded for this assumption")
    latest = approvals[-1]  # deterministic: file order is recording order
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
