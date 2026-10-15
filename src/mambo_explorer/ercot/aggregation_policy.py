"""Versioned aggregation-assumption records (Stage 24, ADR 0021).

Each record defines one way to summarize the four M1-aligned NP6-905-CD 15-minute Settlement
Point Prices of one hour into one ANALYTICAL value. None is an ERCOT-defined hourly price:
ERCOT publishes no hourly real-time SPP in the reviewed materials (docs/aggregation-evidence.md).
A record is usable only with its own recorded, attributable approval (`ercot/approvals.py`),
on top of an active M1 approval; user authorization to build this stage is not an approval.

Energy-weighted prices and settlement amounts are documented candidates only: the quantities
they need do not exist in this application, so they have no approvable record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.m1_policy import M1

ARITHMETIC = "arithmetic-mean"
DURATION_WEIGHTED = "duration-weighted-mean"
UNITS = "$/MWh"
LIMITATION_BANNER = (
    "This is an analytical summary under review-approved assumptions. "
    "It is not an ERCOT-defined hourly settlement price, settlement, or trading backtest."
)
PROHIBITED_INTERPRETATIONS = (
    "an ERCOT real-time settlement price for the hour",
    "a final price",
    "a day-ahead/real-time spread, DART, or any difference with a day-ahead price",
    "a settlement amount, invoice, charge, or payment",
    "a profit, P&L, trading signal, or backtest result",
    "an energy-weighted or load-weighted price",
    "an input to the Finance calculators",
)


@dataclass(frozen=True)
class DurationEvidence:
    id: str
    minutes: int  # the verified Settlement Interval length
    flags: tuple[str, ...]  # DSTFlag values this evidence covers (verbatim)
    sources: tuple[str, ...]
    statement: str


DUR_15 = DurationEvidence(
    id="DUR-15",
    minutes=rt.INTERVAL_MINUTES,
    flags=("N",),
    sources=("OFF-2", "OFF-11"),
    statement=(
        "ERCOT Real-Time Settlement Point Prices are calculated for a 15-minute Settlement "
        "Interval (Protocols §4.1(3); §6.6.1.1 and §3.5.2.1(4) weight SCED prices by their "
        "duration within the 15-minute Settlement Interval). Applied to M1-matched intervals "
        "with DSTFlag N only: no NP6-905-CD document of a daylight-saving day has been "
        "observed, so DSTFlag Y intervals have no duration evidence here."
    ),
)


@dataclass(frozen=True)
class AggregationRecord:
    id: str
    version: str
    method: str
    formula: str
    formula_version: str
    output_name: str
    output_units: str
    dataset: str
    location: str
    depends_on: str  # "M1@1.0.0:<scope fingerprint>"
    completeness: str
    duration_evidence: DurationEvidence | None  # required for duration weighting only
    revision_policies: tuple[str, ...]
    allowed_uses: tuple[str, ...]
    prohibited_uses: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    re_review_triggers: tuple[str, ...]
    authorization: str
    official_status: str = "no ERCOT-defined hourly real-time SPP"
    status: str = "current"  # of the record itself: current | superseded | revoked

    def _sha(self, payload) -> str:
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list)
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def limitations_fingerprint(self) -> str:
        """What an approver must accept explicitly (`--accept-limitations`)."""
        return self._sha([self.limitations, self.prohibited_uses])

    def scope_fingerprint(self) -> str:
        return self._sha(
            {
                "id": self.id,
                "version": self.version,
                "method": self.method,
                "formula": self.formula,
                "formula_version": self.formula_version,
                "output": [self.output_name, self.output_units],
                "dataset": self.dataset,
                "location": self.location,
                "depends_on": self.depends_on,
                "completeness": self.completeness,
                "duration": (
                    [
                        self.duration_evidence.id,
                        self.duration_evidence.minutes,
                        self.duration_evidence.flags,
                    ]
                    if self.duration_evidence
                    else None
                ),
                "revision_policies": self.revision_policies,
                "limitations": self.limitations_fingerprint(),
            }
        )


_M1_DEPENDENCY = f"{M1.id}@{M1.version}:{M1.scope_fingerprint()}"
_COMPLETENESS = (
    "One selected day-ahead hour and exactly the four interval identities M1 expects, each with "
    "exactly one selected revision and a published price, all from one current alignment "
    "snapshot under M1; no missing value and no unresolved duplicate revision."
)
_POLICIES = ("latest-retrieved", "first-retrieved")
_ALLOWED = (
    "Describing, for one hour, the typical level of the four posted 15-minute real-time SPPs at "
    "HB_NORTH in learning and diagnostic views.",
)
_LIMITS = (
    "ERCOT publishes no hourly real-time SPP in the reviewed materials; this is an analytical "
    "summary under review-approved assumptions (M1 and this record).",
    "It is a price summary in $/MWh, not an energy-weighted price and not a settlement amount; "
    "no quantity is involved.",
    "Valid only for a complete M1 alignment; nothing is filled, averaged over fewer intervals, "
    "or interpolated.",
    "Prices are the revisions this computer retrieved under the stated policy; none is final, "
    "and correction reports (NP4-197-M) are not collected.",
    "ERCOT's report-label definitions remain unverified (M1).",
)
_TRIGGERS = (
    "A new version of M1 or of this record, or a change of M1's scope fingerprint.",
    "ERCOT publishing an hourly real-time SPP or a definition of these report labels.",
    "A change to the NP6-905-CD header, identity, or interval length.",
    "Extending the record to another settlement point or to DSTFlag Y intervals.",
)
_AUTH = (
    "The Stage 24 request authorizes building and testing these methods. That is not an "
    "approval of any aggregation method; no attributable approval is recorded."
)

AGG_A = AggregationRecord(
    id="AGG-A",
    version="1.0.0",
    method=ARITHMETIC,
    formula="S = (P1 + P2 + P3 + P4) / 4, where Pi is the selected 15-minute RT SPP of M1 "
    "interval i ($/MWh)",
    formula_version="A.1",
    output_name="Hourly analytical RT SPP summary (arithmetic mean)",
    output_units=UNITS,
    dataset=rt.DATASET,
    location=f"{rt.LOCATION}/{rt.LOCATION_TYPE_CODE}",
    depends_on=_M1_DEPENDENCY,
    completeness=_COMPLETENESS,
    duration_evidence=None,
    revision_policies=_POLICIES,
    allowed_uses=_ALLOWED,
    prohibited_uses=PROHIBITED_INTERPRETATIONS,
    supporting_evidence=("OFF-2", "OFF-12"),
    limitations=_LIMITS
    + (
        "The equal weight 1/4 per interval is the definition of this summary; the same form "
        "appears in ERCOT's credit formula HRSAP (Protocols §16.11.4.3.3), which is not a "
        "settlement price.",
    ),
    re_review_triggers=_TRIGGERS,
    authorization=_AUTH,
)

AGG_B = AggregationRecord(
    id="AGG-B",
    version="1.0.0",
    method=DURATION_WEIGHTED,
    formula="S = Σ(Pi × Di) / Σ Di, where Di is the verified duration of M1 interval i in "
    "hours (DUR-15) and Pi its selected 15-minute RT SPP ($/MWh)",
    formula_version="B.1",
    output_name="Hourly analytical RT SPP summary (duration-weighted mean)",
    output_units=UNITS,
    dataset=rt.DATASET,
    location=f"{rt.LOCATION}/{rt.LOCATION_TYPE_CODE}",
    depends_on=_M1_DEPENDENCY,
    completeness=_COMPLETENESS
    + " Every interval needs duration evidence covering its DSTFlag (DUR-15: N only).",
    duration_evidence=DUR_15,
    revision_policies=_POLICIES,
    allowed_uses=_ALLOWED,
    prohibited_uses=PROHIBITED_INTERPRETATIONS,
    supporting_evidence=("OFF-2", "OFF-11", "OFF-12"),
    limitations=_LIMITS
    + (
        "With four verified 15-minute intervals it equals the arithmetic mean; weighting by "
        "elapsed time does not make it energy-weighted.",
    ),
    re_review_triggers=_TRIGGERS,
    authorization=_AUTH,
)

RECORDS = (AGG_A, AGG_B)

# Documented candidates with no approvable record (docs/aggregation-evidence.md).
NOT_APPROVABLE = {
    "energy-weighted-price": "needs interval-level energy quantities (MWh) compatible with the "
    "settlement point and interval mapping; none exist in this application, and EIA-930 demand "
    "is unrelated to HB_NORTH settlement quantities.",
    "settlement-amount": "a currency amount, not a price; needs participant settlement "
    "quantities, sign conventions, and the omitted charges of Protocols §6.6.",
}


def record(record_id: str) -> AggregationRecord:
    found = [r for r in RECORDS if r.id == record_id]
    if not found:
        raise KeyError(record_id)
    return found[0]
