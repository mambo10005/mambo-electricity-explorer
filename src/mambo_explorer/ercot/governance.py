"""Local governance of the five versioned records (Stage 26, ADR 0023).

Records: M1 (alignment), AGG-A / AGG-B (hourly summary), CMP-A / CMP-B (comparison). This
module adds, on top of `ercot/approvals.py`:
- the dependency graph (CMP-* needs M1 and one AGG; AGG-* needs M1) and activation states;
- itemized limitations with ids and a version, which an approval must acknowledge one by one;
- governed settings (the active comparison convention, the active aggregation method, the
  revision policy) as their own append-only event file, each change attributed and reasoned;
- review packages (one per record) for a human reviewer, with the record's explicit facts;
- an append-only audit log of every executed governance action.

Nothing here approves anything by itself, reads the person running the app as the reviewer,
or makes CMP-A, AGG-A, or a revision policy the default: an unset setting withholds output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot.aggregation_policy import AGG_A, AGG_B, DUR_15
from mambo_explorer.ercot.comparison_policy import CMP_A, CMP_B
from mambo_explorer.ercot.m1_policy import M1

SETTINGS_FILE = "governance-settings.jsonl"
AUDIT_FILE = "audit.jsonl"

RECORDS = {"M1": M1, "AGG-A": AGG_A, "AGG-B": AGG_B, "CMP-A": CMP_A, "CMP-B": CMP_B}
FAMILY = {"M1": "assumption", "AGG-A": "aggregation", "AGG-B": "aggregation",
          "CMP-A": "comparison", "CMP-B": "comparison"}  # fmt: skip
# Each entry: the upstream ids required; a tuple means "exactly one of".
DEPENDENCIES: dict[str, tuple] = {
    "M1": (),
    "AGG-A": ("M1",),
    "AGG-B": ("M1",),
    "CMP-A": ("M1", ("AGG-A", "AGG-B")),
    "CMP-B": ("M1", ("AGG-A", "AGG-B")),
}
AGGREGATIONS = ("AGG-A", "AGG-B")
CONVENTIONS = ("CMP-A", "CMP-B")
REVISION_POLICIES = ("latest-retrieved", "first-retrieved")

# Governance states (docs/governance.md).
MISSING = "missing"
UNDER_REVIEW = "under_review"
APPROVED_INACTIVE = "approved_inactive"
ACTIVE = "active"
REJECTED = "rejected"
REVISION_REQUESTED = "revision_requested"
REVOKED = "revoked"
SUPERSEDED = "superseded"
INCOMPATIBLE = "incompatible"
EVIDENCE_UNAVAILABLE = "evidence_unavailable"
RE_REVIEW_REQUIRED = "re_review_required"
STATES = (
    MISSING, UNDER_REVIEW, APPROVED_INACTIVE, ACTIVE, REJECTED, REVISION_REQUESTED, REVOKED,
    SUPERSEDED, INCOMPATIBLE, EVIDENCE_UNAVAILABLE, RE_REVIEW_REQUIRED,
)  # fmt: skip
INACTIVE_DEPS = "approved_but_inactive_due_to_dependencies"


@dataclass(frozen=True)
class Limitation:
    id: str
    text: str


# Itemized limitations a reviewer must acknowledge one by one (section 9 of the Stage 26
# request). Their version is a fingerprint of the items; a material change forces re-review.
LIMITATIONS: dict[str, tuple[Limitation, ...]] = {
    "M1": (
        Limitation("M1-L1", "Official ERCOT report-label semantics (HourEnding, DeliveryHour, "
                   "DeliveryInterval, DeliveryDate) are unresolved."),
        Limitation("M1-L2", "The meaning of DSTFlag (N, Y) is not officially defined."),
        Limitation("M1-L3", "SettlementPointType HU is an observed report value whose definition "
                   "is unresolved."),
        Limitation("M1-L4", "The mapping is accepted as an operational assumption, not as an ERCOT "
                   "definition."),
    ),
    "AGG-A": (
        Limitation("AGG-A-L1", "An analytical average only."),
        Limitation("AGG-A-L2", "Not an ERCOT settlement price."),
        Limitation("AGG-A-L3", "Not energy-weighted; each selected interval has equal weight."),
        Limitation("AGG-A-L4", "Requires all four M1-aligned intervals with published prices."),
    ),
    "AGG-B": (
        Limitation("AGG-B-L1", "An analytical duration-weighted average only."),
        Limitation("AGG-B-L2", "Not an ERCOT settlement price."),
        Limitation("AGG-B-L3", "Verified duration evidence is required for every interval; none "
                   "is substituted."),
        Limitation("AGG-B-L4", "Not energy-weighted."),
    ),
    "CMP-A": (
        Limitation("CMP-A-L1", "A project-defined sign convention (RT summary minus DAM)."),
        Limitation("CMP-A-L2", "Not an ERCOT-defined DART or any ERCOT quantity."),
        Limitation("CMP-A-L3", "Not a settlement, P&L, savings, or trading performance."),
        Limitation("CMP-A-L4", "Price finality is unresolved."),
        Limitation("CMP-A-L5", "Price-correction feeds (NP4-196-M, NP4-197-M) are not collected."),
    ),
    "CMP-B": (
        Limitation("CMP-B-L1", "A project-defined sign convention (DAM minus RT summary), the "
                   "exact reversal of CMP-A."),
        Limitation("CMP-B-L2", "Not an ERCOT-defined DART or any ERCOT quantity."),
        Limitation("CMP-B-L3", "Not a settlement, P&L, savings, or trading performance."),
        Limitation("CMP-B-L4", "Price finality is unresolved."),
        Limitation("CMP-B-L5", "Price-correction feeds (NP4-196-M, NP4-197-M) are not collected."),
        Limitation("CMP-B-L6", "Must not be operationally active together with CMP-A for the "
                   "same scope unless a later governance decision permits it."),
    ),
}  # fmt: skip


def _sha(payload) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def limitations_version(record_id: str) -> str:
    return _sha([(x.id, x.text) for x in LIMITATIONS[record_id]])


def limitation_ids(record_id: str) -> tuple[str, ...]:
    return tuple(x.id for x in LIMITATIONS[record_id])


class GovernanceError(ValueError):
    pass


def record(record_id: str):
    try:
        return RECORDS[record_id]
    except KeyError:
        raise GovernanceError(f"no governed record {record_id!r}") from None


def check_acknowledgment(record_id: str, acknowledged) -> tuple[str, ...]:
    """Every itemized limitation must be named explicitly; no catch-all is accepted."""
    ids = limitation_ids(record_id)
    given = tuple(x.strip() for x in (acknowledged or ()) if x and x.strip())
    if any(g.lower() in ("all", "*", "everything") for g in given):
        raise GovernanceError("a generic acknowledgment is not accepted; name every limitation id")
    missing = [i for i in ids if i not in given]
    unknown = [g for g in given if g not in ids]
    if missing or unknown:
        raise GovernanceError(
            f"acknowledge exactly {', '.join(ids)}"
            + (f"; missing {missing}" if missing else "")
            + (f"; unknown {unknown}" if unknown else "")
        )
    return ids


# --- governed settings -------------------------------------------------------------------------
SET_CONVENTION = "set_convention"
SET_AGGREGATION = "set_aggregation"
SET_REVISION_POLICY = "set_revision_policy"
SETTING_KINDS = {
    SET_CONVENTION: ("active_comparison_convention", CONVENTIONS),
    SET_AGGREGATION: ("active_aggregation_method", AGGREGATIONS),
    SET_REVISION_POLICY: ("revision_policy", REVISION_POLICIES),
}


def settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / ap.DIRNAME / SETTINGS_FILE


def setting_events(data_dir: Path) -> list[dict]:
    p = settings_path(data_dir)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


def current_settings(data_dir: Path) -> dict:
    """The governed choices in force: None until an operator sets each one explicitly."""
    out = {name: None for name, _ in SETTING_KINDS.values()}
    out["references"] = {}
    for e in setting_events(data_dir):
        name, _ = SETTING_KINDS[e["kind"]]
        out[name] = e["value"]
        out["references"][name] = e["event_id"]
    return out


def new_setting(
    kind: str,
    value: str,
    *,
    operator: str,
    role: str,
    decided_on: str,
    rationale: str,
    now: datetime | None = None,
) -> dict:
    if kind not in SETTING_KINDS:
        raise GovernanceError(f"unknown setting {kind!r}")
    name, allowed = SETTING_KINDS[kind]
    if value not in allowed:
        raise GovernanceError(f"{name} must be one of {allowed}")
    for label, text in (("operator", operator), ("role", role), ("rationale", rationale)):
        if not text or not text.strip():
            raise GovernanceError(f"{label} is required; it is never filled in automatically")
        ap._check_text(label, text)
    try:
        day = date.fromisoformat(decided_on or "")
    except ValueError:
        raise GovernanceError("the decision date must be YYYY-MM-DD") from None
    now = now or datetime.now(UTC)
    if day > now.date():
        raise GovernanceError("the decision date is in the future")
    return {
        "event_id": f"SET-{name}-{_sha([value, now.isoformat()])[:8]}",
        "kind": kind,
        "setting": name,
        "value": value,
        "operator": operator.strip(),
        "role": role.strip(),
        "decided_on": day.isoformat(),
        "rationale": rationale.strip(),
        "recorded_at_utc": now.astimezone(UTC).isoformat(timespec="seconds"),
    }


def append_setting(data_dir: Path, event: dict) -> Path:
    return ap.append_line(settings_path(data_dir), json.dumps(event, sort_keys=True))


def settings_fingerprint(settings: dict) -> dict:
    """What downstream snapshots depend on: the three governed values (not who set them)."""
    keys = ("active_comparison_convention", "active_aggregation_method", "revision_policy")
    return {k: settings.get(k) for k in keys}


# --- audit log ---------------------------------------------------------------------------------


def audit_path(data_dir: Path) -> Path:
    return Path(data_dir) / ap.DIRNAME / AUDIT_FILE


def audit(data_dir: Path, action: str, target: str, *, actor_role: str | None, event_id: str | None,
          outcome: str, detail: str = "", now: datetime | None = None) -> Path:  # fmt: skip
    """Append one audit line for an executed governance action (previews are not audited).
    The actor's name is not stored here; the event file holds it."""
    now = now or datetime.now(UTC)
    entry = {
        "recorded_at_utc": now.astimezone(UTC).isoformat(timespec="seconds"),
        "action": action,
        "target": target,
        "actor_role": actor_role,
        "event_id": event_id,
        "outcome": outcome,
        "detail": detail[:300],
        "tool": "mambo governance (local CLI)",
    }
    return ap.append_line(audit_path(data_dir), json.dumps(entry, sort_keys=True))


def audit_entries(data_dir: Path) -> list[dict]:
    p = audit_path(data_dir)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


# --- states and activation ---------------------------------------------------------------------


@dataclass(frozen=True)
class RecordState:
    id: str
    version: str
    approval_status: str  # approvals.status()
    state: str  # governance state
    activation: str  # active | inactive | approved_but_inactive_due_to_dependencies
    approval_reference: str | None
    detail: str
    blockers: tuple[str, ...]
    dependencies: tuple[str, ...]  # ids this record needs
    evidence_state: str  # available | evidence_unavailable | reference-only | none
    evidence_reference: str | None
    acknowledgment: str  # itemized | fingerprint-only | none
    limitations_version: str
    selected: bool | None  # AGG/CMP: whether the settings select this record


def _dep_ok(settings: dict, states: dict, dep) -> tuple[bool, str]:
    if isinstance(dep, tuple):
        chosen = settings.get("active_aggregation_method")
        if chosen is None:
            return False, f"no active aggregation method is set (one of {', '.join(dep)})"
        if chosen not in dep:
            return False, f"active aggregation {chosen} is not one of {', '.join(dep)}"
        st = states[chosen]
        return st.activation == ACTIVE, f"{chosen} is {st.state}"
    st = states[dep]
    return st.activation == ACTIVE, f"{dep} is {st.state}"


def _scope_compatible(rec, states: dict) -> list[str]:
    """A downstream record binds upstream versions and scope fingerprints; mismatches block."""
    problems = []
    dep = getattr(rec, "depends_on", None)
    if dep and dep != f"{M1.id}@{M1.version}:{M1.scope_fingerprint()}":
        problems.append(f"bound to {dep}, not the current M1")
    aggs = getattr(rec, "aggregations", None)
    if aggs is not None:
        current = {f"{r.id}@{r.version}:{r.scope_fingerprint()}" for r in (AGG_A, AGG_B)}
        if not set(aggs) & current:
            problems.append("accepts no current aggregation record")
    return problems


def states(data_dir: Path, settings: dict | None = None) -> dict[str, RecordState]:
    """Governance state of every record, dependencies resolved in graph order."""
    settings = settings or current_settings(data_dir)
    out: dict[str, RecordState] = {}
    for rid in ("M1", "AGG-A", "AGG-B", "CMP-A", "CMP-B"):
        rec = RECORDS[rid]
        a = ap.status(data_dir, rec)
        ev = a.record
        blockers: list[str] = []
        base = {
            ap.MISSING: MISSING,
            ap.UNDER_REVIEW: UNDER_REVIEW,
            ap.REJECTED: REJECTED,
            ap.REVISION_REQUESTED: REVISION_REQUESTED,
            ap.REVOKED: REVOKED,
            ap.SUPERSEDED: SUPERSEDED,
            ap.INCOMPATIBLE: RE_REVIEW_REQUIRED,
            ap.INVALID: INCOMPATIBLE,
            ap.APPROVED: APPROVED_INACTIVE,
        }[a.status]
        if (
            a.status == ap.APPROVED
            and ev
            and ev.limitations_version not in (None, limitations_version(rid))
        ):
            base = RE_REVIEW_REQUIRED
            blockers.append("the acknowledged limitations are not the current version")
        if a.status != ap.APPROVED:
            blockers.append(a.detail)
        for problem in _scope_compatible(rec, out):
            blockers.append(problem)
            if base == APPROVED_INACTIVE:
                base = INCOMPATIBLE
        selected = None
        if rid in AGGREGATIONS:
            selected = settings.get("active_aggregation_method") == rid
        elif rid in CONVENTIONS:
            selected = settings.get("active_comparison_convention") == rid
        deps_ok = True
        for dep in DEPENDENCIES[rid]:
            ok, why = _dep_ok(settings, out, dep)
            if not ok:
                deps_ok = False
                blockers.append(f"dependency: {why}")
        activation = "inactive"
        state = base
        if base == APPROVED_INACTIVE:
            if not deps_ok:
                activation = INACTIVE_DEPS
            elif selected is False:
                blockers.append("approved but not the selected method/convention")
            elif rid in CONVENTIONS and settings.get("revision_policy") is None:
                blockers.append("no governed revision policy is set")
            else:
                activation, state = ACTIVE, ACTIVE
        avail = a.evidence_available
        evidence_state = (
            "none" if ev is None or not ev.evidence else
            "reference-only" if avail is None else
            "available" if avail else EVIDENCE_UNAVAILABLE
        )  # fmt: skip
        ack = (
            "none" if ev is None or ev.kind != ap.KIND_APPROVAL else
            "itemized" if ev.acknowledged_limitations else
            "fingerprint-only" if ev.accepted_limitations else "none"
        )  # fmt: skip
        out[rid] = RecordState(
            id=rid,
            version=rec.version,
            approval_status=a.status,
            state=state,
            activation=activation,
            approval_reference=a.reference,
            detail=a.detail,
            blockers=tuple(blockers),
            dependencies=tuple(d if isinstance(d, str) else "|".join(d) for d in DEPENDENCIES[rid]),
            evidence_state=evidence_state,
            evidence_reference=ev.evidence if ev else None,
            acknowledgment=ack,
            limitations_version=limitations_version(rid),
            selected=selected,
        )
    return out


def active_set(data_dir: Path, settings: dict | None = None) -> dict:
    """What production may use right now (every value None until governed and active)."""
    settings = settings or current_settings(data_dir)
    st = states(data_dir, settings)
    agg = settings.get("active_aggregation_method")
    cmp = settings.get("active_comparison_convention")
    return {
        "m1": "M1" if st["M1"].activation == ACTIVE else None,
        "aggregation": agg if agg and st[agg].activation == ACTIVE else None,
        "convention": cmp if cmp and st[cmp].activation == ACTIVE else None,
        "revision_policy": settings.get("revision_policy"),
        "settings": settings_fingerprint(settings),
    }


def downstream(record_id: str) -> tuple[str, ...]:
    out = []
    for rid, deps in DEPENDENCIES.items():
        flat = [d for d in deps if isinstance(d, str)] + [
            x for d in deps if isinstance(d, tuple) for x in d
        ]
        if record_id in flat:
            out.append(rid)
    return tuple(out)


def stale_downstream(data_dir: Path, settings: dict | None = None) -> dict:
    """Snapshots whose recorded governance differs from the current settings (or predates
    them). Counted, never deleted."""
    from mambo_explorer.ercot import aggregation as ag
    from mambo_explorer.ercot import assumed_alignment as aa
    from mambo_explorer.ercot import comparison as cmp

    settings = settings or current_settings(data_dir)
    want = settings_fingerprint(settings)
    out = {}
    for name, loader, keys in (
        ("alignment", aa.snapshots, ("revision_policy",)),
        ("aggregation", ag.snapshots, ("active_aggregation_method", "revision_policy")),
        ("comparison", cmp.snapshots, ("active_comparison_convention", "active_aggregation_method",
                                       "revision_policy")),
    ):  # fmt: skip
        snaps = loader(data_dir)
        stale = 0
        for s in snaps:
            gov = s.get("context", {}).get("governance") or {}
            if any(gov.get(k) != want[k] for k in keys):
                stale += 1
        out[name] = {"total": len(snaps), "stale": stale}
    return out


# --- review packages -------------------------------------------------------------------------

FACTS = {
    "M1": (
        "Scope: HB_NORTH only.",
        "DAM dataset: NP4-190-CD. RT dataset: NP6-905-CD.",
        "Match on the same source-native date label, the same numeric hour label, and the same "
        "verbatim DSTFlag; RT intervals 1 through 4.",
        "Hour 24 remains on its stated delivery date.",
        "The repeated fall hour remains distinct by flag; the two occurrences are never merged.",
        "ERCOT has not officially defined these report-label semantics.",
        "HU remains an observed report type whose definition is unresolved.",
    ),
    "AGG-A": (
        "Formula: (P1 + P2 + P3 + P4) / 4.",
        "Output: hourly analytical RT SPP summary in $/MWh.",
        "ERCOT uses a plain hourly average of the four North Hub RT SPPs in a reviewed credit-risk "
        "formula (HRSAP, Protocols §16.11.4.3.3); that use does not make this output an ERCOT "
        "settlement price.",
        "All four selected RT prices must exist.",
        "Equal interval duration is not required by the arithmetic formula; the method "
        "intentionally gives each reported interval equal weight.",
    ),
    "AGG-B": (
        "Formula: Σ(P_i × duration_i) / Σ duration_i.",
        "Output: hourly analytical RT SPP summary in $/MWh.",
        "It equals AGG-A when all four supported intervals are exactly 15 minutes.",
        f"It requires verified duration evidence ({DUR_15.id}: {DUR_15.minutes} minutes for "
        f"DSTFlag {', '.join(DUR_15.flags)}).",
        "It remains an analytical summary, not an energy-weighted settlement price.",
    ),
    "CMP-A": (
        "Formula: RT analytical summary minus DAM SPP.",
        "Positive means the RT analytical summary is numerically above the DAM SPP; negative "
        "means below.",
        "Units remain $/MWh.",
        "It is not DART, settlement, P&L, savings, or forecast error.",
    ),
    "CMP-B": (
        "Formula: DAM SPP minus RT analytical summary.",
        "It is the exact sign reversal of CMP-A.",
        "It must not be simultaneously active with CMP-A for the same scope unless a later "
        "governance decision explicitly permits that.",
    ),
}
FAILURE_MODES = {
    "M1": (
        "A DSTFlag value other than N or Y: ambiguous_dst, never guessed.",
        "A day-ahead hour without its four RT intervals: incomplete, never filled.",
        "Two observations with the same revision number: a conflict the policy cannot resolve.",
    ),
    "AGG-A": (
        "Any missing or blank interval price: withheld; never averaged over fewer intervals.",
        "A stale alignment snapshot: withheld until recomputed.",
    ),
    "AGG-B": (
        "An interval without duration evidence (DSTFlag Y): duration_unsupported; 0.25 h is never "
        "substituted and there is no fallback to AGG-A.",
    ),
    "CMP-A": (
        "A missing or mismatched DAM revision, or a withheld RT summary: withheld.",
        "A different active convention: withheld; signs are never reversed silently.",
    ),
    "CMP-B": (
        "A missing or mismatched DAM revision, or a withheld RT summary: withheld.",
        "CMP-A active for the same scope: CMP-B stays approved_inactive.",
    ),
}
VALIDATION = {
    "M1": "tests/test_assumed_alignment.py (synthetic fixtures; 16 outcomes), tests/"
    "test_interval_alignment.py (candidate evidence, guards)",
    "AGG-A": "tests/test_aggregation.py (hand-worked benchmarks: 50, −5, 24.375; gating matrix)",
    "AGG-B": "tests/test_aggregation.py (equal durations = AGG-A; unequal 65; DSTFlag Y withheld)",
    "CMP-A": "tests/test_comparison.py (sign benchmarks +10, −30, +30, −30, +15, 0; 16 withheld "
    "states)",
    "CMP-B": "tests/test_comparison.py (exact reversal of every CMP-A benchmark)",
}


def review_package(data_dir: Path, record_id: str, settings: dict | None = None) -> dict:
    """Everything a reviewer needs for one record; no private reviewer name, no writes."""
    from mambo_explorer.ercot import alignment as al

    rec = record(record_id)
    st = states(data_dir, settings)[record_id]
    evidence_ids = tuple(getattr(rec, "supporting_evidence", ()))
    official = [e for e in al.EVIDENCE if e.id in evidence_ids and e.kind == "official"]
    empirical = [e for e in al.EVIDENCE if e.id in evidence_ids and e.kind == "actual-file"]
    pkg = {
        "id": rec.id,
        "version": rec.version,
        "family": FAMILY[record_id],
        "rule_or_formula": getattr(rec, "rule", None) or getattr(rec, "formula", None),
        "sign_convention": getattr(rec, "sign_convention", None),
        "scope": getattr(rec, "location", None) or _m1_scope(),
        "scope_fingerprint": rec.scope_fingerprint(),
        "dependencies": st.dependencies,
        "facts": FACTS[record_id],
        "authoritative_evidence": [
            f"{e.id}: {e.title}, {e.section}; {e.proposition}" for e in official
        ],
        "empirical_evidence": [f"{e.id}: {e.title}; {e.proposition}" for e in empirical],
        "project_assumptions": tuple(
            getattr(rec, "assumptions", ())
            or (
                getattr(rec, "unresolved_definitions", None)
                and ("The mapping is an operational assumption (see unresolved semantics).",)
            )
            or ()
        ),  # fmt: skip
        "unresolved_semantics": tuple(
            getattr(rec, "unresolved_definitions", ()) or (getattr(rec, "official_status", ""),)
        ),  # fmt: skip
        "allowed_uses": tuple(
            getattr(rec, "allowed_uses", ()) or ("Opt-in diagnostic alignment of labels under M1.",)
        ),  # fmt: skip
        "prohibited_uses": tuple(
            getattr(rec, "prohibited_uses", None)
            or getattr(rec, "prohibited_interpretations", None)
            or ()
        ),  # fmt: skip
        "limitations": [{"id": x.id, "text": x.text} for x in LIMITATIONS[record_id]],
        "limitations_version": limitations_version(record_id),
        "validation_evidence": VALIDATION[record_id],
        "known_failure_modes": FAILURE_MODES[record_id],
        "re_review_triggers": tuple(rec.re_review_triggers),
        "approval_status": st.approval_status,
        "state": st.state,
        "activation": st.activation,
        "approval_reference": st.approval_reference,
        "acknowledgment": st.acknowledgment,
        "evidence_state": st.evidence_state,
        "blockers": st.blockers,
        "downstream": downstream(record_id),
    }
    return pkg


def _m1_scope() -> str:
    s = M1.locations[0]
    return (f"{s.day_ahead_point} ({s.day_ahead_location_type}) in NP4-190-CD ↔ "
            f"{s.real_time_point}/{s.real_time_type} in NP6-905-CD")  # fmt: skip


def as_dict(x) -> dict:
    return asdict(x)
