"""Governed single-hour comparison of a day-ahead SPP with an approved RT summary (Stage 25).

Two layers, never mixed (ADR 0022):
- **candidate calculations** (`candidate`): the four researched formulas on caller-supplied
  (synthetic) prices; status `candidate_only`;
- **production comparison** (`compare`): only an approved record from
  `ercot/comparison_policy.py`, only on an `aggregation_approved_complete` Stage 24 result with
  a current aggregation snapshot, an active M1 approval, an active approval of an accepted
  aggregation record, and the selected day-ahead revision of the same source-native hour. If
  anything fails the value is withheld and every blocker is named; there is no fallback to
  another formula.

A difference of two $/MWh prices is $/MWh. Nothing here multiplies by a quantity, produces an
amount of money, aggregates across hours, or names the result with market jargon.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from mambo_explorer.ercot import aggregation as ag
from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot import assumed_alignment as aa
from mambo_explorer.ercot import prices as px
from mambo_explorer.ercot.comparison_policy import (
    FINALITY_STATUS,
    NOT_APPROVABLE,
    NOTICE,
    PROHIBITED_INTERPRETATIONS,
    RECORDS,
    UNITS,
    ComparisonRecord,
)
from mambo_explorer.ercot.m1_policy import M1

VALIDATION_VERSION = "25.1"
GOVERNED = "governed-comparison"

CANDIDATE_ONLY = "candidate_only"
COMPARISON_APPROVAL_MISSING = "comparison_approval_missing"
ALIGNMENT_APPROVAL_MISSING = "alignment_approval_missing"
AGGREGATION_APPROVAL_MISSING = "aggregation_approval_missing"
ALIGNMENT_INCOMPLETE = "alignment_incomplete"
AGGREGATION_INCOMPLETE = "aggregation_incomplete"
DAM_OBSERVATION_MISSING = "dam_observation_missing"
STALE_ALIGNMENT_SNAPSHOT = "stale_alignment_snapshot"
STALE_AGGREGATION_SNAPSHOT = "stale_aggregation_snapshot"
REVISION_UNAVAILABLE = "revision_unavailable"
CONFLICTING_REVISIONS = "conflicting_revisions"
INCOMPATIBLE_IDENTITY = "incompatible_identity"
INCOMPATIBLE_UNITS = "incompatible_units"
APPROVED_COMPLETE = "comparison_approved_complete"
STALE_COMPARISON_SNAPSHOT = "stale_comparison_snapshot"
INVALID_INPUT = "invalid_input"
UNSUPPORTED_METHOD = "unsupported_method"
STATUSES = (
    CANDIDATE_ONLY,
    COMPARISON_APPROVAL_MISSING,
    ALIGNMENT_APPROVAL_MISSING,
    AGGREGATION_APPROVAL_MISSING,
    ALIGNMENT_INCOMPLETE,
    AGGREGATION_INCOMPLETE,
    DAM_OBSERVATION_MISSING,
    STALE_ALIGNMENT_SNAPSHOT,
    STALE_AGGREGATION_SNAPSHOT,
    REVISION_UNAVAILABLE,
    CONFLICTING_REVISIONS,
    INCOMPATIBLE_IDENTITY,
    INCOMPATIBLE_UNITS,
    APPROVED_COMPLETE,
    STALE_COMPARISON_SNAPSHOT,
    INVALID_INPUT,
    UNSUPPORTED_METHOD,
)
_PRECEDENCE = (
    UNSUPPORTED_METHOD,
    INVALID_INPUT,
    ALIGNMENT_APPROVAL_MISSING,
    AGGREGATION_APPROVAL_MISSING,
    COMPARISON_APPROVAL_MISSING,
    REVISION_UNAVAILABLE,
    CONFLICTING_REVISIONS,
    ALIGNMENT_INCOMPLETE,
    STALE_ALIGNMENT_SNAPSHOT,
    AGGREGATION_INCOMPLETE,
    STALE_AGGREGATION_SNAPSHOT,
    DAM_OBSERVATION_MISSING,
    INCOMPATIBLE_IDENTITY,
    INCOMPATIBLE_UNITS,
)
_FROM_AGGREGATION = {
    ag.ALIGNMENT_APPROVAL_MISSING: ALIGNMENT_APPROVAL_MISSING,
    ag.APPROVAL_MISSING: AGGREGATION_APPROVAL_MISSING,
    ag.REVISION_UNAVAILABLE: REVISION_UNAVAILABLE,
    ag.CONFLICTING_REVISIONS: CONFLICTING_REVISIONS,
    ag.ALIGNMENT_INCOMPLETE: ALIGNMENT_INCOMPLETE,
    ag.STALE_SNAPSHOT: STALE_ALIGNMENT_SNAPSHOT,
}

RT_FIRST = "rt-minus-dam"
DAM_FIRST = "dam-minus-rt"
ABSOLUTE = "absolute-difference"
PERCENTAGE = "percentage-difference"
CANDIDATES = (RT_FIRST, DAM_FIRST, ABSOLUTE, PERCENTAGE)

# Dimensional and semantic analysis (docs/comparison-evidence.md §3).
DIMENSIONS = (
    {
        "Candidate": "CMP-A. RT summary minus DAM",
        "Formula": "S_RT − P_DAM",
        "Units": "$/MWh − $/MWh = $/MWh",
        "Sign": "positive: the RT summary is higher; negative: lower; 0: equal",
        "Status": "approvable record CMP-A 1.0.0",
    },
    {
        "Candidate": "CMP-B. DAM minus RT summary",
        "Formula": "P_DAM − S_RT",
        "Units": "$/MWh",
        "Sign": "the exact reversal of CMP-A: positive when the DAM price is higher",
        "Status": "approvable record CMP-B 1.0.0",
    },
    {
        "Candidate": "CMP-C. Absolute difference",
        "Formula": "|S_RT − P_DAM|",
        "Units": "$/MWh",
        "Sign": "none: the direction is discarded",
        "Status": "candidate only; not approvable in this stage",
    },
    {
        "Candidate": "CMP-D. Percentage difference",
        "Formula": "(S_RT − P_DAM) / P_DAM × 100",
        "Units": "% of the DAM price (dimensionless)",
        "Sign": "flips meaning when P_DAM is negative; undefined at P_DAM = 0",
        "Status": "candidate only; not approvable in this stage",
    },
)


class ComparisonInputError(ValueError):
    pass


def _dec(text) -> Decimal:
    try:
        value = Decimal(str(text).strip())
    except (InvalidOperation, ValueError):
        raise ComparisonInputError(f"not a number: {text!r}") from None
    if not value.is_finite():
        raise ComparisonInputError(f"not a finite number: {text!r}")
    return value


def difference_rt_first(rt_summary, dam_price) -> Decimal:
    return _dec(rt_summary) - _dec(dam_price)


def difference_dam_first(rt_summary, dam_price) -> Decimal:
    return _dec(dam_price) - _dec(rt_summary)


def absolute_difference(rt_summary, dam_price) -> Decimal:
    return abs(_dec(rt_summary) - _dec(dam_price))


def percentage_difference(rt_summary, dam_price) -> Decimal | None:
    """Candidate only (never production). None when the DAM price is zero (undefined)."""
    dam = _dec(dam_price)
    if dam == 0:
        return None
    return (_dec(rt_summary) - dam) / dam * Decimal(100)


@dataclass(frozen=True)
class CandidateResult:
    status: str  # always candidate_only
    method: str
    output: str | None
    units: str
    note: str


def candidate(method: str, rt_summary, dam_price) -> CandidateResult:
    """A researched formula on caller-supplied (synthetic) prices. Never production output."""
    if method == RT_FIRST:
        return CandidateResult(
            CANDIDATE_ONLY, method, _fmt(difference_rt_first(rt_summary, dam_price)), UNITS, ""
        )
    if method == DAM_FIRST:
        return CandidateResult(
            CANDIDATE_ONLY, method, _fmt(difference_dam_first(rt_summary, dam_price)), UNITS, ""
        )
    if method == ABSOLUTE:
        out = absolute_difference(rt_summary, dam_price)
        return CandidateResult(CANDIDATE_ONLY, method, _fmt(out), UNITS, "direction discarded")
    if method == PERCENTAGE:
        out = percentage_difference(rt_summary, dam_price)
        if out is None:
            return CandidateResult(CANDIDATE_ONLY, method, None, "%", "undefined: DAM price is 0")
        note = "denominator negative: sign reads backwards" if _dec(dam_price) < 0 else ""
        return CandidateResult(CANDIDATE_ONLY, method, _fmt(out), "%", note)
    raise ComparisonInputError(f"unknown candidate method {method!r}")


def _fmt(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


# --- production -------------------------------------------------------------------------------


@dataclass(frozen=True)
class DamInput:
    identity: dict  # DeliveryDate, HourEnding, SettlementPoint, LocationType, DSTFlag
    revision: int
    doc_id: str
    price_raw: str | None
    unit: str | None
    publish_time_raw: str | None
    retrieved_at: str | None
    source: str = px.SOURCE
    dataset: str = px.DATASET


@dataclass(frozen=True)
class ComparisonResult:
    status: str
    blockers: tuple[str, ...]
    method_id: str | None
    method_version: str | None
    output_name: str | None
    formula: str | None
    formula_version: str | None
    sign_convention: str | None
    location: str | None
    m1: str
    aggregation: str | None  # "AGG-A 1.0.0"
    approvals: dict  # M1 / aggregation / comparison approval status and reference
    revision_policy: str
    dam_identity: dict
    dam_revision: dict | None  # revision, doc_id, published, retrieved
    aggregation_snapshot: str | None
    alignment_snapshot: str | None
    rt_intervals: tuple[dict, ...]
    dam_price: str | None
    rt_summary: str | None
    output: str | None  # only for comparison_approved_complete
    units: str
    finality_status: str
    validation: tuple[tuple[str, bool, str], ...]
    limitations: tuple[str, ...]
    prohibited_interpretations: tuple[str, ...]
    notice: str


def _record(method_id: str) -> ComparisonRecord | None:
    return next((r for r in RECORDS if r.id == method_id), None)


def _state(approval: ap.Approval | None) -> str:
    return f"{approval.status} ({approval.reference or 'none'})" if approval else "not supplied"


def compare(
    method_id: str,
    *,
    mode: str,
    alignment: aa.AssumedResult,
    aggregation: ag.AggregationResult,
    aggregation_snapshot: dict | None,
    aggregation_snapshot_state: str | None,
    dam: DamInput | None,
    m1_approval: ap.Approval | None,
    aggregation_approval: ap.Approval | None,
    comparison_approval: ap.Approval | None,
) -> ComparisonResult:
    """Production comparison of one governed hour (or a withheld result with every blocker)."""
    record = _record(method_id)
    checks: list[tuple[str, bool, str]] = []
    blockers: list[tuple[str, str]] = []

    def check(name: str, ok: bool, detail: str, status: str) -> bool:
        checks.append((name, ok, detail))
        if not ok:
            blockers.append((status, f"{name}: {detail}"))
        return ok

    if record is None:
        why = NOT_APPROVABLE.get(method_id, "no comparison record with this identifier")
        check("method", False, why, UNSUPPORTED_METHOD)
    elif record.status != "current":
        check("method", False, f"record {record.id} is {record.status}", UNSUPPORTED_METHOD)
    else:
        check("method", True, f"{record.id} {record.version}", UNSUPPORTED_METHOD)
        problems = record.sign_problems()
        check(
            "sign metadata",
            not problems,
            "; ".join(problems) or record.sign_convention,
            INVALID_INPUT,
        )
    check(
        "comparison mode",
        mode == GOVERNED,
        "governed comparison selected explicitly" if mode == GOVERNED else "not selected",
        INVALID_INPUT,
    )

    # 1. alignment (M1) and its approval
    governed = alignment.alignment_basis == aa.ASSUMPTION
    check(
        "alignment basis",
        governed,
        "M1 selected" if governed else "authoritative-only: no comparison",
        ALIGNMENT_APPROVAL_MISSING,
    )
    m1_ok = bool(
        m1_approval and m1_approval.active and m1_approval.assumption_version == M1.version
    )
    check("M1 approval", m1_ok, _state(m1_approval), ALIGNMENT_APPROVAL_MISSING)

    # 2. aggregation record accepted by this comparison, and its approval
    agg_key = None
    if aggregation.method_id:
        from mambo_explorer.ercot.aggregation_policy import record as agg_record

        r = agg_record(aggregation.method_id)
        agg_key = f"{r.id}@{r.version}:{r.scope_fingerprint()}"
    if record is not None:
        accepted = agg_key in record.aggregations
        check(
            "aggregation record",
            accepted,
            agg_key or "no aggregation record",
            AGGREGATION_APPROVAL_MISSING,
        )
        m1_key = f"{M1.id}@{M1.version}:{M1.scope_fingerprint()}"
        check(
            "M1 dependency",
            record.depends_on == m1_key,
            record.depends_on,
            ALIGNMENT_APPROVAL_MISSING,
        )
    agg_ok = bool(
        aggregation_approval
        and aggregation_approval.active
        and aggregation_approval.assumption_id == aggregation.method_id
    )
    check(
        "aggregation approval", agg_ok, _state(aggregation_approval), AGGREGATION_APPROVAL_MISSING
    )

    # 3. the comparison approval
    if record is not None:
        cmp_ok = bool(
            comparison_approval
            and comparison_approval.active
            and comparison_approval.assumption_id == record.id
            and comparison_approval.assumption_version == record.version
        )
        check(
            "comparison approval", cmp_ok, _state(comparison_approval), COMPARISON_APPROVAL_MISSING
        )
        check(
            "revision policy",
            aggregation.revision_policy in record.revision_policies,
            aggregation.revision_policy,
            REVISION_UNAVAILABLE,
        )

    # 4. the approved RT summary and its snapshot
    agg_complete = aggregation.status == ag.APPROVED_COMPLETE
    if not agg_complete:
        mapped = _FROM_AGGREGATION.get(aggregation.status, AGGREGATION_INCOMPLETE)
        check(
            "RT aggregation",
            False,
            f"{aggregation.status}: " + "; ".join(aggregation.blockers),
            mapped,
        )
        if mapped != AGGREGATION_INCOMPLETE:
            blockers.append(
                (AGGREGATION_INCOMPLETE, "RT aggregation: no approved complete summary")
            )
    else:
        check(
            "RT aggregation",
            True,
            f"{aggregation.output} {aggregation.units}",
            AGGREGATION_INCOMPLETE,
        )
    snap_ok = bool(
        aggregation_snapshot
        and aggregation_snapshot_state == "current"
        and aggregation_snapshot.get("status") == ag.APPROVED_COMPLETE
        and aggregation_snapshot.get("output") == aggregation.output
        and aggregation_snapshot.get("context", {}).get("intervals")
        == [
            [i["DeliveryInterval"], i["DSTFlag"], i["revision"], i["doc_id"]]
            for i in aggregation.intervals
        ]
    )
    check(
        "aggregation snapshot",
        snap_ok,
        _snapshot_detail(aggregation_snapshot, aggregation_snapshot_state, aggregation),
        STALE_AGGREGATION_SNAPSHOT,
    )

    # 5. the day-ahead observation
    dam_price = None
    dam_rev = None
    if dam is None or not (dam.price_raw or "").strip():
        check(
            "DAM observation",
            False,
            "no selected day-ahead price for this hour",
            DAM_OBSERVATION_MISSING,
        )
    else:
        dam_rev = {
            "revision": dam.revision,
            "doc_id": dam.doc_id,
            "published": dam.publish_time_raw,
            "retrieved": dam.retrieved_at,
        }
        try:
            dam_price = _fmt(_dec(dam.price_raw))
            check("DAM observation", True, f"{dam_price} {dam.unit}", DAM_OBSERVATION_MISSING)
        except ComparisonInputError as exc:
            check("DAM observation", False, str(exc), INVALID_INPUT)
        same = (
            dam.identity == alignment.dam_identity == aggregation.dam_identity
            and dam.identity.get("SettlementPoint") == px.LOCATION
            and dam.identity.get("LocationType") == px.LOCATION_TYPE
        )
        check("identity", same, "day-ahead hour, alignment, and aggregation agree" if same else
              f"{dam.identity} vs {aggregation.dam_identity}", INCOMPATIBLE_IDENTITY)  # fmt: skip
        sel = alignment.dam_revision or {}
        rev_same = (sel.get("revision"), sel.get("doc_id")) == (dam.revision, dam.doc_id)
        check(
            "DAM revision",
            rev_same,
            f"selected {sel.get('revision')} / used {dam.revision}",
            INCOMPATIBLE_IDENTITY,
        )
        rt_points = {
            (i["SettlementPointName"], i["SettlementPointType"]) for i in aggregation.intervals
        }
        if record is not None and aggregation.intervals:
            check(
                "RT location",
                rt_points == {("HB_NORTH", "HU")},
                str(sorted(rt_points)),
                INCOMPATIBLE_IDENTITY,
            )
        units_ok = dam.unit == UNITS and aggregation.units == UNITS
        check(
            "units", units_ok, f"DAM {dam.unit}; RT summary {aggregation.units}", INCOMPATIBLE_UNITS
        )

    output = None
    order = {s: n for n, s in enumerate(STATUSES)}
    if not blockers and record is not None and dam_price is not None and agg_complete:
        value = record.rt_coefficient * _dec(aggregation.output) + record.dam_coefficient * _dec(
            dam_price
        )
        output = _fmt(value)
        status = APPROVED_COMPLETE
    elif not blockers:
        status = INVALID_INPUT
        blockers.append((INVALID_INPUT, "no inputs to compare"))
    else:
        status = min((s for s, _ in blockers), key=lambda s: (_PRECEDENCE.index(s), order[s]))

    return ComparisonResult(
        status=status,
        blockers=tuple(dict.fromkeys(b for _, b in blockers)),
        method_id=record.id if record else None,
        method_version=record.version if record else None,
        output_name=record.output_name if record else None,
        formula=record.formula if record else None,
        formula_version=record.formula_version if record else None,
        sign_convention=record.sign_convention if record else None,
        location=record.location if record else None,
        m1=f"{M1.id} {M1.version}",
        aggregation=f"{aggregation.method_id} {aggregation.method_version}"
        if aggregation.method_id
        else None,
        approvals={
            "M1": _state(m1_approval),
            "aggregation": _state(aggregation_approval),
            "comparison": _state(comparison_approval),
        },
        revision_policy=aggregation.revision_policy,
        dam_identity=dam.identity if dam else aggregation.dam_identity,
        dam_revision=dam_rev,
        aggregation_snapshot=aggregation_snapshot["snapshot_id"] if aggregation_snapshot else None,
        alignment_snapshot=aggregation.alignment_snapshot,
        rt_intervals=aggregation.intervals,
        dam_price=dam_price,
        rt_summary=aggregation.output,
        output=output,
        units=UNITS,
        finality_status=FINALITY_STATUS,
        validation=tuple(checks),
        limitations=record.limitations if record else (),
        prohibited_interpretations=PROHIBITED_INTERPRETATIONS,
        notice=NOTICE,
    )


def _snapshot_detail(snap: dict | None, state: str | None, aggregation) -> str:
    """Why an aggregation snapshot does or does not support the comparison (browser finding:
    "is current" alone read as fine while the snapshot recorded a withheld summary)."""
    if not snap:
        return "no aggregation snapshot of this hour; record one first"
    sid = snap["snapshot_id"]
    if state != "current":
        return f"{sid} is {state}; record a new one"
    if snap.get("status") != ag.APPROVED_COMPLETE:
        return (
            f"{sid} is current but records {snap.get('status')}, not an approved complete summary"
        )
    if snap.get("output") != aggregation.output:
        return f"{sid} records {snap.get('output')}, not the current summary {aggregation.output}"
    intervals = [
        [i["DeliveryInterval"], i["DSTFlag"], i["revision"], i["doc_id"]]
        for i in aggregation.intervals
    ]
    if snap.get("context", {}).get("intervals") != intervals:
        return f"{sid} records other interval revisions than the current summary"
    return f"{sid} is current and matches the approved summary"


def store_dam_lookup(data_dir: Path) -> Callable[[dict, dict | None], DamInput | None]:
    """The selected day-ahead revision of one source-native hour, with its provenance."""
    target = px.store(data_dir)

    def lookup(identity: dict, selected: dict | None) -> DamInput | None:
        if not selected or not target.committed_files("observations"):
            return None
        with target.query() as con:
            rows = con.execute(
                "SELECT value_raw, unit, publish_time_raw, CAST(retrieved_at_utc AS VARCHAR) "
                "FROM observations WHERE delivery_date_raw = ? AND hour_ending = ? AND "
                "dst_flag = ? AND location = ? AND location_type = ? AND revision = ? AND "
                "doc_id = ?",
                [
                    identity["DeliveryDate"], identity["HourEnding"], identity["DSTFlag"],
                    identity["SettlementPoint"], identity["LocationType"], selected["revision"],
                    selected["doc_id"],
                ],
            ).fetchall()  # fmt: skip
        if len(rows) != 1:
            return None
        raw, unit, pub, ret = rows[0]
        return DamInput(identity, selected["revision"], selected["doc_id"], raw, unit, pub, ret)

    return lookup


# --- comparison snapshots ---------------------------------------------------------------
SNAPSHOT_DIR = "comparison"
SNAPSHOT_FILE = "snapshots.jsonl"


def _sha(payload) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def context(result: ComparisonResult, aggregation_snapshot_state: str | None) -> dict:
    record = _record(result.method_id or "")
    agg = None
    if result.aggregation:
        from mambo_explorer.ercot.aggregation_policy import record as agg_record

        r = agg_record(result.aggregation.split()[0])
        agg = f"{r.id}@{r.version}:{r.scope_fingerprint()}"
    return {
        "method": f"{record.id}@{record.version}:{record.scope_fingerprint()}" if record else None,
        "dam_identity": result.dam_identity,
        "dam_revision": [result.dam_revision.get("revision"), result.dam_revision.get("doc_id")]
        if result.dam_revision
        else None,
        "aggregation_snapshot": f"{result.aggregation_snapshot}:{aggregation_snapshot_state}",
        "alignment_snapshot": result.alignment_snapshot,
        "rt_intervals": [
            [i["DeliveryInterval"], i["DSTFlag"], i["revision"], i["doc_id"]]
            for i in result.rt_intervals
        ],
        "m1": f"{M1.id}@{M1.version}:{M1.scope_fingerprint()}",
        "aggregation": agg,
        "approvals": result.approvals,
        "revision_policy": result.revision_policy,
        "formula_version": result.formula_version,
        "validation_version": VALIDATION_VERSION,
    }


def snapshot(result: ComparisonResult, ctx: dict, recorded_at_utc: str) -> dict:
    return {
        "snapshot_id": "cmp-" + _sha([ctx, result.status, result.output, recorded_at_utc]),
        "recorded_at_utc": recorded_at_utc,
        "context": ctx,
        "status": result.status,
        "dam_price": result.dam_price,
        "rt_summary": result.rt_summary,
        "output": result.output,
        "units": result.units,
        "output_name": result.output_name,
        "sign_convention": result.sign_convention,
        "finality_status": result.finality_status,
        "prohibited_interpretations": list(result.prohibited_interpretations),
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


def snapshot_key(ctx: dict) -> str:
    return _sha(
        [(ctx.get("method") or "").split(":")[0], ctx["dam_identity"], ctx["revision_policy"]]
    )


def snapshot_states(
    snaps: Sequence[dict], current_contexts: dict
) -> list[tuple[dict, str, list[str]]]:
    """(snapshot, state, reasons): current, stale_comparison_snapshot, superseded, unknown."""
    latest: dict[str, str] = {}
    for s in snaps:
        latest[snapshot_key(s["context"])] = s["snapshot_id"]
    out = []
    for s in snaps:
        key = snapshot_key(s["context"])
        if latest[key] != s["snapshot_id"]:
            out.append((s, "superseded", ["a later snapshot exists for the same hour and method"]))
            continue
        now = current_contexts.get(key)
        if now is None:
            out.append((s, "unknown", ["the hour was not recomputed"]))
            continue
        changed = [k for k in sorted(now) if now[k] != s["context"].get(k)]
        out.append(
            (
                s,
                STALE_COMPARISON_SNAPSHOT if changed else "current",
                [f"{k} changed" for k in changed],
            )
        )
    return out


def as_dict(result) -> dict:
    return asdict(result)
