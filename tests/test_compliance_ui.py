"""Compliance page (responsibility explorer) and lessons 11-12 via AppTest (offline)."""

import re

import pytest
from guards import assert_no_data_elements
from streamlit.testing.v1 import AppTest

from mambo_explorer import responsibilities as rs
from mambo_explorer import routes
from mambo_explorer.compliance import NOT_A_CONCLUSION
from mambo_explorer.lessons import load_lessons
from mambo_explorer.progress import Progress

PAGE = "from mambo_explorer.pages import render_page\nrender_page('compliance')\n"
LEARN = "from mambo_explorer.pages import render_page\nrender_page('learn')\n"
CAT = rs.load()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    return path


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return parts


def _table(at, *cols):
    return next((t.value for t in at.table if all(c in t.value.columns for c in cols)), None)


def test_page_frames_entries_as_sources_to_investigate(data_dir):
    at = AppTest.from_string(PAGE).run(timeout=30)
    assert not at.exception
    text = "\n".join(_texts(at))
    assert "relevant source to investigate" in text.lower()
    assert "never enough to decide it" in text and "not been reviewed by a" in text
    # The only "applies to you" is the disclaimer's negation.
    assert not rs.CONCLUSIVE.search(text.replace(NOT_A_CONCLUSION, ""))
    assert_no_data_elements(at)  # tables of source records only; no charts or metrics


@pytest.mark.parametrize("activity", rs.ACTIVITIES)
def test_each_activity_lists_its_records_with_links_limits_and_review(data_dir, activity):
    at = AppTest.from_string(PAGE)
    at.session_state["compliance_activity"] = activity
    at.run(timeout=30)
    assert not at.exception
    text = "\n".join(_texts(at))
    records = CAT.for_activity(activity)
    assert text.count("#### Relevant source to investigate: ") == len(records)
    for r in records:
        assert CAT.sources[r["source_reference"]]["url"] in text
        assert r["explicit_limitations"][0] in text
    assert text.count("review: unreviewed") == len(records)
    assert "a retrieval date, not an effective date" in text
    orgs = {r["authority_id"] for r in records}
    assert ("organizations have sources here" in text) == (len(orgs) > 1)


def test_reliability_shows_the_proposal_as_not_effective_and_the_final_rule_date(data_dir):
    at = AppTest.from_string(PAGE)
    at.session_state["compliance_activity"] = "reliability"
    at.run(timeout=30)
    text = "\n".join(_texts(at))
    assert "Proposed change: not an effective requirement." in text
    assert "Effective: none: this is a proposal, not an effective requirement" in text
    assert "Effective: 2026-05-26 (" in text
    assert re.search(r"Unresolved questions|implementation plan", text)
    assert any("implementation plan" in w.value for w in at.warning)


def test_claim_map_and_source_gaps_are_complete(data_dir):
    at = AppTest.from_string(PAGE).run(timeout=30)
    claims = _table(at, "Record", "Source", "Section")
    assert list(claims["Record"]) == [r["id"] for r in CAT.records]
    gaps = _table(at, "Source", "What happened")
    assert len(gaps) == len(CAT.source_gaps)
    status = _table(at, "ID", "Feature", "Status")
    assert dict(zip(status["ID"], status["Status"], strict=True)) == {
        "COMP-01": "planned",
        "COMP-02": "done",
        "COMP-03": "done",
        "COMP-04": "planned",
    }


def _open(lesson_id):
    at = AppTest.from_string(LEARN)
    at.session_state["lesson_choice"] = lesson_id
    return at.run(timeout=30)


@pytest.mark.parametrize(
    "lesson_id, count", [("who-sets-the-rules", 5), ("requirement-to-evidence", 6)]
)
def test_lessons_render_claims_table_and_exercises(data_dir, lesson_id, count):
    at = _open(lesson_id)
    assert not at.exception
    radios = [r for r in at.radio if r.label == "Your answer"]
    assert len(radios) == count
    claims = _table(at, "Claim (paraphrased)", "Source", "Section")
    lesson_claims = next(le for le in load_lessons() if le.id == lesson_id).meta["claims"]
    assert len(claims) == len(lesson_claims)
    assert any("Not yet reviewed by a person" in t for t in _texts(at))


def test_overlap_exercise_records_progress(data_dir):
    at = _open("who-sets-the-rules")
    radios = [r for r in at.radio if r.label == "Your answer"]
    overlap = next(r for r in radios if any(o.startswith("More than one") for o in r.options))
    overlap.set_value(next(o for o in overlap.options if o.startswith("More than one")))
    [b for b in at.button if b.label == "Check answer"][radios.index(overlap)].click()
    at.run(timeout=30)
    assert any("Correct." in s.value for s in at.success)
    record = Progress(data_dir).exercise_record("who-sets-the-rules", "layers-new-england")
    assert record["first_attempt_correct"] and record["snapshot_id"].startswith("compliance-")


def test_rendered_markdown_has_no_unescaped_dollar(data_dir):
    unescaped = re.compile(r"(?<!\\)\$")
    for at in (AppTest.from_string(PAGE).run(timeout=30), _open("requirement-to-evidence")):
        assert [t for t in _texts(at) if unescaped.search(t)] == []
