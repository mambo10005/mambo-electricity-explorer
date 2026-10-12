"""Suite-wide isolation: no test may read or write the developer's real data directory.

Three independent layers (docs/testing-isolation.md):
1. MAMBO_DATA_DIR points at a session temp directory. Tests that need their own directory
   still override it with monkeypatch; undoing that falls back here, never to ./data.
2. MAMBO_FORBIDDEN_DATA_DIRS names the real ./data, so the app's own configuration check
   (config.validate_data_dir) refuses it under any spelling: other casing, relative paths,
   symlinks/junctions, or aliases.
3. The working directory is a session temp directory, so the `./data` fallback and any
   repository `.env` (with credentials) are out of reach even if a test deletes both
   variables.
At the end of the session, the real ./data tree must be unchanged (paths and mtimes). The
comparison is kept in memory only.

Found in Stage 9: a test's monkeypatch.undo() dropped its MAMBO_DATA_DIR override and an
AppTest rerun wrote a lesson "viewed" mark into the real ./data/learn/progress.json.
"""

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REAL_DATA = REPO / "data"


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
    saved = {k: os.environ.get(k) for k in ("MAMBO_DATA_DIR", "MAMBO_FORBIDDEN_DATA_DIRS")}
    old_cwd = os.getcwd()
    os.environ["MAMBO_DATA_DIR"] = str(tmp_path_factory.mktemp("session-data"))
    os.environ["MAMBO_FORBIDDEN_DATA_DIRS"] = str(REAL_DATA)
    cwd = tmp_path_factory.mktemp("session-cwd")
    # An empty .git marker makes the scratch cwd its own repository root. Without it,
    # config.find_repo_root walks up to whatever repository encloses the temp folder (on
    # this machine the user's home is a Git repository) and rejects every temp data dir.
    (cwd / ".git").mkdir()
    os.chdir(cwd)
    yield
    os.chdir(old_cwd)
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    after = _fingerprint(REAL_DATA)
    changed = set(after) ^ set(before) or {k for k in after if after[k] != before.get(k)}
    assert after == before, f"tests changed the real data directory: {sorted(changed)}"
