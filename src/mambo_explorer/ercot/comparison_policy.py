"""Versioned comparison-assumption records (Stage 25, ADR 0022).

Each record defines one signed way to compare ONE ERCOT NP4-190-CD day-ahead SPP at HB_NORTH with
ONE approved hourly analytical summary of the M1-aligned NP6-905-CD real-time SPPs of the same
source-native hour. ERCOT defines no day-ahead/real-time price difference in the reviewed
materials (docs/comparison-evidence.md). A record is usable only with its own recorded,
attributable approval, on top of active M1 and aggregation approvals; user authorization to
build this stage is not an approval.

The absolute difference and the percentage difference are documented candidates only; they
have no approvable record in this stage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from mambo_explorer.ercot import prices as px
from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.aggregation_policy import RECORDS as AGG_RECORDS
from mambo_explorer.ercot.m1_policy import M1

UNITS = "$/MWh"
FINALITY_STATUS = (
    "not determined: neither price is established as final (no Business-Day calendar; the "
    "correction reports NP4-196-M and NP4-197-M are not collected)"
)
NOTICE = (
    "This is an analytical price comparison under review-approved assumptions. "
    "It is not an ERCOT settlement, profit-and-loss result, trading backtest, or forecast "
    "evaluation."
)
PROHIBITED_INTERPRETATIONS = (
    "a DART value or any ERCOT-defined day-ahead/real-time quantity",
    "a settlement amount, charge, payment, or invoice",
    "a profit, loss, P&L, savings, or cost avoided",
    "a hedge value or hedge effectiveness",
    "a participant's exposure (no quantity is involved)",
    "a forecast error or an evaluation of the day-ahead market as a forecast",
    "a trading signal, strategy result, or backtest",
    "a comparison of final prices",
    "an input to the Finance calculators",
)


@dataclass(frozen=True)
class ComparisonRecord:
    id: str
    version: str
    formula: str
    formula_version: str
    sign_convention: str
    rt_coefficient: int  # +1 or -1 multiplying the RT summary
    dam_coefficient: int  # the opposite sign, multiplying the day-ahead SPP
    inputs: str
    datasets: tuple[str, ...]
    location: str  # day-ahead point/type and real-time point/type
    depends_on: str  # M1@version:scope
    aggregations: tuple[str, ...]  # "AGG-A@1.0.0:<scope>" entries this comparison accepts
    revision_policies: tuple[str, ...]
    output_name: str
    output_units: str
    allowed_uses: tuple[str, ...]
    prohibited_interpretations: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    re_review_triggers: tuple[str, ...]
    authorization: str
    official_status: str = "no ERCOT-defined day-ahead/real-time price difference"
    status: str = "current"

    def _sha(self, payload) -> str:
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list)
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def limitations_fingerprint(self) -> str:
        return self._sha([self.limitations, self.prohibited_interpretations])

    def scope_fingerprint(self) -> str:
        return self._sha(
            {
                "id": self.id,
                "version": self.version,
                "formula": self.formula,
                "formula_version": self.formula_version,
                "sign": [self.sign_convention, self.rt_coefficient, self.dam_coefficient],
                "datasets": self.datasets,
                "location": self.location,
                "depends_on": self.depends_on,
                "aggregations": self.aggregations,
                "revision_policies": self.revision_policies,
                "output": [self.output_name, self.output_units],
                "limitations": self.limitations_fingerprint(),
            }
        )

    def sign_problems(self) -> list[str]:
        """Inconsistent sign metadata makes the record unusable (never silently corrected)."""
        problems = []
        if {self.rt_coefficient, self.dam_coefficient} != {1, -1}:
            problems.append("coefficients must be +1 and -1")
        first = "RT" if self.rt_coefficient == 1 else "DAM"
        if not self.sign_convention.startswith(f"{first} "):
            problems.append(f"sign convention does not start with {first}")
        return problems


_M1 = f"{M1.id}@{M1.version}:{M1.scope_fingerprint()}"
_AGGS = tuple(f"{r.id}@{r.version}:{r.scope_fingerprint()}" for r in AGG_RECORDS)
_POLICIES = ("latest-retrieved", "first-retrieved")
_LOCATION = (
    f"{px.LOCATION} ({px.LOCATION_TYPE}) in {px.DATASET} and {rt.LOCATION}/"
    f"{rt.LOCATION_TYPE_CODE} in {rt.DATASET}"
)
_INPUTS = (
    "One selected NP4-190-CD day-ahead SPP observation (source-native DeliveryDate, HourEnding, "
    "DSTFlag; selected revision; $/MWh) and one aggregation_approved_complete hourly analytical "
    "RT SPP summary for the same M1-aligned hour, from current alignment and aggregation "
    "snapshots under the same revision policy."
)
_ALLOWED = (
    "Showing, for one governed hour, how far the approved real-time analytical summary lies "
    "above or below the day-ahead SPP, in $/MWh, in learning and diagnostic views.",
)
_LIMITS = (
    "ERCOT defines no day-ahead/real-time price difference in the reviewed materials; this is a "
    "project analytical comparison under review-approved assumptions (M1, an AGG record, and "
    "this record).",
    "Both inputs are prices in $/MWh, and so is the difference; no quantity is involved, so it "
    "is not an amount of money.",
    "The real-time side is an analytical summary of four 15-minute prices, not an ERCOT hourly "
    "price.",
    "Neither price is established as final; corrections (NP4-196-M, NP4-197-M) are not collected.",
    "ERCOT's report-label definitions remain unverified (M1).",
    "One hour at a time; no time series, average, or count of differences is produced.",
)
_TRIGGERS = (
    "A new version of M1, of an accepted AGG record, or of this record.",
    "ERCOT publishing a day-ahead/real-time comparison or label definitions.",
    "A change to either report's header, identity, unit, or the HB_NORTH scope.",
    "Any proposal to add quantities, percentages, or aggregation across hours.",
)
_AUTH = (
    "The Stage 25 request authorizes building and testing these comparisons. That is not an "
    "approval of any comparison; no attributable approval is recorded."
)
_EVIDENCE = ("OFF-3", "OFF-8", "OFF-13", "OFF-14", "OFF-15")

CMP_A = ComparisonRecord(
    id="CMP-A",
    version="1.0.0",
    formula="D = S_RT - P_DAM, where S_RT is the approved hourly analytical RT SPP summary and "
    "P_DAM the selected day-ahead SPP of the same hour ($/MWh)",
    formula_version="CA.1",
    sign_convention="RT minus DAM: positive when the RT summary is higher than the DAM price",
    rt_coefficient=1,
    dam_coefficient=-1,
    inputs=_INPUTS,
    datasets=(px.DATASET, rt.DATASET),
    location=_LOCATION,
    depends_on=_M1,
    aggregations=_AGGS,
    revision_policies=_POLICIES,
    output_name="Analytical DAM-to-RT price difference (RT summary minus DAM)",
    output_units=UNITS,
    allowed_uses=_ALLOWED,
    prohibited_interpretations=PROHIBITED_INTERPRETATIONS,
    supporting_evidence=_EVIDENCE,
    limitations=_LIMITS,
    re_review_triggers=_TRIGGERS,
    authorization=_AUTH,
)

CMP_B = ComparisonRecord(
    id="CMP-B",
    version="1.0.0",
    formula="D = P_DAM - S_RT, where P_DAM is the selected day-ahead SPP and S_RT the approved "
    "hourly analytical RT SPP summary of the same hour ($/MWh)",
    formula_version="CB.1",
    sign_convention="DAM minus RT: positive when the DAM price is higher than the RT summary",
    rt_coefficient=-1,
    dam_coefficient=1,
    inputs=_INPUTS,
    datasets=(px.DATASET, rt.DATASET),
    location=_LOCATION,
    depends_on=_M1,
    aggregations=_AGGS,
    revision_policies=_POLICIES,
    output_name="Analytical DAM-to-RT price difference (DAM minus RT summary)",
    output_units=UNITS,
    allowed_uses=_ALLOWED,
    prohibited_interpretations=PROHIBITED_INTERPRETATIONS,
    supporting_evidence=_EVIDENCE,
    limitations=_LIMITS,
    re_review_triggers=_TRIGGERS,
    authorization=_AUTH,
)

RECORDS = (CMP_A, CMP_B)

NOT_APPROVABLE = {
    "absolute-difference": "discards the direction of the difference; it may only accompany a "
    "signed comparison for a stated reason, and no record approves it in this stage.",
    "percentage-difference": "undefined when the day-ahead price is zero, unstable near zero, "
    "hard to read with negative prices, and dependent on the denominator chosen; it needs its "
    "own governed record before any production use.",
}


def record(record_id: str) -> ComparisonRecord:
    found = [r for r in RECORDS if r.id == record_id]
    if not found:
        raise KeyError(record_id)
    return found[0]
