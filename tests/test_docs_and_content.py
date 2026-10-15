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
    "docs/decisions/0003-dependency-locking.md",
    "docs/decisions/0004-eia-collection-and-storage.md",
    "docs/dependency-licenses.md",
    "docs/calculations.md",
    "docs/lesson-authoring.md",
    "docs/datasets/ercot-np6-345-cd.md",
    "docs/decisions/0005-ercot-direct-connector.md",
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


def _register_row(prefix: str) -> list[str]:
    register = _read("docs/source-register.md")
    line = next(line for line in register.splitlines() if line.startswith(f"| {prefix}"))
    return [c.strip() for c in line.strip().strip("|").split("|")]


def test_source_register_order_and_local_only_connections():
    eia, ercot = _register_row("EIA"), _register_row("ERCOT")
    assert eia[2] == "1" and ercot[2].startswith("2")
    assert eia[-1].startswith("Yes, locally") and ercot[-1].startswith("Yes, locally")
    # Local use is recorded separately from publication, which stays pending for both.
    assert "publication review pending" in eia[7] and "publication review pending" in ercot[7]


def test_ercot_review_separates_local_use_from_publication():
    register = _read("docs/source-register.md")
    assert "### ERCOT NP6-345-CD Actual System Load by Weather Zone" in register
    assert "**Local collection and use: CLEARED**" in register
    assert "**Public redistribution: NOT REVIEWED FOR THIS PROJECT.**" in register
    assert "No account was created and no terms were accepted" in register
    assert "never compared numerically" in register


def test_eia_review_recorded_without_blanket_unrestricted_claim():
    register = _read("docs/source-register.md")
    assert "### EIA Open Data API — 2026-10-11" in register
    for topic in ("Attribution", "No implied endorsement", "Access restrictions", "Protected"):
        assert topic in register, topic
    status = _register_row("EIA")[7]
    assert "cleared for local collection/use" in status and "publication review pending" in status
    assert "unrestricted" not in register.lower().replace("not everything is unrestricted", "")


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


def test_eia930_review_separates_collection_clearance_from_publication():
    register = _read("docs/source-register.md")
    assert "### EIA-930 hourly demand and forecast" in register
    assert "**Local collection and use: CLEARED**" in register
    assert "**Public redistribution: NOT YET REVIEWED.**" in register
    assert "Hour-ending is not stated for the API `period` field" in register
