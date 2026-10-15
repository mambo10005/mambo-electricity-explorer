import copy
import re
from pathlib import Path

from mambo_explorer.catalog import FEATURE_STATUSES, features
from mambo_explorer.navigation import SECTIONS

REPO = Path(__file__).resolve().parents[1]
DONE_FEATURES = {
    "DOCS-01",
    "SHELL-01",
    "SHELL-02",
    "QA-01",
    "QA-02",
    "QA-03",
    "QA-04",
    "QA-05",
    "DATA-01",
    "DATA-04",
    "MODEL-02",
    "MODEL-03",
    "EXPLORE-03",
    "LEARN-03",
    "LEARN-04",
    "FIN-03",
    "CALC-01",
    "STORE-01",
    "STORE-02",
    "EXPLORE-02",
}


def _matrix_rows(text: str) -> dict[str, tuple[str, str]]:
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and re.fullmatch(r"[A-Z]+-\d{2}", cells[0]):
            rows[cells[0]] = (cells[2], cells[3])
    return rows


def matrix_drift(matrix_text: str, feature_list: list[dict]) -> list[str]:
    """Differences between docs/feature-matrix.md and features.yaml (empty = in sync)."""
    doc = _matrix_rows(matrix_text)
    yml = {f["id"]: (f["section"], f["status"]) for f in feature_list}
    return sorted(
        f"{fid}: doc={doc.get(fid)} yaml={yml.get(fid)}"
        for fid in doc.keys() | yml.keys()
        if doc.get(fid) != yml.get(fid)
    )


def _matrix_text() -> str:
    return (REPO / "docs/feature-matrix.md").read_text("utf-8")


def test_feature_ids_unique_and_fields_valid():
    ids = [f["id"] for f in features()]
    assert len(set(ids)) == len(ids)
    valid_sections = {s.key for s in SECTIONS} | {"platform"}
    for f in features():
        assert f["status"] in FEATURE_STATUSES, f
        assert f["section"] in valid_sections, f
        assert f["name"].strip(), f
        assert f.get("ui", False) in (True, False), f


def test_every_navigation_section_tracks_at_least_one_feature():
    tracked = {f["section"] for f in features()}
    for s in SECTIONS:
        assert s.key in tracked, s.key


def test_only_expected_features_are_marked_done():
    done = {f["id"] for f in features() if f["status"] == "done"}
    assert done == DONE_FEATURES


def test_feature_matrix_doc_matches_features_yaml():
    assert matrix_drift(_matrix_text(), features()) == []


def test_status_drift_is_detected():
    drifted = copy.deepcopy(features())
    drifted[-1]["status"] = "done"
    assert matrix_drift(_matrix_text(), drifted) == [
        f"{drifted[-1]['id']}: doc=('{drifted[-1]['section']}', 'planned') "
        f"yaml=('{drifted[-1]['section']}', 'done')"
    ]


def test_missing_feature_row_is_detected():
    text = "\n".join(line for line in _matrix_text().splitlines() if "| PUB-01 |" not in line)
    assert matrix_drift(text, features()) == ["PUB-01: doc=None yaml=('platform', 'planned')"]
