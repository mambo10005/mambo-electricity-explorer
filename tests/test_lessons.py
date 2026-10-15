import re

import pytest

from mambo_explorer.lessons import LessonError, load_glossary, load_lessons, parse_lesson

EXPECTED = ["power-vs-energy", "reading-demand", "demand-vs-forecast", "missing-observations"]
VALID = """---
lesson_id: sample
title: Sample
order: 9
sequence_stage: fundamentals
prerequisites: []
objectives: [Learn a thing]
content_version: 1.0.0
effective_date: null
authored_by: Claude (AI agent)
authored_at: 2026-10-11
reviewed_by: null
reviewed_at: null
review_status: unreviewed
sources: [{id: s, title: S, url: "https://www.eia.gov/", accessed: 2026-10-11}]
dataset_bindings: []
calculation_ids: [power_energy]
data_panels: []
exercises:
  - exercise_id: e1
    kind: concept
    generator: power_energy_synthetic
    calculation_id: power_energy
glossary_terms: [MW]
limitations: [None really]
implementation_status: implemented
---

## Beginner

Text.

## Technical detail

More text.
"""


def test_four_lessons_load_in_order_with_valid_prerequisites():
    lessons = load_lessons()
    assert [le.id for le in lessons] == EXPECTED
    assert lessons[0].meta["prerequisites"] == []
    for earlier, later in zip(lessons, lessons[1:], strict=False):
        assert earlier.id in later.meta["prerequisites"]


def test_shipped_lessons_are_not_labeled_human_reviewed():
    for lesson in load_lessons():
        meta = lesson.meta
        assert meta["review_status"] == "unreviewed", lesson.id
        assert meta["reviewed_by"] is None and meta["reviewed_at"] is None
        assert "agent" in meta["authored_by"].lower()


def test_lessons_declare_required_fields_and_sources():
    for lesson in load_lessons():
        meta = lesson.meta
        assert re.fullmatch(r"\d+\.\d+\.\d+", str(meta["content_version"]))
        assert all(s["url"].startswith("https://www.eia.gov/") for s in meta["sources"])
        assert meta["exercises"] and meta["limitations"] and meta["objectives"]
        if any(e["kind"] == "data" for e in meta["exercises"]):
            assert meta["dataset_bindings"][0]["entity"] == "ERCO"


def test_lesson_text_does_not_hardcode_current_data():
    """Lessons must keep working after new collections and revisions."""
    for lesson in load_lessons():
        text = lesson.beginner + lesson.technical
        assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}", text), lesson.id  # no specific labels
        assert not re.search(r"\b(408|144|216|192)\b", text), lesson.id  # no current row counts


def test_lesson_text_respects_source_semantics():
    text = {le.id: (le.beginner + le.technical).lower() for le in load_lessons()}
    assert "not** a set of readings from customers' meters" in text["reading-demand"]
    assert (
        "does\nnot say why" in text["reading-demand"]
        or "does not say why" in text["reading-demand"]
    )
    assert "not** a trading test" in text["demand-vs-forecast"]
    assert "vintage" in text["demand-vs-forecast"]
    assert "does not guess why rows are missing" in text["missing-observations"]
    assert "operating day" not in text["missing-observations"].replace('"operating days"', "")


def test_glossary_covers_lesson_terms_and_acronyms():
    glossary = load_glossary()
    for acronym in ("MW", "MWh", "BA", "ERCOT", "EIA", "UTC", "MAE", "RMSE"):
        assert glossary[acronym].get("expansion"), acronym


def test_valid_sample_parses():
    assert parse_lesson(VALID).id == "sample"


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("review_status: unreviewed", "review_status: human-reviewed", "needs reviewed_by"),
        (
            "reviewed_by: null\nreviewed_at: null\nreview_status: unreviewed",
            "reviewed_by: Claude (AI agent)\nreviewed_at: 2026-10-12\n"
            "review_status: human-reviewed",
            "reviewer must differ",
        ),
        (
            "reviewed_by: null\nreviewed_at: null\nreview_status: unreviewed",
            "reviewed_by: Review Agent\nreviewed_at: 2026-10-12\nreview_status: human-reviewed",
            "AI agent cannot be the human reviewer",
        ),
        ("reviewed_by: null", "reviewed_by: Someone", "unreviewed content must have null"),
        ("content_version: 1.0.0", "content_version: v1", "semantic"),
        ("generator: power_energy_synthetic", "generator: made_up", "unknown generator"),
        ("kind: concept", "kind: data", "needs a dataset binding"),
        ("calculation_ids: [power_energy]", "calculation_ids: [magic]", "unknown calculation_ids"),
        ('url: "https://www.eia.gov/"', 'url: "http://example.com"', "https"),
        ("sequence_stage: fundamentals", "sequence_stage: astrology", "unknown sequence_stage"),
        ("## Technical detail", "## Details", "sections"),
        ("limitations: [None really]", "limitations: []", "limitations must be"),
    ],
)
def test_invalid_lessons_are_rejected(old, new, message):
    assert old in VALID
    with pytest.raises(LessonError, match=message):
        parse_lesson(VALID.replace(old, new))
