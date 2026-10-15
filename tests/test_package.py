import tomllib
from pathlib import Path

import mambo_explorer

REPO = Path(__file__).resolve().parents[1]


def test_package_imports_with_version_matching_pyproject():
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    assert mambo_explorer.__version__ == pyproject["project"]["version"]


def test_private_publication_safeguard_preserved():
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    assert "Private :: Do Not Upload" in pyproject["project"]["classifiers"]
    assert "license" not in pyproject["project"]


def test_modules_import():
    from mambo_explorer import catalog, navigation, pages  # noqa: F401
