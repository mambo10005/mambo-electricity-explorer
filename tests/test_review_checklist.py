"""The human-review checklist must cover the current content and must not claim a review."""

import re
from pathlib import Path

from mambo_explorer.lessons import load_glossary, load_lessons

CHECKLIST = Path(__file__).resolve().parents[1] / "docs/review/human-review-checklist.md"


def _text() -> str:
    return CHECKLIST.read_text("utf-8")


def test_every_lesson_is_listed_at_its_current_content_version():
    text = _text()
    for lesson in load_lessons():
        heading = f"`{lesson.id}` · v{lesson.meta['content_version']}"
        assert heading in text, f"checklist out of date for {lesson.id}"
        for ex in lesson.meta["exercises"]:
            assert f"`{ex['exercise_id']}`" in text, (lesson.id, ex["exercise_id"])


def test_every_glossary_term_is_listed():
    text = _text()
    glossary = load_glossary()
    assert f"{len(glossary)} terms" in text
    listed = " ".join(text.split("## Glossary", 1)[1].split())  # ignore line wrapping
    for term in glossary:
        assert re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", listed), term


def test_review_fields_are_blank_and_no_review_is_claimed():
    text = _text()
    for field in ("Reviewer (name)", "Review date", "Approved? (yes / no / with changes)"):
        assert f"| {field} | |" in text, field
    assert "**Status: not reviewed by a person.**" in text
    assert "human-reviewed" not in text.replace("`review_status: human-reviewed`", "")
    for lesson in load_lessons():
        assert lesson.meta["review_status"] == "unreviewed"
        assert lesson.meta["reviewed_by"] is None and lesson.meta["reviewed_at"] is None
