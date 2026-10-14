"""Versioned assumption record M1 (Stage 23, ADR 0020): day-ahead hour ↔ real-time intervals.

M1 is an OPERATIONAL ASSUMPTION, not an ERCOT field definition. ERCOT's official materials do
not define the reports' HourEnding, DeliveryHour, DeliveryInterval, DeliveryDate, or DSTFlag
labels (docs/interval-alignment.md). The owner authorized implementing M1 as a documented,
review-approved assumption; using it still needs a recorded, attributable approval
(`ercot/approvals.py`), and the official semantics stay unresolved.

This module is the only place the four-interval expectation lives (`expected_intervals`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from mambo_explorer.ercot import prices as px
from mambo_explorer.ercot import rt_prices as rt


@dataclass(frozen=True)
class LocationScope:
    day_ahead_point: str
    day_ahead_location_type: str  # the store's type; the NP4-190-CD file has no type column
    real_time_point: str
    real_time_type: str  # as written in NP6-905-CD; the code is not officially defined
    evidence: str


@dataclass(frozen=True)
class AssumptionRecord:
    id: str
    version: str
    title: str
    rule: str
    datasets: tuple[str, ...]
    locations: tuple[LocationScope, ...]
    expected_intervals: tuple[str, ...]
    flags: tuple[str, ...]  # DSTFlag values matched verbatim; anything else is not guessed
    schema: dict
    supporting_evidence: tuple[str, ...]
    unresolved_definitions: tuple[str, ...]
    limitations: tuple[str, ...]
    re_review_triggers: tuple[str, ...]
    authorization: str
    reported_acceptance: str
    official_status: str = "unresolved"
    status: str = "current"  # "current" | "superseded" | "revoked" (of the record itself)

    def schema_fingerprint(self) -> str:
        return _sha(self.schema)

    def scope_fingerprint(self) -> str:
        """What an approval binds to: change any of these and the approval no longer matches."""
        return _sha(
            {
                "id": self.id,
                "version": self.version,
                "rule": self.rule,
                "datasets": self.datasets,
                "locations": [
                    (
                        s.day_ahead_point,
                        s.day_ahead_location_type,
                        s.real_time_point,
                        s.real_time_type,
                    )
                    for s in self.locations
                ],
                "expected_intervals": self.expected_intervals,
                "flags": self.flags,
                "schema": self.schema_fingerprint(),
            }
        )

    def location_for(self, day_ahead_point: str, day_ahead_type: str) -> LocationScope | None:
        return next(
            (
                s
                for s in self.locations
                if (s.day_ahead_point, s.day_ahead_location_type)
                == (day_ahead_point, day_ahead_type)
            ),
            None,
        )


def _sha(payload) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


BANNER = (
    "Aligned under review-approved assumption M1. ERCOT report-label definitions remain unverified."
)

M1 = AssumptionRecord(
    id="M1",
    version="1.0.0",
    title="Day-ahead hour to real-time intervals by matching source-native labels",
    rule=(
        "Match one NP4-190-CD day-ahead hour (DeliveryDate D, HourEnding hh:00, DSTFlag F, "
        "SettlementPoint P) to the NP6-905-CD real-time observations with the same "
        "DeliveryDate label D, DeliveryHour equal to the number hh, the same verbatim DSTFlag F, "
        "the in-scope settlement point and type for P, and DeliveryInterval labels 1 through 4. "
        "Hour 24 stays on its published DeliveryDate; repeated hours are matched per flag and "
        "never merged."
    ),
    datasets=(px.DATASET, rt.DATASET),
    locations=(
        LocationScope(
            day_ahead_point=px.LOCATION,
            day_ahead_location_type=px.LOCATION_TYPE,
            real_time_point=rt.LOCATION,
            real_time_type=rt.LOCATION_TYPE_CODE,
            evidence=(
                "Observed: HB_NORTH appears once per NP6-905-CD interval with "
                "SettlementPointType HU (Stage 20 live files); the day-ahead store types "
                "HB_NORTH as a hub from ERCOT's NP4-160-SG hub mapping (ADR 0016). The HU code "
                "itself is not defined in the reviewed official materials."
            ),
        ),
    ),
    expected_intervals=("1", "2", "3", "4"),
    flags=("N", "Y"),
    schema={
        "day_ahead": {"dataset": px.DATASET, "header": px.HEADER, "identity": px.IDENTITY},
        "real_time": {"dataset": rt.DATASET, "header": rt.HEADER, "identity": rt.IDENTITY},
    },
    supporting_evidence=("OFF-1", "OFF-2", "OFF-3", "OFF-5", "ACT-1", "ACT-2", "ACT-3"),
    unresolved_definitions=(
        "HourEnding (NP4-190-CD) and DeliveryHour (NP6-905-CD): no official definition that "
        "they name the same Operating Hour.",
        "DeliveryInterval: no official definition that 1-4 are the hour's 15-minute Settlement "
        "Intervals in order.",
        'DSTFlag: documented only as "DST Flag"; the meaning of N and Y is not defined.',
        "DeliveryDate: not officially stated to be the Operating Day.",
        "SettlementPointType HU: not officially defined as the hub type.",
    ),
    limitations=(
        "An operational assumption, not ERCOT-verified and not a legal or regulatory approval.",
        "The four expected intervals are part of M1, not an independently verified rule.",
        "A complete alignment does not prove a complete Operating Day, final prices, or "
        "correct official semantics.",
        "Labels and price presence only: no price is aggregated, compared, or converted to "
        "a clock time or UTC.",
        "Revisions are those this computer retrieved; none is called final.",
    ),
    re_review_triggers=(
        "ERCOT publishes field definitions, a user guide, or a schema change for either report.",
        "A change to either report header or stored identity (schema fingerprint).",
        "A DSTFlag value other than N or Y, or a day whose labels contradict M1.",
        "Observation of an NP4-190-CD or NP6-905-CD DST-day document (backlog BL-8).",
        "Adding a settlement point or type to the scope.",
        "Any new version of this record.",
    ),
    authorization=(
        "The owner authorized implementing M1 as an explicitly documented, review-approved "
        "operational assumption (Stage 23 request, 2026-10-13). This is authorization to "
        "implement, not a reviewer approval."
    ),
    reported_acceptance=(
        "The Stage 23 request describes M1 as review-approved but names no reviewer, role, "
        "date, or approval artifact; that acceptance is reported, not attributable."
    ),
)

RECORDS = (M1,)


def current(assumption_id: str = "M1") -> AssumptionRecord:
    return next(r for r in RECORDS if r.id == assumption_id and r.status == "current")
