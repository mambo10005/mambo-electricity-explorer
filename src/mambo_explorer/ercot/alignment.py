"""Source-native interval alignment of ERCOT day-ahead hours and real-time intervals (ADR 0019).

Relates one NP4-190-CD day-ahead hour (DeliveryDate, HourEnding, SettlementPoint, DSTFlag) to
NP6-905-CD real-time intervals (DeliveryDate, DeliveryHour, DeliveryInterval,
SettlementPointName, SettlementPointType, DSTFlag) by their labels only, under a mapping
whose evidence is recorded in `EVIDENCE` and `CANDIDATES` (docs/interval-alignment.md).

What this module never does: read or return a price value (only whether a price is present),
compute a spread or an hourly real-time figure, convert a label to a clock time or UTC,
rewrite hour 24 or a DSTFlag, fill an absent interval, or call any revision final.
Completeness is per hour and separate from dataset coverage and from revision completeness.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from mambo_explorer.ercot.m1_policy import M1 as M1_RECORD

# --- statuses -----------------------------------------------------------------------------
ALIGNED_COMPLETE = "aligned_complete"
ALIGNED_INCOMPLETE = "aligned_incomplete"
AMBIGUOUS_DST = "ambiguous_dst"
INCOMPATIBLE_IDENTITY = "incompatible_identity"
MISSING_DAY_AHEAD = "missing_day_ahead"
MISSING_REAL_TIME = "missing_real_time"
UNSUPPORTED_SEMANTICS = "unsupported_semantics"
UNAVAILABLE_REVISION = "unavailable_revision"
INVALID_INPUT = "invalid_input"
STATUSES = (
    ALIGNED_COMPLETE,
    ALIGNED_INCOMPLETE,
    AMBIGUOUS_DST,
    INCOMPATIBLE_IDENTITY,
    MISSING_DAY_AHEAD,
    MISSING_REAL_TIME,
    UNSUPPORTED_SEMANTICS,
    UNAVAILABLE_REVISION,
    INVALID_INPUT,
)

# Candidate status used only by ercot/assumed_alignment.py after its approval checks pass.
ASSUMPTION_GOVERNED = "review-approved-assumption"

# --- revision policies (section 5 of docs/interval-alignment.md) ----------------------------
LATEST_RETRIEVED = "latest-retrieved"
FIRST_RETRIEVED = "first-retrieved"
LATEST_KNOWN_BEFORE = "latest-known-before-cutoff"
FINAL = "final"
REVISION_POLICIES = {
    LATEST_RETRIEVED: "The highest stored revision of each identity: the newest value this "
    "computer has retrieved. Not necessarily ERCOT's newest, and never called final.",
    FIRST_RETRIEVED: "Revision 1 of each identity: the first value this computer stored. Not "
    "necessarily ERCOT's first publication (an earlier posting may have been replaced before "
    "it was retrieved).",
    LATEST_KNOWN_BEFORE: "Not available: which value ERCOT had published before a cutoff would "
    "need an archive of every posting and correction; the store holds only the documents this "
    "computer retrieved.",
    FINAL: "Not available: finality is not determined (no Business-Day calendar; the "
    "correction reports NP4-196-M and NP4-197-M are not collected).",
}
SUPPORTED_REVISION_POLICIES = (LATEST_RETRIEVED, FIRST_RETRIEVED)

# --- completeness policies --------------------------------------------------------------------
STRICT = "strict"
COMPLETENESS_POLICIES = {
    STRICT: "Complete only if every expected real-time interval identity of the hour is "
    "present exactly once after the revision policy, each with a published (non-blank) price, "
    "and the day-ahead hour has a published price. Nothing is filled or averaged.",
}

# --- source-native label formats (as validated by the collectors) ----------------------------
_DATE = re.compile(r"^(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/\d{4}$")
_HOUR_ENDING = re.compile(r"^(0[1-9]|1\d|2[0-4]):00$")
_DELIVERY_HOUR = re.compile(r"^([1-9]|1\d|2[0-4])$")
_DELIVERY_INTERVAL = re.compile(r"^[1-9]\d*$")
KNOWN_DST_FLAGS = ("N", "Y")


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: str  # "official" | "actual-file" | "synthetic"
    title: str
    location: str
    section: str
    version: str
    published: str | None
    effective: str | None
    retrieved: str
    proposition: str
    ambiguity: str


@dataclass(frozen=True)
class Candidate:
    id: str
    rule: str
    status: str  # "accepted" | "rejected" | "not-supported"
    supporting: tuple[str, ...]
    contradicting: tuple[str, ...]
    assumptions: tuple[str, ...]
    covered: tuple[str, ...]
    unsupported: tuple[str, ...]
    confidence: str
    review: str = "AI-authored; not human-reviewed"
    # compatible (day-ahead store location type, real-time SettlementPointType) pairs
    compatible_types: frozenset = frozenset({("hub", "HU")})
    expected_intervals: tuple[str, ...] = ()  # verified real-time DeliveryInterval labels


PROTOCOLS = "https://www.ercot.com/mktrules/nprotocols/current"
NOTICES = "https://www.ercot.com/services/comm/mkt_notices/"  # + notice id
RETRIEVED = "2026-10-13"
AI_NOTE = "AI-authored; not human-reviewed"

# The Stage 22 investigation (docs/interval-alignment.md holds the full record).
EVIDENCE: tuple[Evidence, ...] = (
    Evidence(
        "OFF-1",
        "official",
        "ERCOT Nodal Protocols Section 2, Definitions and Acronyms",
        PROTOCOLS,
        "Definitions: Operating Day; Operating Hour; Central Prevailing Time (CPT)",
        "Section 2, version dated August 1, 2026",
        None,
        None,
        RETRIEVED,
        'Operating Day: "The day, including hours ending 0100 to 2400, during which energy '
        'flows." Operating Hour: "A full clock hour during which energy flows." CPT: "Either '
        'Central Standard Time or Central Daylight Time, in effect in Austin, Texas."',
        "No section defines DeliveryDate, HourEnding, DeliveryHour, DeliveryInterval, or "
        "DSTFlag, or states that either report's labels are Operating Days and Hours in CPT.",
    ),
    Evidence(
        "OFF-2",
        "official",
        "ERCOT Nodal Protocols Section 4, Day-Ahead Operations",
        PROTOCOLS,
        "§4.1(3)",
        "Section 4, version dated August 1, 2026",
        None,
        None,
        RETRIEVED,
        'DAM energy settlements use DAM Settlement Point Prices calculated "for a one-hour '
        'Settlement Interval"; Real-Time energy settlements use Real-Time Settlement Point '
        'Prices calculated "for a 15-minute Settlement Interval".',
        "Defines settlement interval lengths, not report labels.",
    ),
    Evidence(
        "OFF-3",
        "official",
        "ERCOT Nodal Protocols Section 6, Adjustment Period and Real-Time Operations",
        PROTOCOLS,
        "§6.6.3.3 Real-Time Energy Imbalance Payment or Charge at a Hub (variable table)",
        "Section 6, version dated August 28, 2026",
        None,
        None,
        RETRIEVED,
        'DAEP and DAES are DAM quantities cleared "for the hour that includes the 15-minute '
        'Settlement Interval", and each is multiplied by ¼ in the 15-minute formula: every '
        "15-minute Settlement Interval belongs to exactly one DAM hour, a quarter of it.",
        "A settlement concept. It does not say which DeliveryHour/DeliveryInterval labels name "
        "the intervals of the hour labelled by an HourEnding.",
    ),
    Evidence(
        "OFF-4",
        "official",
        "ERCOT Nodal Protocols Section 3, Management Activities for the ERCOT System",
        PROTOCOLS,
        "§3.5.2.1 North 345 kV Hub",
        "Section 3, version dated August 1, 2026",
        None,
        None,
        RETRIEVED,
        "The Day-Ahead hub price is defined for a given Operating Hour (aggregated Shift "
        "Factors); the Real-Time hub price for a given 15-minute Settlement Interval "
        "(time-weighted Hub Bus prices plus the adder, floored). Neither is defined as an "
        "aggregate of the other.",
        "Price definitions; no label rule.",
    ),
    Evidence(
        "OFF-5",
        "official",
        "ERCOT Current Day Reports XSD",
        "https://www.ercot.com/files/docs/2026/07/10/Current-Day-Reporting-CDR-XSD.txt",
        "NP4-190-CD and NP6-905-CD element sequences; element DSTFlag",
        "file dated 2026-07-10 (release 2026-R8)",
        "2026-07-10",
        None,
        RETRIEVED,
        "Field names and order match both CSV headers. DSTFlag is a string whose only "
        'documentation is "DST Flag"; HourEnding, DeliveryHour, and DeliveryDate are '
        "documented by their names only.",
        "No semantics: names alone are not definitions. The meaning of N is not documented.",
    ),
    Evidence(
        "OFF-6",
        "official",
        "ERCOT market notice M-E092826-01, ERCOT MOTE will be open for DST testing",
        NOTICES + "M-E092826-01",
        "DST testing table",
        "notice dated September 28, 2026 (earlier versions: 2017, 2020, 2021)",
        "2026-09-28",
        None,
        RETRIEVED,
        'For the long day, ERCOT lists the hours "0100", "0200 (Normal Hour)", '
        '"0200* (Repeated Hour)", "0300"; the repeated clock hour is 1–2 AM ("1* AM … '
        'Repeated Hour", "2 AM CST End of Repeated hour").',
        "A test-environment notice for market submissions; it does not say how NP4-190-CD or "
        "NP6-905-CD encode the repeated hour.",
    ),
    Evidence(
        "OFF-7",
        "official",
        "ERCOT market notices M-A030526-01 and M-A030625-01, dashboards affected by the "
        "beginning of DST",
        NOTICES + "M-A030526-01",
        "Long description",
        "notices dated March 5, 2026 and March 6, 2025",
        "2026-03-05",
        None,
        RETRIEVED,
        'The "skipped 2:00 a.m. hour" on the spring day; the Real-Time Settlement Point '
        "Prices display mislabels an interval ending 0300 as 0200 and repeats the 0315 "
        "interval.",
        "About dashboards, not the reports; ERCOT says dashboard data should not be relied "
        "upon. It shows that labels near the transition can be wrong in displays.",
    ),
    Evidence(
        "OFF-8",
        "official",
        "ERCOT Nodal Protocols Sections 4 and 6: price finality",
        PROTOCOLS,
        "§4.5.2(6) (DAM) and §6.3(7) (Real-Time)",
        "Section 4 August 1, 2026; Section 6 August 28, 2026",
        None,
        None,
        RETRIEVED,
        "DAM prices are final at 1000, Real-Time prices at 1600, of the second Business Day "
        "after the Operating Day, still subject to Board review after notice within 30 days "
        "and to PUCT authority.",
        "The app has no Business-Day calendar and does not collect NP4-196-M or NP4-197-M.",
    ),
    Evidence(
        "OFF-9",
        "official",
        "ERCOT data product pages (EMIL) NP4-190-CD, NP6-905-CD, NP4-180-ER, NP6-785-ER, "
        "NP4-196-M, NP4-197-M",
        "https://www.ercot.com/mp/data-products/data-product-details?id=NP4-190-CD",
        "EMIL information",
        "pages last updated 2026-02-24 to 2026-10-06",
        None,
        None,
        RETRIEVED,
        'Every page lists "User Guide N/A". NP4-180-ER (type 13060) and NP6-785-ER (type '
        "13061) are public historical DAM/RTM hub and load-zone SPP reports (weekly, xlsx). "
        "NP4-196-M and NP4-197-M are the DAM and RTM price-correction reports.",
        "No report-specific field definitions exist on these pages. The NP4-190-CD page cites "
        "rule NP4.5.3(2)(b), which the August 1, 2026 Section 4 does not contain.",
    ),
    Evidence(
        "OFF-10",
        "official",
        "ERCOT Nodal Protocols Section 11, Data Acquisition and Aggregation",
        PROTOCOLS,
        "§11.4.4.2 (variable table)",
        "Section 11, version dated June 1, 2026",
        None,
        None,
        RETRIEVED,
        '"DST adjust … Spring DST = -4; Fall DST = 4", applied to counts of 15-minute '
        "intervals: four fewer on the spring day, four more on the fall day.",
        "Retail load-profiling context, not the price reports.",
    ),
    Evidence(
        "GAP-1",
        "inaccessible",
        "ERCOT list notice W-A092311-05 (2011), reportedly on DST flags",
        "https://lists.ercot.com",
        "not read",
        "not read",
        None,
        None,
        RETRIEVED,
        "Not read: the page showed a loading stub, then a redirect loop. Search summaries say "
        "it described the flags as marking the repeated hour; that is not evidence here.",
        "Could be the missing definition of DSTFlag; it is not bypassed or guessed.",
    ),
    Evidence(
        "ACT-1",
        "actual-file",
        "ERCOT NP4-180-ER DAMLZHBSPP_2025 and _2026; NP6-785-ER RTMLZHBSPP_2025 and _2026",
        "https://www.ercot.com/mp/data-products/data-product-details?id=NP4-180-ER",
        "HB_NORTH rows, 01/01/2025 to 10/10/2026 (648 DeliveryDates)",
        "documents 1177667469, 1285117853, 1177737535, 1285119237",
        "2026-01-01 to 2026-10-11",
        None,
        RETRIEVED,
        "On all 648 days, every day-ahead (Hour Ending, flag) label appears once, and the "
        "real-time file has the same (Delivery Hour, flag) set with Delivery Interval 1–4 each. "
        "Spring days (03/09/2025, 03/08/2026): 23 hours, 03:00 absent in both, 92 intervals. "
        "Fall day (11/02/2025): 25 hours, 02:00 N and 02:00 Y in both, 100 intervals. Hour 24 "
        "appears under its own DeliveryDate in both.",
        "Historical compilations, not the NP4-190-CD/NP6-905-CD reports themselves; their flag "
        'column is named "Repeated Hour Flag". Consistency is not a definition.',
    ),
    Evidence(
        "ACT-2",
        "actual-file",
        "NP4-190-CD and NP6-905-CD documents compared with the historical compilations",
        "https://www.ercot.com/mp/data-products/data-product-details?id=NP6-905-CD",
        "48 day-ahead hours (10/06–10/07/2026) and 31 real-time intervals (10/05–10/06/2026)",
        "NP4-190-CD documents of 2026-10-05 and 2026-10-06; Stage 21 NP6-905-CD documents",
        None,
        None,
        RETRIEVED,
        "All 48 day-ahead and 31 real-time labels exist in the compilations with the same "
        "values (three real-time values differ only in trailing zeros), linking the reports' "
        "DSTFlag column to the compilations' Repeated Hour Flag for these N labels.",
        "Only N labels overlap; no DST day overlaps the reports' public lists.",
    ),
    Evidence(
        "ACT-3",
        "actual-file",
        "NP6-905-CD document SPPHLZNP6905_20261013_0000",
        "https://www.ercot.com/mp/data-products/data-product-details?id=NP6-905-CD",
        "document name and rows",
        "Stage 20 live check",
        "2026-10-13",
        None,
        "2026-10-12",
        "The document named for 2026-10-13 00:00 holds DeliveryDate 10/12/2026, DeliveryHour "
        "24, DeliveryInterval 4: hour 24 is kept under the earlier DeliveryDate.",
        "Document names are not used to infer time.",
    ),
)

_CONCEPT = ("OFF-1", "OFF-2", "OFF-3", "OFF-5")
CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        "M1",
        "Day-ahead (DeliveryDate D, HourEnding hh:00, DSTFlag F) ↔ real-time (DeliveryDate D, "
        "DeliveryHour hh, DeliveryInterval 1–4, DSTFlag F) at the same settlement point "
        "(day-ahead hub HB_NORTH ↔ real-time HB_NORTH type HU)",
        "partially-supported",
        _CONCEPT + ("ACT-1", "ACT-2", "ACT-3"),
        ("OFF-7",),
        (
            "HourEnding hh:00 and DeliveryHour hh name the same Operating Hour (not defined "
            "officially).",
            "DeliveryInterval 1–4 are that hour's four 15-minute Settlement Intervals (not "
            "defined officially).",
            "Real-time SettlementPointType HU is the hub type of the day-ahead hub HB_NORTH.",
            "Equal DSTFlag values denote the same occurrence of a repeated hour.",
        ),
        (
            "Ordinary hours 01–24 (648 of 648 compilation days consistent)",
            "Spring days with 03:00 absent, fall day with 02:00 N and 02:00 Y (actual files)",
        ),
        (
            "Any official definition of the report labels",
            "DSTFlag values other than N and Y",
            "Settlement points other than HB_NORTH",
        ),
        "moderate (consistent actual files; no official label definition)",
        expected_intervals=M1_RECORD.expected_intervals,  # defined only in the M1 record
    ),
    Candidate(
        "M2",
        "Day-ahead HourEnding is hour-ending but real-time DeliveryHour is hour-beginning "
        "(real-time hour hh pairs with day-ahead (hh+1):00)",
        "rejected",
        (),
        ("ACT-1", "ACT-3"),
        ("Different label conventions in the two reports.",),
        (),
        ("All cases",),
        "low: contradicted by actual files (real-time DeliveryHour runs 1–24 with no 0; both "
        "reports omit the same label, 03:00/3, on spring days; hour 24 interval 4 is published "
        "after midnight)",
    ),
    Candidate(
        "M3",
        "DSTFlag distinguishes the repeated fall-back hour; it is never dropped or rewritten",
        "partially-supported",
        ("OFF-5", "OFF-6", "ACT-1", "ACT-2"),
        (),
        (
            "Y marks the second occurrence of HourEnding 02:00 (actual files, the notice's "
            '"0200*"); the meaning of N is not documented (never read as "standard time").',
        ),
        ("Fall-back days in the historical compilations",),
        ("Flag values other than N/Y; reports with no DST day in their public lists",),
        "moderate",
    ),
    Candidate(
        "M4",
        "Hour 24 belongs to the stated DeliveryDate (never rewritten as hour 00 of the next date)",
        "partially-supported",
        ("OFF-1", "ACT-1", "ACT-3"),
        (),
        ("DeliveryDate is the Operating Day (implied, not stated).",),
        ("Hour 24 in both reports",),
        (),
        "moderate-high",
    ),
)


def evidence(eid: str) -> Evidence:
    return next(e for e in EVIDENCE if e.id == eid)


def candidate(cid: str) -> Candidate:
    return next(c for c in CANDIDATES if c.id == cid)


def accepted() -> Candidate | None:
    return next((c for c in CANDIDATES if c.status == "accepted"), None)


# --- inputs -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class DamHour:
    """A day-ahead hour's source-native identity (no revision)."""

    delivery_date_raw: str
    hour_ending: str
    settlement_point: str
    location_type: str  # the store's location type; the DAM file has no type column
    dst_flag: str

    def key(self) -> tuple:
        return (self.delivery_date_raw, self.hour_ending, self.settlement_point, self.dst_flag)


@dataclass(frozen=True)
class DamObservation:
    hour: DamHour
    revision: int
    doc_id: str
    publish_time_raw: str
    price_present: bool


@dataclass(frozen=True)
class RtInterval:
    """A real-time interval's source-native identity (no revision)."""

    delivery_date_raw: str
    delivery_hour: str
    delivery_interval: str
    settlement_point: str
    settlement_point_type: str
    dst_flag: str

    def key(self) -> tuple:
        return (
            self.delivery_date_raw,
            self.delivery_hour,
            self.delivery_interval,
            self.settlement_point,
            self.settlement_point_type,
            self.dst_flag,
        )

    def label(self) -> str:
        return (
            f"{self.delivery_date_raw} H{self.delivery_hour} I{self.delivery_interval} "
            f"{self.settlement_point}/{self.settlement_point_type} {self.dst_flag}"
        )


@dataclass(frozen=True)
class RtObservation:
    interval: RtInterval
    revision: int
    doc_id: str
    publish_time_raw: str
    price_present: bool


# --- result -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class AlignmentResult:
    status: str
    mapping: str | None
    mapping_status: str | None  # the candidate's evidence status
    asserted: bool  # True only under an accepted mapping; a candidate check asserts nothing
    revision_policy: str
    completeness_policy: str
    dam_identity: dict
    dam_revision: dict | None
    matched: tuple[dict, ...] = ()  # selected real-time identities with revision references
    expected_interval_count: int | None = None  # only when verified (an accepted mapping)
    candidate_expected_count: int | None = None  # what an unaccepted candidate would expect
    observed_interval_count: int = 0
    missing_intervals: tuple[str, ...] = ()
    duplicate_intervals: tuple[str, ...] = ()
    revision_conflicts: tuple[dict, ...] = ()
    excluded: tuple[dict, ...] = ()
    dst: dict = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


LIMITATIONS = (
    "Labels only: no price is read, compared, aggregated, or returned; no DART spread is "
    "calculated.",
    "No clock time, time zone, or UTC instant is derived from any label.",
    "Revisions are those this computer retrieved; none is called final.",
    "Hour-level completeness is separate from dataset coverage and from revision completeness.",
    "AI-authored; not human-reviewed.",
)


def _dam_dict(hour: DamHour) -> dict:
    return {
        "DeliveryDate": hour.delivery_date_raw,
        "HourEnding": hour.hour_ending,
        "SettlementPoint": hour.settlement_point,
        "LocationType": hour.location_type,
        "DSTFlag": hour.dst_flag,
    }


def _rt_dict(obs: RtObservation) -> dict:
    i = obs.interval
    return {
        "DeliveryDate": i.delivery_date_raw,
        "DeliveryHour": i.delivery_hour,
        "DeliveryInterval": i.delivery_interval,
        "SettlementPointName": i.settlement_point,
        "SettlementPointType": i.settlement_point_type,
        "DSTFlag": i.dst_flag,
        "revision": obs.revision,
        "doc_id": obs.doc_id,
        "published": obs.publish_time_raw,
        "price_present": obs.price_present,
    }


def _rev(obs) -> dict:
    return {"revision": obs.revision, "doc_id": obs.doc_id, "published": obs.publish_time_raw}


def select_revision(observations: Sequence, policy: str) -> tuple[object | None, list]:
    """Pick one observation of a single identity under a supported policy.

    Returns (chosen, unresolved): `unresolved` lists observations sharing the chosen
    revision number (a true duplicate the policy cannot resolve).
    """
    if not observations:
        return None, []
    if policy == LATEST_RETRIEVED:
        target = max(o.revision for o in observations)
    elif policy == FIRST_RETRIEVED:
        target = min(o.revision for o in observations)
    else:
        raise ValueError(f"unsupported revision policy {policy!r}")
    same = [o for o in observations if o.revision == target]
    return same[0], (same if len(same) > 1 else [])


def _invalid_dam(hour: DamHour) -> list[str]:
    bad = []
    if not _DATE.match(hour.delivery_date_raw):
        bad.append(f"day-ahead DeliveryDate {hour.delivery_date_raw!r} is not MM/DD/YYYY")
    if not _HOUR_ENDING.match(hour.hour_ending):
        bad.append(f"day-ahead HourEnding {hour.hour_ending!r} is not 01:00..24:00")
    if not hour.settlement_point:
        bad.append("day-ahead SettlementPoint is empty")
    return bad


def _invalid_rt(i: RtInterval) -> list[str]:
    bad = []
    if not _DATE.match(i.delivery_date_raw):
        bad.append(f"{i.label()}: DeliveryDate is not MM/DD/YYYY")
    if not _DELIVERY_HOUR.match(i.delivery_hour):
        bad.append(f"{i.label()}: DeliveryHour is not 1..24")
    if not _DELIVERY_INTERVAL.match(i.delivery_interval):
        bad.append(f"{i.label()}: DeliveryInterval is not a positive integer")
    return bad


def align(
    dam: DamObservation | DamHour,
    rt_candidates: Sequence[RtObservation],
    *,
    revision_policy: str,
    completeness_policy: str = STRICT,
    dam_revisions: Sequence[DamObservation] = (),
) -> AlignmentResult:
    """Align one day-ahead hour with real-time intervals under the ACCEPTED mapping only.

    `dam` is one observation or a bare identity; `dam_revisions` adds the other stored
    revisions of the same hour. With no accepted mapping the result is unsupported_semantics
    (after input and policy validation); nothing is inferred.
    """
    return _evaluate(
        accepted(),
        dam,
        rt_candidates,
        revision_policy,
        completeness_policy,
        dam_revisions,
        candidate_check=False,
    )


def check_candidate(
    mapping: str,
    dam: DamObservation | DamHour,
    rt_candidates: Sequence[RtObservation],
    *,
    revision_policy: str,
    completeness_policy: str = STRICT,
    dam_revisions: Sequence[DamObservation] = (),
) -> AlignmentResult:
    """Diagnostic only: how the labels would relate under a named, unaccepted candidate.

    The result has `asserted=False` unless the candidate is accepted, carries no verified
    expected count, and a rejected candidate is never evaluated (unsupported_semantics).
    """
    return _evaluate(
        candidate(mapping),
        dam,
        rt_candidates,
        revision_policy,
        completeness_policy,
        dam_revisions,
        candidate_check=True,
    )


def _evaluate(
    chosen_map: Candidate | None,
    dam: DamObservation | DamHour,
    rt_candidates: Sequence[RtObservation],
    revision_policy: str,
    completeness_policy: str,
    dam_revisions: Sequence[DamObservation],
    *,
    candidate_check: bool,
) -> AlignmentResult:
    hour = dam.hour if isinstance(dam, DamObservation) else dam
    dam_obs = ([dam] if isinstance(dam, DamObservation) else []) + list(dam_revisions)
    asserted = chosen_map is not None and chosen_map.status == "accepted"
    base = {
        "mapping": chosen_map.id if chosen_map else None,
        "mapping_status": chosen_map.status if chosen_map else None,
        "asserted": asserted,
        "revision_policy": revision_policy,
        "completeness_policy": completeness_policy,
        "dam_identity": _dam_dict(hour),
        "limitations": LIMITATIONS,
    }

    def result(status, **kw) -> AlignmentResult:
        return AlignmentResult(status=status, **{"dam_revision": None, **base, **kw})

    # 1. inputs and policies
    problems = _invalid_dam(hour)
    problems += [p for o in rt_candidates for p in _invalid_rt(o.interval)]
    problems += [
        f"day-ahead revision for {o.hour.key()} is not the requested hour"
        for o in dam_obs
        if o.hour != hour
    ]
    if completeness_policy not in COMPLETENESS_POLICIES:
        problems.append(f"unknown completeness policy {completeness_policy!r}")
    if revision_policy not in REVISION_POLICIES:
        problems.append(f"unknown revision policy {revision_policy!r}")
    if problems:
        return result(INVALID_INPUT, reasons=tuple(problems))
    if revision_policy not in SUPPORTED_REVISION_POLICIES:
        return result(UNAVAILABLE_REVISION, reasons=(REVISION_POLICIES[revision_policy],))

    # 2. mapping
    usable = chosen_map is not None and (
        asserted
        or (candidate_check and chosen_map.status == "partially-supported")
        or chosen_map.status == ASSUMPTION_GOVERNED
    )
    if not usable:
        why = (
            f"candidate {chosen_map.id} is {chosen_map.status}: no alignment is asserted"
            if chosen_map
            else "no candidate mapping is accepted: ERCOT's official materials do not define "
            "how the reports' HourEnding, DeliveryHour, DeliveryInterval, and DSTFlag labels "
            "relate (docs/interval-alignment.md)"
        )
        return result(UNSUPPORTED_SEMANTICS, reasons=(why,))
    ev = chosen_map.supporting
    if chosen_map.status == ASSUMPTION_GOVERNED:
        base["limitations"] = LIMITATIONS
    elif not asserted:
        base["limitations"] = (
            f"Candidate check only: {chosen_map.id} is {chosen_map.status}, not accepted. "
            "This status describes labels under an unverified rule; it is not an alignment.",
        ) + LIMITATIONS
    n_expected = len(chosen_map.expected_intervals)
    counts = (
        {"expected_interval_count": n_expected}
        if asserted
        else {"candidate_expected_count": n_expected}
    )

    # 3. DST flag of the day-ahead hour
    if hour.dst_flag not in KNOWN_DST_FLAGS:
        return result(
            AMBIGUOUS_DST,
            evidence=ev,
            dst={"day_ahead": hour.dst_flag, "known_flags": list(KNOWN_DST_FLAGS)},
            reasons=(
                f"day-ahead DSTFlag {hour.dst_flag!r} is not a documented value; the hour "
                "cannot be matched without guessing",
            ),
        )

    # 4. the day-ahead price under the revision policy
    dam_choice, dam_dupes = select_revision(dam_obs, revision_policy)
    if dam_choice is None:
        return result(
            MISSING_DAY_AHEAD,
            evidence=ev,
            reasons=("no stored day-ahead observation for this hour",),
        )
    dam_ref = _rev(dam_choice)
    if dam_dupes:
        return result(
            INVALID_INPUT,
            dam_revision=dam_ref,
            evidence=ev,
            reasons=("the day-ahead hour has two observations with the same revision number",),
        )
    if not dam_choice.price_present:
        return result(
            MISSING_DAY_AHEAD,
            dam_revision=dam_ref,
            evidence=ev,
            reasons=("the selected day-ahead revision has a blank (missing) price",),
        )

    # 5. partition candidates by source-native identity
    want_hour = str(int(hour.hour_ending[:2]))
    matching, other_flag, excluded = [], [], []
    for obs in rt_candidates:
        i = obs.interval
        if i.delivery_date_raw != hour.delivery_date_raw:
            excluded.append({**_rt_dict(obs), "reason": "different DeliveryDate"})
        elif i.settlement_point != hour.settlement_point:
            excluded.append({**_rt_dict(obs), "reason": "different settlement point"})
        elif (hour.location_type, i.settlement_point_type) not in chosen_map.compatible_types:
            excluded.append(
                {
                    **_rt_dict(obs),
                    "reason": f"type {i.settlement_point_type!r} is not the verified "
                    f"real-time type for a day-ahead {hour.location_type!r}",
                }
            )
        elif i.delivery_hour != want_hour:
            excluded.append({**_rt_dict(obs), "reason": "different DeliveryHour"})
        elif i.dst_flag != hour.dst_flag:
            other_flag.append(obs)
        else:
            matching.append(obs)
    excluded_t = tuple(excluded)
    dst = {
        "day_ahead": hour.dst_flag,
        "real_time_same_flag": len({o.interval.key() for o in matching}),  # distinct intervals
        "real_time_other_flag": sorted({o.interval.dst_flag for o in other_flag}),
    }
    if not matching and not other_flag:
        if excluded and all(x["reason"] != "different DeliveryHour" for x in excluded):
            return result(
                INCOMPATIBLE_IDENTITY,
                dam_revision=dam_ref,
                excluded=excluded_t,
                evidence=ev,
                dst=dst,
                reasons=("every candidate differs from the day-ahead identity",),
            )
        return result(
            MISSING_REAL_TIME,
            dam_revision=dam_ref,
            excluded=excluded_t,
            evidence=ev,
            dst=dst,
            missing_intervals=chosen_map.expected_intervals,
            **counts,
            reasons=("no stored real-time interval carries this hour's labels",),
        )
    if not matching:
        flags = {o.interval.dst_flag for o in other_flag}
        unknown = sorted(flags - set(KNOWN_DST_FLAGS))
        return result(
            AMBIGUOUS_DST,
            dam_revision=dam_ref,
            excluded=excluded_t
            + tuple({**_rt_dict(o), "reason": "other DSTFlag"} for o in other_flag),
            evidence=ev,
            dst=dst,
            reasons=(
                f"real-time intervals for this hour exist only with DSTFlag "
                f"{sorted(flags)}; the day-ahead hour has {hour.dst_flag!r}"
                + (f" ({unknown} undocumented)" if unknown else "")
                + ". DSTFlag is never rewritten, so the hour is not matched.",
            ),
        )

    # 6. revision policy per interval identity, then completeness
    by_key: dict[tuple, list[RtObservation]] = {}
    for obs in matching:
        by_key.setdefault(obs.interval.key(), []).append(obs)
    selected, conflicts, duplicates = [], [], []
    for _key, group in sorted(by_key.items(), key=lambda kv: int(kv[0][2])):
        chosen, dupes = select_revision(group, revision_policy)
        if dupes:
            duplicates.append(chosen.interval.label())
            continue
        if len({o.revision for o in group}) > 1:
            conflicts.append(
                {
                    "interval": chosen.interval.label(),
                    "revisions": sorted(o.revision for o in group),
                    "selected": chosen.revision,
                    "policy": revision_policy,
                }
            )
        selected.append(chosen)
    present = {o.interval.delivery_interval for o in selected}
    expected = chosen_map.expected_intervals
    missing = tuple(x for x in expected if x not in present)
    unexpected = sorted(present - set(expected), key=int)
    blank = [o.interval.label() for o in selected if not o.price_present]
    common = {
        "dam_revision": dam_ref,
        "matched": tuple(_rt_dict(o) for o in selected),
        **counts,
        "observed_interval_count": len(selected),
        "missing_intervals": missing,
        "duplicate_intervals": tuple(duplicates),
        "revision_conflicts": tuple(conflicts),
        "excluded": excluded_t
        + tuple({**_rt_dict(o), "reason": "other DSTFlag"} for o in other_flag),
        "evidence": ev,
        "dst": dst,
    }
    reasons = []
    if missing:
        reasons.append(f"real-time interval(s) {', '.join(missing)} not stored")
    if duplicates:
        reasons.append(
            "duplicate interval(s) the revision policy cannot resolve: " + "; ".join(duplicates)
        )
    if unexpected:
        reasons.append(f"DeliveryInterval(s) {unexpected} are outside the verified set")
    if blank:
        reasons.append("blank (missing) real-time price: " + "; ".join(blank))
    if reasons:
        return result(ALIGNED_INCOMPLETE, reasons=tuple(reasons), **common)
    return result(
        ALIGNED_COMPLETE,
        reasons=(
            f"all {len(expected)} verified real-time intervals present once under "
            f"{revision_policy}, each with a published price",
        ),
        **common,
    )
