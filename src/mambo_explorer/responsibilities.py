"""Load and validate the regulatory responsibility records (content/responsibilities.yaml).

Educational only (ADR 0012). Each record maps one paraphrased claim to one official source
section and says which source is relevant to investigate for an activity. Nothing here
decides whether a rule applies to anyone. Validation runs on every load and in tests, so a
record that over-claims (a proposal with an effective date, a retrieval date posing as an
effective date, applicability wording, a missing source) cannot reach the UI.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from importlib.resources import files

import yaml

REVIEW_STATUSES = ("unreviewed", "human-reviewed")
DOCUMENT_TYPES = {
    "statute": "binding-requirement",
    "regulation": "binding-requirement",
    "final-rule": "binding-requirement",
    "tariff-index": "approved-tariff-or-rule",
    "official-page": "official-guidance",
    "proposed-rule": "proposed-change",
    "notice": "proposed-change",
}
STATUSES = (
    "binding-requirement",
    "approved-tariff-or-rule",
    "official-guidance",
    "educational-summary",
    "proposed-change",
)
ACTIVITIES = (
    "wholesale-transactions",
    "retail-service",
    "reliability",
    "emergency-reporting",
    "procurement",
    "financial-derivatives",
)
RECORD_FIELDS = (
    "id",
    "authority_id",
    "organization_type",
    "activity",
    "status",
    "jurisdiction_scope",
    "supported_responsibility",
    "explicit_limitations",
    "source_reference",
    "source_section",
    "source_version",
    "published_date",
    "effective_date",
    "retrieved_at",
    "human_review_status",
)
# Wording that turns "a source to investigate" into an applicability conclusion.
CONCLUSIVE = re.compile(
    r"you (are|must|shall)|legally required|must comply with this|applies to you"
    r"|your organization (is|must)|you need to file",
    re.IGNORECASE,
)


class ResponsibilityError(ValueError):
    pass


@dataclass(frozen=True)
class Catalog:
    set_version: str
    retrieved_at: date
    statuses: dict[str, str]
    activities: dict[str, dict]
    authorities: dict[str, dict]
    organization_types: dict[str, str]
    sources: dict[str, dict]
    records: tuple[dict, ...]
    open_questions: tuple[dict, ...]
    source_gaps: tuple[dict, ...]
    fingerprint: str  # changes whenever the content changes; exercises key answers on it

    def for_activity(self, activity: str) -> list[dict]:
        return [r for r in self.records if r["activity"] == activity]

    def record(self, record_id: str) -> dict:
        return next(r for r in self.records if r["id"] == record_id)


def _is_date(value) -> bool:
    return isinstance(value, date)


def validate(data: dict) -> Catalog:
    def fail(msg: str):
        raise ResponsibilityError(msg)

    if not isinstance(data, dict):
        fail("responsibility file is not a mapping")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(data.get("set_version"))):
        fail("set_version must be semantic")
    statuses = {s["key"]: s["label"] for s in data["statuses"]}
    if tuple(statuses) != STATUSES:
        fail(f"statuses must be exactly {STATUSES}")
    activities = {a["key"]: a for a in data["activities"]}
    if tuple(activities) != ACTIVITIES:
        fail(f"activities must be exactly {ACTIVITIES}")
    org_types = dict(data["organization_types"])
    authorities = {a["id"]: a for a in data["authorities"]}
    for a in authorities.values():
        if a["organization_type"] not in org_types:
            fail(f"authority {a['id']}: unknown organization_type")
    sources = {}
    for s in data["sources"]:
        if not {"id", "title", "publisher", "document_type", "url"} <= set(s):
            fail(f"source needs id, title, publisher, document_type, url: {s}")
        if s["document_type"] not in DOCUMENT_TYPES:
            fail(f"source {s['id']}: unknown document_type {s['document_type']!r}")
        if not str(s["url"]).startswith("https://"):
            fail(f"source {s['id']}: url must be https")
        if s["id"] in sources:
            fail(f"duplicate source {s['id']}")
        sources[s["id"]] = s

    ids: set[str] = set()
    for r in data["records"]:
        rid = r.get("id", "?")
        missing = [k for k in RECORD_FIELDS if k not in r]
        if missing:
            fail(f"record {rid}: missing fields {missing}")
        if rid in ids:
            fail(f"duplicate record {rid}")
        ids.add(rid)
        if r["authority_id"] not in authorities:
            fail(f"record {rid}: unknown authority {r['authority_id']}")
        if r["organization_type"] != authorities[r["authority_id"]]["organization_type"]:
            fail(f"record {rid}: organization_type differs from its authority's")
        if r["activity"] not in activities:
            fail(f"record {rid}: unknown activity {r['activity']}")
        if r["status"] not in statuses:
            fail(f"record {rid}: unknown status {r['status']}")
        source = sources.get(r["source_reference"])
        if source is None:
            fail(f"record {rid}: unknown source {r['source_reference']}")
        if (
            r["status"] != "educational-summary"
            and DOCUMENT_TYPES[source["document_type"]] != r["status"]
        ):
            fail(f"record {rid}: status {r['status']} does not match its source's type")
        for key in (
            "jurisdiction_scope",
            "supported_responsibility",
            "source_section",
            "source_version",
        ):
            if not str(r[key]).strip():
                fail(f"record {rid}: {key} is empty")
        if not r["explicit_limitations"] or not all(
            str(x).strip() for x in r["explicit_limitations"]
        ):
            fail(f"record {rid}: explicit_limitations must be a non-empty list")
        texts = [r["supported_responsibility"], *r["explicit_limitations"]]
        if any(CONCLUSIVE.search(str(t)) for t in texts):
            fail(f"record {rid}: wording states an applicability conclusion")

        # Dates: unknown is null; retrieval is never an effective date.
        for key in ("published_date", "effective_date"):
            if r[key] is not None and not _is_date(r[key]):
                fail(f"record {rid}: {key} must be a date or null")
        if not _is_date(r["retrieved_at"]):
            fail(f"record {rid}: retrieved_at must be a date")
        if r["status"] == "proposed-change" and r["effective_date"] is not None:
            fail(f"record {rid}: a proposed change cannot carry an effective date")
        if r["effective_date"] is not None:
            if not str(r.get("effective_date_basis", "")).strip():
                fail(f"record {rid}: an effective_date needs effective_date_basis")
            if r["published_date"] is None or r["effective_date"] < r["published_date"]:
                fail(f"record {rid}: effective_date needs a published_date on or before it")
        elif "effective_date_basis" in r:
            fail(f"record {rid}: effective_date_basis without an effective_date")
        if r["published_date"] is not None and r["published_date"] > r["retrieved_at"]:
            fail(f"record {rid}: published after it was retrieved")

        status = r["human_review_status"]
        if status not in REVIEW_STATUSES:
            fail(f"record {rid}: human_review_status must be one of {REVIEW_STATUSES}")
        reviewer = r.get("reviewed_by")
        if status == "human-reviewed":
            if not reviewer or not _is_date(r.get("reviewed_at")):
                fail(f"record {rid}: human-reviewed needs reviewed_by and reviewed_at")
            if "agent" in str(reviewer).lower() or "claude" in str(reviewer).lower():
                fail(f"record {rid}: an AI agent cannot be the human reviewer")
        elif reviewer is not None or r.get("reviewed_at") is not None:
            fail(f"record {rid}: unreviewed records must not name a reviewer")

    for r in data["records"]:
        unknown = set(r.get("related", [])) - ids
        if unknown:
            fail(f"record {r['id']}: unknown related records {sorted(unknown)}")
    for q in data["open_questions"]:
        if not set(q["activities"]) <= set(activities) or not str(q["text"]).strip():
            fail(f"open question {q.get('id')}: bad activities or empty text")
    for g in data["source_gaps"]:
        if not str(g.get("source", "")).strip() or not str(g.get("outcome", "")).strip():
            fail(f"source gap needs source and outcome: {g}")

    canonical = yaml.safe_dump(data, sort_keys=True, default_flow_style=False)
    return Catalog(
        set_version=str(data["set_version"]),
        retrieved_at=data["retrieved_at"],
        statuses=statuses,
        activities=activities,
        authorities=authorities,
        organization_types=org_types,
        sources=sources,
        records=tuple(data["records"]),
        open_questions=tuple(data["open_questions"]),
        source_gaps=tuple(data["source_gaps"]),
        fingerprint=hashlib.sha256(canonical.encode()).hexdigest()[:12],
    )


def raw() -> dict:
    text = files("mambo_explorer.content").joinpath("responsibilities.yaml").read_text("utf-8")
    return yaml.safe_load(text)


@lru_cache(maxsize=1)
def load() -> Catalog:
    return validate(raw())
