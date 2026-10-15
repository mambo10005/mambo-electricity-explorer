import re
from pathlib import Path

from mambo_explorer.catalog import data_labels, learning_sequence

REPO = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = [
    "README.md",
    "CLAUDE.md",
    ".env.example",
    "docs/PRD.md",
    "docs/architecture.md",
    "docs/feature-matrix.md",
    "docs/source-register.md",
    "docs/progress.md",
    "docs/github-workflow.md",
    "docs/decisions/README.md",
    "docs/decisions/0001-license.md",
    "docs/decisions/0002-application-stack.md",
    ".github/pull_request_template.md",
]


def _read(rel: str) -> str:
    return (REPO / rel).read_text("utf-8")


def test_required_documents_exist():
    missing = [rel for rel in REQUIRED_DOCS if not (REPO / rel).is_file()]
    assert not missing


def test_prd_separates_requirement_tiers_and_has_no_tbd():
    prd = _read("docs/PRD.md")
    for heading in ("Proposed design decisions", "Unresolved decisions"):
        assert re.search(rf"^## .*{heading}$", prd, re.MULTILINE), heading
    assert re.search(r"\*\*R-1\.\*\*", prd)
    assert "TBD" not in prd


def test_prd_covers_required_markets_and_authorities():
    prd = _read("docs/PRD.md")
    for term in (
        "ERCOT",
        "CAISO",
        "PJM",
        "MISO",
        "SPP",
        "NYISO",
        "ISO-NE",
        "non-ISO",
        "FERC",
        "NERC",
        "DOE",
        "PUC",
        "CFTC",
        "mambo-power",
        "EIA",
    ):
        assert term in prd, term


def test_license_remains_pending():
    assert not (REPO / "LICENSE").exists()
    assert "Proposed (no license chosen)" in _read("docs/decisions/0001-license.md")


def test_source_register_lists_eia_first_and_unreviewed():
    register = _read("docs/source-register.md")
    eia_row = next(line for line in register.splitlines() if line.startswith("| EIA"))
    assert "| 1 |" in eia_row and "Pending" in eia_row


def test_env_example_has_only_empty_or_placeholder_values():
    values = dict(
        line.split("=", 1)
        for line in _read(".env.example").splitlines()
        if line.strip() and not line.startswith("#")
    )
    assert values["EIA_API_KEY"] == ""
    for key, value in values.items():
        if any(word in key for word in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
            assert value == "", key


def test_learning_sequence_order():
    assert [s["key"] for s in learning_sequence()] == [
        "fundamentals",
        "regional-markets",
        "settlement",
        "financial-contracts-risk",
        "compliance",
        "integrated-analysis",
    ]
    assert all(s["title"] and s["description"] for s in learning_sequence())


def test_data_labels():
    assert [label["key"] for label in data_labels()] == [
        "observed",
        "derived",
        "modeled",
        "synthetic",
    ]
