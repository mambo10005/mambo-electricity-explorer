"""Offline checks on the lock file and the dependency license inventory.

`uv lock --check` (run by scripts/quality.py) proves the lock matches pyproject.toml;
these tests cover what uv does not: deferred dependencies and inventory drift.
"""

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = "mambo-electricity-explorer"


def _pyproject() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))


def _locked() -> set[tuple[str, str]]:
    lock = tomllib.loads((REPO / "uv.lock").read_text("utf-8"))
    return {(p["name"], p["version"]) for p in lock["package"] if p["name"] != PROJECT}


def test_storage_dependencies_not_declared_before_their_milestone():
    declared = " ".join(_pyproject()["project"]["dependencies"]).lower()
    assert "duckdb" not in declared
    assert "pyarrow" not in declared


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
