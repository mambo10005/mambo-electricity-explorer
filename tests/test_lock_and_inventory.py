"""Offline checks on the lock file and the dependency license inventory.

`uv lock --check` (run by scripts/quality.py) proves the lock matches pyproject.toml;
these tests cover what uv does not: unused dependencies and inventory drift.
"""

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = "mambo-electricity-explorer"


def _pyproject() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))


def _locked() -> set[tuple[str, str]]:
    lock = tomllib.loads((REPO / "uv.lock").read_text("utf-8"))
    return {(p["name"], p["version"]) for p in lock["package"] if p["name"] != PROJECT}


# Import name for each declared runtime dependency.
IMPORT_NAMES = {
    "streamlit": "streamlit",
    "pyyaml": "yaml",
    "duckdb": "duckdb",
    "pyarrow": "pyarrow",
    "mambo-power": "mambo_power",
}


def test_every_declared_runtime_dependency_is_used_in_src():
    """Replaces the Stage 2 guard that forbade duckdb/pyarrow before they were used."""
    dependencies = _pyproject()["project"]["dependencies"]
    declared = {re.split(r"[<>=!~ ]", d, maxsplit=1)[0].lower() for d in dependencies}
    assert declared == set(IMPORT_NAMES)
    source = "\n".join(p.read_text("utf-8") for p in (REPO / "src").rglob("*.py"))
    for name in declared:
        module = IMPORT_NAMES[name]
        assert re.search(rf"^\s*(import|from) {module}\b", source, re.MULTILINE), name


def test_dev_tools_are_a_dependency_group_not_a_published_extra():
    pyproject = _pyproject()
    assert "optional-dependencies" not in pyproject["project"]
    assert any(d.startswith("ruff==") for d in pyproject["dependency-groups"]["dev"])


def test_lock_covers_runtime_and_dev_tools():
    names = {name for name, _ in _locked()}
    assert {"streamlit", "pyyaml", "pytest", "ruff"} <= names


def test_license_inventory_matches_lock():
    rows = set()
    for line in (REPO / "docs/dependency-licenses.md").read_text("utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0] not in ("Package", "---"):
            rows.add((cells[0], cells[1]))
    assert rows == _locked(), "regenerate with scripts/license_inventory.py"
