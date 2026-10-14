"""Governed hourly summaries of M1-aligned real-time SPPs (Stage 24, ADR 0021).

Two layers, never mixed:
- **candidate calculations** (`candidate`): the four researched formulas on caller-supplied
  (synthetic) numbers, for diagnostics and benchmarks; status `candidate_only`;
- **production aggregation** (`aggregate`): only an approved record from
  `ercot/aggregation_policy.py`, only on one current Stage 23 alignment snapshot under an
  active M1 approval, with every prerequisite checked. If any fails, the value is withheld and
  every blocker is named; there is no fallback to another method.

Arithmetic uses Decimal on the prices as published (`value_raw`), so results are exact. Nothing
here compares with a day-ahead price, computes a difference of prices, converts a label to a
clock time, or labels a summary as final or as an ERCOT price.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from mambo_explorer.ercot import approvals as ap
from mambo_explorer.ercot import assumed_alignment as aa
from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.aggregation_policy import (
    ARITHMETIC,
    DURATION_WEIGHTED,
    LIMITATION_BANNER,
    NOT_APPROVABLE,
    PROHIBITED_INTERPRETATIONS,
    RECORDS,
    UNITS,
    AggregationRecord,
)
from mambo_explorer.ercot.m1_policy import M1

VALIDATION_VERSION = "24.1"

CANDIDATE_ONLY = "candidate_only"
APPROVAL_MISSING = "approval_missing"
ALIGNMENT_APPROVAL_MISSING = "alignment_approval_missing"
ALIGNMENT_INCOMPLETE = "alignment_incomplete"
REVISION_UNAVAILABLE = "revision_unavailable"
CONFLICTING_REVISIONS = "conflicting_revisions"
DURATION_UNSUPPORTED = "duration_unsupported"
APPROVED_COMPLETE = "aggregation_approved_complete"
STALE_SNAPSHOT = "stale_snapshot"
INVALID_INPUT = "invalid_input"
UNSUPPORTED_METHOD = "unsupported_method"
STATUSES = (
    CANDIDATE_ONLY,
    APPROVAL_MISSING,
    ALIGNMENT_APPROVAL_MISSING,
    ALIGNMENT_INCOMPLETE,
    REVISION_UNAVAILABLE,
    CONFLICTING_REVISIONS,
    DURATION_UNSUPPORTED,
    APPROVED_COMPLETE,
    STALE_SNAPSHOT,
    INVALID_INPUT,
    UNSUPPORTED_METHOD,
)

ENERGY_WEIGHTED = "energy-weighted-price"
SETTLEMENT_AMOUNT = "settlement-amount"
CANDIDATES = (ARITHMETIC, DURATION_WEIGHTED, ENERGY_WEIGHTED, SETTLEMENT_AMOUNT)

# Dimensional analysis (docs/aggregation-evidence.md §3).
DIMENSIONS = (
    {
        "Candidate": "A. Arithmetic mean",
        "Formula": "(P1 + P2 + P3 + P4) / 4",
        "Inputs": "Pi in $/MWh (four interval prices)",
        "Denominator": "a count (4); dimensionless",
        "Output": "$/MWh: a price summary",
        "Interpretation": "the typical posted price level of the hour; equal weight per interval",
    },
    {
        "Candidate": "B. Duration-weighted mean",
        "Formula": "Σ(Pi × Di) / ΣDi",
        "Inputs": "Pi in $/MWh; Di in hours (elapsed time, verified)",
        "Denominator": "hours",
        "Output": "$/MWh: a price summary weighted by elapsed time",
        "Interpretation": "equals A when every Di is equal; still not energy-weighted",
    },
    {
        "Candidate": "C. Energy-weighted price",
        "Formula": "Σ(Pi × Ei) / ΣEi",
        "Inputs": "Pi in $/MWh; Ei in MWh with stated signs (settlement quantities)",
        "Denominator": "MWh; undefined when ΣEi = 0",
        "Output": "$/MWh: the effective price of a quantity",
        "Interpretation": "needs quantities this application does not have; not implemented",
    },
    {
        "Candidate": "D. Settlement amount",
        "Formula": "Σ(Pi × Ei)",
        "Inputs": "Pi in $/MWh; Ei in MWh (MW × hours) with sign conventions",
        "Denominator": "none",
        "Output": "$: a currency amount, not a price",
        "Interpretation": "omits every other charge of Protocols §6.6; not implemented",
    },
)


class AggregationInputError(ValueError):
    pass


def _dec(text) -> Decimal:
    try:
        value = Decimal(str(text).strip())
    except (InvalidOperation, ValueError):
        raise AggregationInputError(f"not a number: {text!r}") from None
    if not value.is_finite():
        raise AggregationInputError(f"not a finite number: {text!r}")
    return value


def _clean(values: Sequence, name: str) -> list[Decimal]:
    out = [_dec(v) for v in values]
    if not out:
        raise AggregationInputError(f"no {name}")
    return out


def arithmetic_mean(prices: Sequence) -> Decimal:
    p = _clean(prices, "prices")
    return sum(p) / Decimal(len(p))


def duration_weighted_mean(prices: Sequence, durations_hours: Sequence) -> Decimal:
    p, d = _clean(prices, "prices"), _clean(durations_hours, "durations")
    if len(p) != len(d):
        raise AggregationInputError("each price needs exactly one duration")
    if any(x <= 0 for x in d):
        raise AggregationInputError("durations must be positive")
    return sum(pi * di for pi, di in zip(p, d, strict=True)) / sum(d)


def energy_weighted_price(prices: Sequence, energies_mwh: Sequence) -> Decimal | None:
    """Synthetic diagnostics only. None when the total energy is zero (undefined)."""
    p, e = _clean(prices, "prices"), _clean(energies_mwh, "energies")
    if len(p) != len(e):
        raise AggregationInputError("each price needs exactly one energy quantity")
    total = sum(e)
    if total == 0:
        return None
    return sum(pi * ei for pi, ei in zip(p, e, strict=True)) / total


def settlement_amount(prices: Sequence, energies_mwh: Sequence) -> Decimal:
    """Synthetic diagnostics only: a currency amount ($), not a price."""
    p, e = _clean(prices, "prices"), _clean(energies_mwh, "energies")
    if len(p) != len(e):
        raise AggregationInputError("each price needs exactly one energy quantity")
    return sum(pi * ei for pi, ei in zip(p, e, strict=True))


@dataclass(frozen=True)
class CandidateResult:
    status: str  # always candidate_only
    method: str
    output: str | None
    units: str
    note: str


def candidate(method: str, prices, durations=None, energies=None) -> CandidateResult:
    """A researched formula on caller-supplied (synthetic) inputs. Never production output."""
    if method == ARITHMETIC:
        return CandidateResult(CANDIDATE_ONLY, method, _fmt(arithmetic_mean(prices)), UNITS, "")
    if method == DURATION_WEIGHTED:
        out = duration_weighted_mean(prices, durations or ())
        return CandidateResult(CANDIDATE_ONLY, method, _fmt(out), UNITS, "")
    if method == ENERGY_WEIGHTED:
        out = energy_weighted_price(prices, energies or ())
        if out is None:
            return CandidateResult(
                CANDIDATE_ONLY, method, None, UNITS, "undefined: total energy is zero"
            )
        return CandidateResult(CANDIDATE_ONLY, method, _fmt(out), UNITS, "")
    if method == SETTLEMENT_AMOUNT:
        out = settlement_amount(prices, energies or ())
        return CandidateResult(CANDIDATE_ONLY, method, _fmt(out), "$", "an amount, not a price")
    raise AggregationInputError(f"unknown candidate method {method!r}")


def _fmt(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


# --- production ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregationResult:
    status: str
    blockers: tuple[str, ...]
    method_id: str | None
    method_version: str | None
    method: str | None
    output_name: str | None
    formula: str | None
    formula_version: str | None
    m1: str
    m1_approval: str
    aggregation_approval: str
    alignment_basis: str
    alignment_status: str
    alignment_snapshot: str | None
    revision_policy: str
    dam_identity: dict
    intervals: tuple[dict, ...]  # identities with selected revision and document
    duration_evidence: dict | None
    input_prices: tuple[str, ...]  # as published, in interval order, when all were found
    output: str | None  # only for aggregation_approved_complete
    units: str
    validation: tuple[tuple[str, bool, str], ...]
    limitations: tuple[str, ...]
    prohibited_interpretations: tuple[str, ...]
    banner: str


def _record(method_id: str) -> AggregationRecord | None:
    return next((r for r in RECORDS if r.id == method_id), None)


def _durations(record: AggregationRecord, intervals: Sequence[dict]) -> tuple[list, str | None]:
    ev = record.duration_evidence
    if ev is None:
        return [], "this method has no duration evidence"
    uncovered = [i for i in intervals if i["DSTFlag"] not in ev.flags]
    if uncovered:
        labels = ", ".join(f"I{i['DeliveryInterval']} {i['DSTFlag']}" for i in uncovered)
        return [], f"{ev.id} does not cover DSTFlag of {labels}; no duration is substituted"
    return [Decimal(ev.minutes) / Decimal(60)] * len(intervals), None


def aggregate(
    method_id: str,
    alignment: aa.AssumedResult,
    *,
    m1_approval: ap.Approval | None,
    aggregation_approval: ap.Approval | None,
    alignment_snapshot: dict | None,
    alignment_snapshot_state: str | None,
    price_lookup: Callable[[dict], str | None],
) -> AggregationResult:
    """Production aggregation of one hour under an approved record (or a withheld result)."""
    record = _record(method_id)
    checks: list[tuple[str, bool, str]] = []
    blockers: list[tuple[str, str]] = []

    def check(name: str, ok: bool, detail: str, status: str) -> bool:
        checks.append((name, ok, detail))
        if not ok:
            blockers.append((status, f"{name}: {detail}"))
        return ok

    if record is None:
        why = NOT_APPROVABLE.get(method_id, "no aggregation record with this identifier")
        check("method", False, why, UNSUPPORTED_METHOD)
    elif record.status != "current":
        check("method", False, f"record {record.id} is {record.status}", UNSUPPORTED_METHOD)
    else:
        check("method", True, f"{record.id} {record.version} ({record.method})", UNSUPPORTED_METHOD)

    governed = alignment.alignment_basis == aa.ASSUMPTION
    check(
        "alignment basis",
        governed,
        "M1 selected explicitly" if governed else "authoritative-only: aggregation never runs",
        ALIGNMENT_APPROVAL_MISSING,
    )
    m1_ok = bool(
        m1_approval and m1_approval.active and m1_approval.assumption_version == M1.version
    )
    check(
        "M1 approval",
        m1_ok,
        f"{m1_approval.status} ({m1_approval.reference or 'none'})"
        if m1_approval
        else "not supplied",
        ALIGNMENT_APPROVAL_MISSING,
    )
    if record is not None:
        dep_ok = record.depends_on == f"{M1.id}@{M1.version}:{M1.scope_fingerprint()}"
        check("M1 version and scope", dep_ok, record.depends_on, ALIGNMENT_APPROVAL_MISSING)
        agg_ok = bool(
            aggregation_approval
            and aggregation_approval.assumption_id == record.id
            and aggregation_approval.active
            and aggregation_approval.assumption_version == record.version
        )
        check(
            "aggregation approval",
            agg_ok,
            (
                f"{aggregation_approval.status} ({aggregation_approval.reference or 'none'})"
                if aggregation_approval and aggregation_approval.assumption_id == record.id
                else f"no approval status for {record.id}"
            ),
            APPROVAL_MISSING,
        )
        policy_ok = alignment.revision_policy in record.revision_policies
        check("revision policy", policy_ok, alignment.revision_policy, REVISION_UNAVAILABLE)

    conflict = alignment.alignment_status == aa.CONFLICTING_REVISIONS or bool(
        alignment.duplicate_intervals
    )
    check(
        "revision conflicts",
        not conflict,
        "; ".join(alignment.duplicate_intervals) or "none",
        CONFLICTING_REVISIONS,
    )
    complete = (
        alignment.completeness_status == aa.COMPLETE
        and alignment.expected_intervals == M1.expected_intervals
    )
    check(
        "M1 alignment",
        complete,
        f"{alignment.alignment_status} / {alignment.completeness_status}",
        ALIGNMENT_INCOMPLETE,
    )

    intervals = tuple(
        {
            k: m[k]
            for k in (
                "DeliveryDate",
                "DeliveryHour",
                "DeliveryInterval",
                "SettlementPointName",
                "SettlementPointType",
                "DSTFlag",
                "revision",
                "doc_id",
            )
        }  # fmt: skip
        for m in alignment.matched
    )
    snap_id = alignment_snapshot["snapshot_id"] if alignment_snapshot else None
    selected = [
        (i["DeliveryHour"], i["DeliveryInterval"], i["DSTFlag"], i["revision"], i["doc_id"])
        for i in intervals
    ]
    in_snapshot = (
        [
            (s["DeliveryHour"], s["DeliveryInterval"], s["DSTFlag"], s["revision"], s["doc_id"])
            for s in alignment_snapshot["selected_real_time"]
        ]
        if alignment_snapshot
        else None
    )
    snap_ok = bool(
        alignment_snapshot
        and alignment_snapshot_state == "current"
        and in_snapshot == selected
        and alignment_snapshot.get("context", {}).get("revision_policy")
        == alignment.revision_policy
    )
    check(
        "alignment snapshot",
        snap_ok,
        (
            f"{snap_id} is {alignment_snapshot_state}"
            + (
                ""
                if in_snapshot == selected
                else "; its revisions differ from the current alignment"
            )
            if alignment_snapshot
            else "no current alignment snapshot of this hour; record one first"
        ),
        STALE_SNAPSHOT,
    )

    duration_doc = None
    durations: list = []
    if record is not None and record.method == DURATION_WEIGHTED:
        durations, problem = _durations(record, intervals) if intervals else ([], "no intervals")
        ev = record.duration_evidence
        duration_doc = {
            "id": ev.id,
            "minutes": ev.minutes,
            "flags": list(ev.flags),
            "sources": list(ev.sources),
        }
        check("duration evidence", problem is None, problem or ev.statement, DURATION_UNSUPPORTED)

    prices: list[str] = []
    if complete and intervals:
        for i in intervals:
            raw = price_lookup(i)
            if raw is None or not str(raw).strip():
                check(
                    "interval prices",
                    False,
                    f"no price for interval {i['DeliveryInterval']}",
                    ALIGNMENT_INCOMPLETE,
                )
                prices = []
                break
            prices.append(str(raw).strip())
        else:
            try:
                [_dec(x) for x in prices]
                check("interval prices", True, f"{len(prices)} prices as published", INVALID_INPUT)
            except AggregationInputError as exc:
                check("interval prices", False, str(exc), INVALID_INPUT)
                prices = []

    output = None
    order = {s: n for n, s in enumerate(STATUSES)}
    if not blockers and record is not None and prices:
        value = (
            arithmetic_mean(prices)
            if record.method == ARITHMETIC
            else duration_weighted_mean(prices, durations)
        )
        output = _fmt(value)
        status = APPROVED_COMPLETE
    elif not blockers:
        status = INVALID_INPUT
        blockers.append((INVALID_INPUT, "no inputs to aggregate"))
    else:
        # the most fundamental blocker names the status; every blocker is reported
        precedence = (
            UNSUPPORTED_METHOD, ALIGNMENT_APPROVAL_MISSING, APPROVAL_MISSING, REVISION_UNAVAILABLE,
            CONFLICTING_REVISIONS, ALIGNMENT_INCOMPLETE, STALE_SNAPSHOT, DURATION_UNSUPPORTED,
            INVALID_INPUT,
        )  # fmt: skip
        status = min((s for s, _ in blockers), key=lambda s: (precedence.index(s), order[s]))

    return AggregationResult(
        status=status,
        blockers=tuple(b for _, b in blockers),
        method_id=record.id if record else None,
        method_version=record.version if record else None,
        method=record.method if record else method_id,
        output_name=record.output_name if record else None,
        formula=record.formula if record else None,
        formula_version=record.formula_version if record else None,
        m1=f"{M1.id} {M1.version}",
        m1_approval=f"{m1_approval.status} ({m1_approval.reference or 'none'})"
        if m1_approval
        else "not supplied",
        aggregation_approval=(
            f"{aggregation_approval.status} ({aggregation_approval.reference or 'none'})"
            if aggregation_approval
            else "not supplied"
        ),
        alignment_basis=alignment.alignment_basis,
        alignment_status=alignment.alignment_status,
        alignment_snapshot=snap_id,
        revision_policy=alignment.revision_policy,
        dam_identity=alignment.dam_identity,
        intervals=intervals,
        duration_evidence=duration_doc,
        input_prices=tuple(prices),
        output=output,
        units=UNITS,
        validation=tuple(checks),
        limitations=(record.limitations if record else ()) + (VALIDATION_NOTE,),
        prohibited_interpretations=PROHIBITED_INTERPRETATIONS,
        banner=LIMITATION_BANNER,
    )


VALIDATION_NOTE = (
    "A complete summary is not a final ERCOT price: collection coverage, M1 alignment, input "
    "completeness, revision availability, finality, and correction coverage are separate."
)


def store_price_lookup(data_dir: Path) -> Callable[[dict], str | None]:
    """Looks up the published price text of exactly one selected interval revision."""
    target = rt.store(data_dir)

    def lookup(i: dict) -> str | None:
        if not target.committed_files("observations"):
            return None
        with target.query() as con:
            rows = con.execute(
                "SELECT value_raw FROM observations WHERE delivery_date_raw = ? AND "
                "delivery_hour = ? AND delivery_interval = ? AND dst_flag = ? AND location = ? "
                "AND settlement_point_type = ? AND revision = ? AND doc_id = ?",
                [
                    i["DeliveryDate"], i["DeliveryHour"], i["DeliveryInterval"], i["DSTFlag"],
                    i["SettlementPointName"], i["SettlementPointType"], i["revision"], i["doc_id"],
                ],
            ).fetchall()  # fmt: skip
        return rows[0][0] if len(rows) == 1 else None

    return lookup


# --- aggregation snapshots ------------------------------------------------------------------------
SNAPSHOT_DIR = "aggregation"
SNAPSHOT_FILE = "snapshots.jsonl"


def _sha(payload) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def context(
    result: AggregationResult,
    alignment_snapshot_state: str | None,
    record: AggregationRecord | None = None,
) -> dict:
    """Everything an aggregation snapshot depends on (recomputed to detect staleness)."""
    record = record or _record(result.method_id or "")
    return {
        "method": f"{record.id}@{record.version}:{record.scope_fingerprint()}" if record else None,
        "dam_identity": result.dam_identity,
        "revision_policy": result.revision_policy,
        "alignment_snapshot": f"{result.alignment_snapshot}:{alignment_snapshot_state}",
        "m1": f"{M1.id}@{M1.version}:{M1.scope_fingerprint()}",
        "m1_approval": result.m1_approval,
        "aggregation_approval": result.aggregation_approval,
        "intervals": [
            [i["DeliveryInterval"], i["DSTFlag"], i["revision"], i["doc_id"]]
            for i in result.intervals
        ],
        "duration_evidence": _sha(result.duration_evidence),
        "formula_version": result.formula_version,
        "validation_version": VALIDATION_VERSION,
    }


def snapshot(result: AggregationResult, ctx: dict, recorded_at_utc: str) -> dict:
    return {
        "snapshot_id": "agg-" + _sha([ctx, result.status, result.output, recorded_at_utc]),
        "recorded_at_utc": recorded_at_utc,
        "context": ctx,
        "status": result.status,
        "output": result.output,
        "units": result.units,
        "output_name": result.output_name,
        "input_prices": list(result.input_prices),
        "duration_evidence": result.duration_evidence,
        "limitations": list(result.limitations),
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
    """(snapshot, state, reasons): current, stale (any input changed), superseded, unknown."""
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
        out.append((s, "stale" if changed else "current", [f"{k} changed" for k in changed]))
    return out


def as_dict(result) -> dict:
    return asdict(result)
