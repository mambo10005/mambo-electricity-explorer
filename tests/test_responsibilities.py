"""Responsibility records, compliance exercises, and lesson claim links (offline, ADR 0012)."""

import copy
import re
from datetime import date
from importlib.resources import files

import pytest

from mambo_explorer import compliance_exercises as ce
from mambo_explorer import responsibilities as rs
from mambo_explorer.lessons import LessonError, load_lessons, parse_lesson

CAT = rs.load()


def _bad(mutate, message):
    data = copy.deepcopy(rs.raw())
    mutate(data)
    with pytest.raises(rs.ResponsibilityError, match=message):
        rs.validate(data)


def _rec(data, record_id):
    return next(r for r in data["records"] if r["id"] == record_id)


# --- schema -------------------------------------------------------------------------------


def test_every_record_has_the_required_fields_and_known_references():
    assert len(CAT.records) >= 15
    for r in CAT.records:
        assert set(rs.RECORD_FIELDS) <= set(r), r["id"]
        assert r["authority_id"] in CAT.authorities
        assert r["source_reference"] in CAT.sources
        assert r["human_review_status"] == "unreviewed"  # agent-authored; BL-3
        assert r["explicit_limitations"]
        assert isinstance(r["retrieved_at"], date)


def test_every_activity_has_records_and_named_sources_cover_the_brief():
    for activity in rs.ACTIVITIES:
        assert CAT.for_activity(activity), activity
    org_types = {r["organization_type"] for r in CAT.records}
    assert {
        "federal-regulator",
        "electric-reliability-organization",
        "regional-entity",
        "federal-department",
        "state-regulator",
        "system-operator",
        "federal-derivatives-regulator",
    } <= org_types


def test_sources_are_official_https_pages_and_none_is_unused():
    used = {r["source_reference"] for r in CAT.records}
    assert used == set(CAT.sources)
    hosts = {re.match(r"https://([^/]+)/", s["url"]).group(1) for s in CAT.sources.values()}
    assert hosts == {
        "www.govinfo.gov",
        "www.ecfr.gov",
        "www.cpuc.ca.gov",
        "www.ercot.com",
        "www.iso-ne.com",
    }


def test_cpuc_records_are_marked_california_specific():
    for r in CAT.records:
        if r["authority_id"] == "cpuc":
            assert "California" in r["jurisdiction_scope"]


def test_status_follows_the_source_document_type():
    for r in CAT.records:
        doc = CAT.sources[r["source_reference"]]["document_type"]
        assert rs.DOCUMENT_TYPES[doc] == r["status"], r["id"]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: _rec(d, "ferc-wholesale-sales").pop("source_section"), "missing fields"),
        (
            lambda d: _rec(d, "ferc-wholesale-sales").update(source_reference="nope"),
            "unknown source",
        ),
        (lambda d: _rec(d, "ferc-wholesale-sales").update(activity="trading"), "unknown activity"),
        (lambda d: _rec(d, "ferc-wholesale-sales").update(authority_id="sec"), "unknown authority"),
        (
            lambda d: _rec(d, "ferc-wholesale-sales").update(organization_type="state-regulator"),
            "organization_type differs",
        ),
        (lambda d: _rec(d, "ferc-wholesale-sales").update(explicit_limitations=[]), "limitations"),
        (
            lambda d: _rec(d, "ercot-retail-switching").update(status="binding-requirement"),
            "does not match",
        ),
        (lambda d: d["sources"][0].update(url="http://example.com/"), "https"),
        (lambda d: _rec(d, "ferc-wholesale-sales").update(related=["ghost"]), "unknown related"),
        (lambda d: d["records"].append(copy.deepcopy(d["records"][0])), "duplicate record"),
    ],
)
def test_schema_violations_are_rejected(mutate, message):
    _bad(mutate, message)


# --- dates ---------------------------------------------------------------------------------


def test_unknown_dates_are_null_and_retrieval_is_never_an_effective_date():
    for r in CAT.records:
        assert r["effective_date"] != r["retrieved_at"], r["id"]
        if r["effective_date"] is None:
            assert "effective_date_basis" not in r
        else:
            assert r["effective_date_basis"].strip() and r["published_date"] is not None
    statutes = [
        r for r in CAT.records if CAT.sources[r["source_reference"]]["document_type"] == "statute"
    ]
    assert statutes and all(
        r["published_date"] is None and r["effective_date"] is None for r in statutes
    )


def test_only_the_final_rule_carries_an_effective_date_and_it_is_the_stated_one():
    dated = {r["id"]: r["effective_date"] for r in CAT.records if r["effective_date"]}
    assert dated == {"cip-003-11-final": date(2026, 5, 26)}
    final = CAT.record("cip-003-11-final")
    assert final["published_date"] == date(2026, 3, 24)
    assert "not necessarily the standard" in final["effective_date_basis"]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: _rec(d, "cpuc-utility-service").update(published_date="2026"), "date or null"),
        (
            lambda d: _rec(d, "ferc-wholesale-sales").update(effective_date=date(2026, 10, 11)),
            "effective_date_basis",
        ),
        (
            lambda d: _rec(d, "cip-003-11-final").update(published_date=None),
            "published_date on or before",
        ),
        (
            lambda d: _rec(d, "cip-003-11-final").update(effective_date=date(2026, 1, 1)),
            "published_date on or before",
        ),
        (
            lambda d: _rec(d, "ferc-wholesale-sales").update(effective_date_basis="x"),
            "basis without",
        ),
        (
            lambda d: _rec(d, "cip-003-11-final").update(published_date=date(2027, 1, 1)),
            "after it was retrieved|on or before",
        ),
    ],
)
def test_date_violations_are_rejected(mutate, message):
    _bad(mutate, message)


# --- proposals ------------------------------------------------------------------------------


def test_proposals_are_never_effective_and_are_separate_from_the_final_rule():
    proposals = [r for r in CAT.records if r["status"] == "proposed-change"]
    assert {r["id"] for r in proposals} == {"cip-003-11-proposal", "doe-417-collection"}
    for r in proposals:
        assert r["effective_date"] is None
        assert CAT.sources[r["source_reference"]]["document_type"] in ("proposed-rule", "notice")
    proposal, final = CAT.record("cip-003-11-proposal"), CAT.record("cip-003-11-final")
    assert proposal["source_reference"] != final["source_reference"]
    assert final["status"] == "binding-requirement"
    assert "cip-003-11-final" in proposal["related"]


def test_a_proposal_with_an_effective_date_is_rejected():
    def mutate(d):
        _rec(d, "cip-003-11-proposal").update(
            effective_date=date(2025, 11, 24), effective_date_basis="comments closed"
        )

    _bad(mutate, "proposed change cannot carry an effective date")


def test_a_proposal_cannot_be_relabeled_binding():
    _bad(
        lambda d: _rec(d, "cip-003-11-proposal").update(status="binding-requirement"),
        "does not match",
    )


# --- wording, review, applicability -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "You are legally required to comply with this standard.",
        "This applies to you.",
        "You must file Form DOE-417.",
        "Your organization must register.",
    ],
)
def test_applicability_conclusions_are_rejected(text):
    _bad(
        lambda d: _rec(d, "doe-417-collection").update(supported_responsibility=text),
        "applicability",
    )


def test_shipped_wording_never_concludes_applicability():
    for r in CAT.records:
        for t in (r["supported_responsibility"], *r["explicit_limitations"]):
            assert not rs.CONCLUSIVE.search(t), r["id"]


def test_review_status_cannot_be_claimed_by_an_agent_or_left_half_filled():
    _bad(lambda d: _rec(d, "cpuc-utility-service").update(reviewed_by="Someone"), "must not name")

    def agent(d):
        _rec(d, "cpuc-utility-service").update(
            human_review_status="human-reviewed",
            reviewed_by="Claude agent",
            reviewed_at=date(2026, 10, 11),
        )

    _bad(agent, "AI agent")


def test_overlaps_are_represented_not_collapsed():
    # Several organizations per activity, with related records linking the overlaps.
    for activity in (
        "wholesale-transactions",
        "retail-service",
        "reliability",
        "procurement",
        "financial-derivatives",
    ):
        assert len({r["authority_id"] for r in CAT.for_activity(activity)}) >= 2, activity
    derivatives = {r["authority_id"] for r in CAT.for_activity("financial-derivatives")}
    assert derivatives == {"cftc", "ferc"}
    assert any("cftc-ferc-boundary" == q["id"] for q in CAT.open_questions)


def test_unresolved_questions_are_recorded_for_ercot_dates_and_versions():
    ids = {q["id"] for q in CAT.open_questions}
    assert {
        "ercot-federal-roles",
        "cip-003-11-dates",
        "doe-417-version",
        "cftc-ferc-boundary",
    } <= ids
    ercot = next(q for q in CAT.open_questions if q["id"] == "ercot-federal-roles")
    assert "not\nestablished" in ercot["text"] or "not established" in ercot["text"]


def test_inaccessible_sources_are_recorded_as_gaps():
    gaps = " ".join(g["source"] for g in CAT.source_gaps)
    for host in (
        "ferc.gov",
        "nerc.com",
        "texasre.org",
        "cftc.gov",
        "puc.texas.gov",
        "federalregister.gov",
    ):
        assert host in gaps, host


# --- exercises ----------------------------------------------------------------------------


def test_every_compliance_exercise_cites_existing_records_or_says_it_is_a_summary():
    for name, spec in ce.SPECS.items():
        ex = ce.generate({"exercise_id": name, "generator": name})
        for record_id in spec.records:
            CAT.record(record_id)
        if spec.records:
            assert "Sources: " in ex.explanation, name
        else:
            assert "Educational summary written for this app" in ex.explanation, name
        assert len(set(ex.options)) == 4 and ex.options[ex.answer_index] == spec.correct


def test_overlap_questions_need_more_than_one_source():
    for name in ce.OVERLAP:
        spec = ce.SPECS[name]
        assert len({CAT.record(r)["authority_id"] for r in spec.records}) >= 2
        assert spec.correct.startswith("More than one")
        assert all(d.startswith("Only") for d in spec.decoys[:2])


def test_applicability_questions_never_conclude_yes():
    for name in ce.UNRESOLVED:
        spec = ce.SPECS[name]
        assert "No conclusion is possible" in spec.correct
        assert "qualified person" in spec.correct


def test_synthetic_organization_is_labeled_and_no_authority_is_given_its_policy():
    synthetic = [s for s in ce.SPECS.values() if "SYNTHETIC" in s.question]
    assert synthetic
    assert "not by any authority" in ce.SYNTHETIC_POLICY
    for spec in synthetic:
        assert ce.generate(
            {"exercise_id": "x", "generator": next(k for k, v in ce.SPECS.items() if v is spec)}
        ).synthetic


def test_exercise_snapshot_follows_the_record_set():
    assert ce.snapshot_id() == f"compliance-{CAT.fingerprint}"
    changed = copy.deepcopy(rs.raw())
    _rec(changed, "cpuc-utility-service")["source_version"] = "edited"
    assert rs.validate(changed).fingerprint != CAT.fingerprint


# --- lessons ------------------------------------------------------------------------------


def test_compliance_lessons_link_every_claim_to_a_listed_source():
    lessons = {le.id: le for le in load_lessons()}
    for lesson_id in ("who-sets-the-rules", "requirement-to-evidence"):
        meta = lessons[lesson_id].meta
        assert meta["sequence_stage"] == "compliance" and meta["review_status"] == "unreviewed"
        urls = {s["url"] for s in meta["sources"]}
        for claim in meta["claims"]:
            assert CAT.sources[CAT.record(claim)["source_reference"]]["url"] in urls
        for ex in meta["exercises"]:
            assert set(ce.SPECS[ex["generator"]].records) <= set(meta["claims"])


def test_lesson_12_keeps_the_synthetic_policy_away_from_authorities():
    lesson = next(le for le in load_lessons() if le.id == "requirement-to-evidence")
    text = " ".join((lesson.beginner + " " + lesson.technical).split())
    assert "**SYNTHETIC**" in text and "SYN-1 is not a rule of any authority" in text
    assert "not certification" in text and "not regulatory approval" in text
    assert "deadline" not in lesson.beginner.lower()


def test_lesson_claims_must_exist_and_have_their_source_listed():
    lessons = files("mambo_explorer.content").joinpath("lessons")
    text = lessons.joinpath("12-requirement-to-evidence.md").read_text("utf-8")
    with pytest.raises(LessonError, match="record ids"):
        parse_lesson(text.replace("  - doe-417-collection\n", "  - made-up-claim\n", 1))
    dropped = re.sub(r"  - id: fr-2023-18729\n(    .*\n){3}", "", text, count=1)
    with pytest.raises(LessonError, match="not in the lesson's sources"):
        parse_lesson(dropped)
    with pytest.raises(LessonError, match="cites records not in claims"):
        parse_lesson(text.replace("  - cip-003-11-proposal\n", "", 1))
