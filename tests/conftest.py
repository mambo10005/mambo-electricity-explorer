"""Suite-wide isolation: no test may read or write the developer's real data directory.

Every test runs with MAMBO_DATA_DIR pointing at a session temp directory. Tests that need
their own directory still override it with monkeypatch; when that override is undone,
the variable falls back to this session directory, never to ./data. At the end of the
session, the real ./data tree must be byte-for-byte untouched (paths and mtimes).

Found in Stage 9: a test's monkeypatch.undo() dropped its MAMBO_DATA_DIR override and an
AppTest rerun wrote a lesson "viewed" mark into the real ./data/learn/progress.json.
"""

import os
from pathlib import Path

import pytest

REAL_DATA = Path(__file__).resolve().parents[1] / "data"


def _fingerprint(root: Path) -> dict[str, int]:
    if not root.is_dir():
        return {}
    return {
        str(p.relative_to(root)): p.stat().st_mtime_ns
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture(scope="session", autouse=True)
def _isolated_data_dir(tmp_path_factory):
    before = _fingerprint(REAL_DATA)
    previous = os.environ.get("MAMBO_DATA_DIR")
    os.environ["MAMBO_DATA_DIR"] = str(tmp_path_factory.mktemp("session-data"))
    yield
    if previous is None:
        os.environ.pop("MAMBO_DATA_DIR", None)
    else:
        os.environ["MAMBO_DATA_DIR"] = previous
    after = _fingerprint(REAL_DATA)
    assert after == before, (
        f"tests changed the real data directory: {set(after) ^ set(before) or 'mtimes'}"
    )
