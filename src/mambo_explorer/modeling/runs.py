"""Local persistence of model runs: one JSON file per run in <MAMBO_DATA_DIR>/model-runs/.

The data directory is gitignored, so runs never enter Git. Records are written
atomically and are never edited after writing. Failed runs are kept too, so the history
is honest.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from mambo_explorer.modeling.adapter import OpfRunRecord, RunRecord
from mambo_explorer.storage import atomic_write

_RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")
_KINDS = {"pf.dc": RunRecord, "pf.dispatch": RunRecord, "opf.dc": OpfRunRecord}


def _record(data: dict) -> RunRecord | OpfRunRecord:
    """Rebuild a saved record by its kind (records saved before Stage 7 have no kind: pf.dc)."""
    return _KINDS[data.get("kind", "pf.dc")](**data)


class RunStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "model-runs"

    def save(self, record: RunRecord | OpfRunRecord) -> Path:
        if not _RUN_ID.fullmatch(record.run_id):
            raise ValueError(f"invalid run id {record.run_id!r}")
        path = self.root / f"{record.run_id}.json"
        if path.exists():
            raise FileExistsError(f"run {record.run_id} already saved")
        atomic_write(path, record.to_json().encode("utf-8"))
        return path

    def load(self, run_id: str) -> RunRecord | OpfRunRecord:
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError(f"invalid run id {run_id!r}")
        return _record(json.loads((self.root / f"{run_id}.json").read_text("utf-8")))

    def recent(self, limit: int = 10, kind: str | None = None) -> list[RunRecord | OpfRunRecord]:
        if not self.root.is_dir():
            return []
        paths = sorted(
            (p for p in self.root.glob("*.json") if _RUN_ID.fullmatch(p.stem)), reverse=True
        )
        records = [_record(json.loads(p.read_text("utf-8"))) for p in paths]
        return [r for r in records if kind is None or r.kind == kind][:limit]
