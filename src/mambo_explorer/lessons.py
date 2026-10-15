"""Load and validate versioned lesson content (Markdown with YAML front matter).

See docs/lesson-authoring.md for the schema. Validation runs on every load and in tests,
so malformed or over-claiming content (e.g. "human-reviewed" without a named reviewer)
cannot reach the UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from importlib.resources import files

import yaml

from mambo_explorer.catalog import learning_sequence

REVIEW_STATUSES = ("unreviewed", "human-reviewed")
IMPLEMENTATION_STATUSES = ("implemented", "draft")
EXERCISE_KINDS = ("data", "concept")
CALCULATION_IDS = ("power_energy", "series_summary", "coverage", "forecast_error")
DATA_PANELS = ("power_energy_example", "demand_series", "forecast_comparison", "coverage")
REQUIRED = (
    "lesson_id",
    "title",
    "order",
    "sequence_stage",
    "prerequisites",
    "objectives",
    "content_version",
    "effective_date",
    "authored_by",
    "authored_at",
    "reviewed_at",
    "reviewed_by",
    "review_status",
    "sources",
    "dataset_bindings",
    "calculation_ids",
    "data_panels",
    "exercises",
    "glossary_terms",
    "limitations",
    "implementation_status",
)
SECTIONS = ("## Beginner", "## Technical detail")
_SEMVER = re.compile(r"\d+\.\d+\.\d+")


class LessonError(ValueError):
    pass


@dataclass(frozen=True)
class Lesson:
    meta: dict
    beginner: str
    technical: str

    @property
    def id(self) -> str:
        return self.meta["lesson_id"]

    @property
    def title(self) -> str:
        return self.meta["title"]


def _content():
    return files("mambo_explorer.content")


def load_glossary() -> dict[str, dict]:
    entries = yaml.safe_load(_content().joinpath("glossary.yaml").read_text("utf-8"))["terms"]
    glossary = {}
    for entry in entries:
        for key in ("term", "definition"):
            if not str(entry.get(key, "")).strip():
                raise LessonError(f"glossary entry missing {key}: {entry}")
        if entry["term"] in glossary:
            raise LessonError(f"duplicate glossary term {entry['term']}")
        glossary[entry["term"]] = entry
    return glossary


def parse_lesson(text: str, source: str = "<string>") -> Lesson:
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text.replace("\r\n", "\n"), re.DOTALL)
    if not match:
        raise LessonError(f"{source}: missing YAML front matter")
    meta = yaml.safe_load(match.group(1))
    body = match.group(2)
    positions = [body.find(s) for s in SECTIONS]
    if any(p < 0 for p in positions) or positions != sorted(positions):
        raise LessonError(f"{source}: body needs '{SECTIONS[0]}' then '{SECTIONS[1]}' sections")
    beginner = body[positions[0] + len(SECTIONS[0]) : positions[1]].strip()
    technical = body[positions[1] + len(SECTIONS[1]) :].strip()
    if not beginner or not technical:
        raise LessonError(f"{source}: empty beginner or technical section")
    lesson = Lesson(meta, beginner, technical)
    validate_meta(meta, source)
    return lesson


def _is_date(value) -> bool:
    if isinstance(value, date):
        return True
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def validate_meta(meta: dict, source: str) -> None:
    def fail(msg: str):
        raise LessonError(f"{source}: {msg}")

    if not isinstance(meta, dict):
        fail("front matter is not a mapping")
    missing = [k for k in REQUIRED if k not in meta]
    if missing:
        fail(f"missing fields {missing}")
    if not re.fullmatch(r"[a-z0-9-]+", str(meta["lesson_id"])):
        fail("lesson_id must be lowercase letters, digits, and hyphens")
    if not _SEMVER.fullmatch(str(meta["content_version"])):
        fail("content_version must be semantic (e.g. 1.0.0)")
    if meta["sequence_stage"] not in {s["key"] for s in learning_sequence()}:
        fail(f"unknown sequence_stage {meta['sequence_stage']!r}")
    if meta["effective_date"] is not None and not _is_date(meta["effective_date"]):
        fail("effective_date must be a date or null")
    if not str(meta["authored_by"]).strip() or not _is_date(meta["authored_at"]):
        fail("authored_by and authored_at are required")

    # Review: creation is not review. Agent-authored content stays "unreviewed".
    status = meta["review_status"]
    if status not in REVIEW_STATUSES:
        fail(f"review_status must be one of {REVIEW_STATUSES}")
    if status == "human-reviewed":
        if not meta["reviewed_by"] or not _is_date(meta["reviewed_at"]):
            fail("human-reviewed content needs reviewed_by and reviewed_at")
        if str(meta["reviewed_by"]).strip().lower() == str(meta["authored_by"]).strip().lower():
            fail("reviewer must differ from author")
        if (
            "agent" in str(meta["reviewed_by"]).lower()
            or "claude" in str(meta["reviewed_by"]).lower()
        ):
            fail("an AI agent cannot be the human reviewer")
    elif meta["reviewed_by"] is not None or meta["reviewed_at"] is not None:
        fail("unreviewed content must have null reviewed_by and reviewed_at")

    if meta["implementation_status"] not in IMPLEMENTATION_STATUSES:
        fail(f"implementation_status must be one of {IMPLEMENTATION_STATUSES}")
    for key in ("objectives", "limitations"):
        if not meta[key] or not all(str(x).strip() for x in meta[key]):
            fail(f"{key} must be a non-empty list")
    for src in meta["sources"]:
        if not {"id", "title", "url", "accessed"} <= set(src) or not _is_date(src["accessed"]):
            fail(f"source needs id, title, url, accessed date: {src}")
        if not str(src["url"]).startswith("https://"):
            fail(f"source url must be https: {src['url']}")
    for binding in meta["dataset_bindings"]:
        if not {"dataset", "route", "entity", "metrics"} <= set(binding):
            fail(f"dataset binding needs dataset, route, entity, metrics: {binding}")
    unknown_calcs = set(meta["calculation_ids"]) - set(CALCULATION_IDS)
    if unknown_calcs:
        fail(f"unknown calculation_ids {sorted(unknown_calcs)}")
    unknown_panels = set(meta["data_panels"]) - set(DATA_PANELS)
    if unknown_panels:
        fail(f"unknown data_panels {sorted(unknown_panels)}")
    from mambo_explorer.exercises import GENERATORS  # local import avoids a cycle

    ids = set()
    for ex in meta["exercises"]:
        if not {"exercise_id", "kind", "generator", "calculation_id"} <= set(ex):
            fail(f"exercise needs exercise_id, kind, generator, calculation_id: {ex}")
        if ex["kind"] not in EXERCISE_KINDS or ex["generator"] not in GENERATORS:
            fail(f"exercise {ex['exercise_id']}: bad kind or unknown generator")
        if ex["calculation_id"] not in meta["calculation_ids"]:
            fail(f"exercise {ex['exercise_id']}: calculation_id not declared by the lesson")
        if ex["kind"] == "data" and not meta["dataset_bindings"]:
            fail(f"exercise {ex['exercise_id']}: data exercise needs a dataset binding")
        if ex["exercise_id"] in ids:
            fail(f"duplicate exercise_id {ex['exercise_id']}")
        ids.add(ex["exercise_id"])
    if not meta["exercises"]:
        fail("at least one exercise is required")


def load_lessons() -> list[Lesson]:
    folder = _content().joinpath("lessons")
    lessons = [
        parse_lesson(entry.read_text("utf-8"), entry.name)
        for entry in sorted(folder.iterdir(), key=lambda e: e.name)
        if entry.name.endswith(".md")
    ]
    by_id = {}
    for lesson in lessons:
        if lesson.id in by_id:
            raise LessonError(f"duplicate lesson_id {lesson.id}")
        by_id[lesson.id] = lesson
    glossary = load_glossary()
    for lesson in lessons:
        for prereq in lesson.meta["prerequisites"]:
            if prereq not in by_id:
                raise LessonError(f"{lesson.id}: unknown prerequisite {prereq}")
        missing_terms = set(lesson.meta["glossary_terms"]) - set(glossary)
        if missing_terms:
            raise LessonError(f"{lesson.id}: glossary terms not defined {sorted(missing_terms)}")
    _check_acyclic(by_id)
    return sorted(lessons, key=lambda le: (le.meta["order"], le.id))


def _check_acyclic(by_id: dict[str, Lesson]) -> None:
    state: dict[str, int] = {}

    def visit(lesson_id: str) -> None:
        if state.get(lesson_id) == 1:
            raise LessonError(f"prerequisite cycle through {lesson_id}")
        if state.get(lesson_id) == 2:
            return
        state[lesson_id] = 1
        for prereq in by_id[lesson_id].meta["prerequisites"]:
            visit(prereq)
        state[lesson_id] = 2

    for lesson_id in by_id:
        visit(lesson_id)
