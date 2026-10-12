"""Local learning progress and bookmarks: one JSON file in the gitignored data directory.

Three distinct states per lesson (none of them is a certification):
- viewed:                     the lesson page was opened
- exercise completed:         at least one exercise was answered (right or wrong)
- understanding demonstrated: every exercise in the lesson was answered correctly on
                              the first attempt for its question instance
No account and no cloud service: the file stays on this computer.
"""

from __future__ import annotations

import json
from pathlib import Path

from mambo_explorer.storage import atomic_write, now_utc

VERSION = 1
NOT_STARTED, VIEWED, EXERCISE_COMPLETED, UNDERSTANDING = (
    "not started",
    "viewed",
    "exercise completed",
    "understanding demonstrated",
)


class Progress:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "learn" / "progress.json"

    def load(self) -> dict:
        if not self.path.is_file():
            return {"version": VERSION, "lessons": {}}
        data = json.loads(self.path.read_text("utf-8"))
        if data.get("version") != VERSION:
            raise ValueError(f"unsupported progress file version {data.get('version')}")
        return data

    def _save(self, data: dict) -> None:
        atomic_write(self.path, json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))

    def _lesson(self, data: dict, lesson_id: str) -> dict:
        return data["lessons"].setdefault(
            lesson_id, {"viewed_at": None, "bookmarked": False, "exercises": {}}
        )

    def mark_viewed(self, lesson_id: str) -> None:
        data = self.load()
        lesson = self._lesson(data, lesson_id)
        if not lesson["viewed_at"]:
            lesson["viewed_at"] = now_utc().isoformat()
            self._save(data)

    def set_bookmark(self, lesson_id: str, on: bool) -> None:
        data = self.load()
        self._lesson(data, lesson_id)["bookmarked"] = bool(on)
        self._save(data)

    def record_answer(
        self,
        lesson_id: str,
        exercise_id: str,
        snapshot: str,
        correct: bool,
        result_refs: tuple[str, ...] = (),
    ) -> dict:
        """Record an attempt. A new snapshot starts a fresh question instance.

        `result_refs` are the model run ids a model-backed answer was computed from (kept with
        the question instance so the answer can be traced to saved runs)."""
        data = self.load()
        exercises = self._lesson(data, lesson_id)["exercises"]
        record = exercises.get(exercise_id)
        if record is None or record["snapshot_id"] != snapshot:
            record = {
                "snapshot_id": snapshot,
                "attempts": 0,
                "first_attempt_correct": None,
                "answered_correctly": False,
                "completed_at": None,
            }
            if result_refs:
                record["result_refs"] = list(result_refs)
            exercises[exercise_id] = record
        record["attempts"] += 1
        if record["first_attempt_correct"] is None:
            record["first_attempt_correct"] = bool(correct)
        record["answered_correctly"] = record["answered_correctly"] or bool(correct)
        record["completed_at"] = record["completed_at"] or now_utc().isoformat()
        self._save(data)
        return record

    def lesson_state(self, lesson_id: str, exercise_ids: list[str]) -> str:
        lesson = self.load()["lessons"].get(lesson_id)
        if not lesson or not lesson["viewed_at"]:
            return NOT_STARTED
        records = [lesson["exercises"].get(e) for e in exercise_ids]
        if exercise_ids and all(r and r["first_attempt_correct"] for r in records):
            return UNDERSTANDING
        if any(records):
            return EXERCISE_COMPLETED
        return VIEWED

    def bookmarked(self, lesson_id: str) -> bool:
        return bool(self.load()["lessons"].get(lesson_id, {}).get("bookmarked"))

    def exercise_record(self, lesson_id: str, exercise_id: str) -> dict | None:
        return self.load()["lessons"].get(lesson_id, {}).get("exercises", {}).get(exercise_id)
