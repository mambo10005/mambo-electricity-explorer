import re
from pathlib import Path

from mambo_explorer.catalog import FEATURE_STATUSES, features
from mambo_explorer.navigation import SECTIONS

REPO = Path(__file__).resolve().parents[1]
SHELL_FEATURES = {"DOCS-01", "SHELL-01", "SHELL-02"}


def _matrix_rows() -> dict[str, tuple[str, str]]:
    rows = {}
    for line in (REPO / "docs/feature-matrix.md").read_text("utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and re.fullmatch(r"[A-Z]+-\d{2}", cells[0]):
            rows[cells[0]] = (cells[2], cells[3])
    return rows


def test_feature_ids_unique_and_fields_valid():
    ids = [f["id"] for f in features()]
    assert len(set(ids)) == len(ids)
    valid_sections = {s.key for s in SECTIONS} | {"platform"}
    for f in features():
        assert f["status"] in FEATURE_STATUSES, f
        assert f["section"] in valid_sections, f
        assert f["name"].strip(), f


def test_every_navigation_section_tracks_at_least_one_feature():
    tracked = {f["section"] for f in features()}
    for s in SECTIONS:
        assert s.key in tracked, s.key


def test_only_shell_features_are_marked_done():
    done = {f["id"] for f in features() if f["status"] == "done"}
    assert done == SHELL_FEATURES


def test_feature_matrix_doc_matches_features_yaml():
    expected = {f["id"]: (f["section"], f["status"]) for f in features()}
    assert _matrix_rows() == expected
