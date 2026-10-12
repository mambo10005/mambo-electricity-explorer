"""Regression for the Stage 9 finding: undoing a test's MAMBO_DATA_DIR override must never
fall back to the developer's real ./data directory (see tests/conftest.py)."""

from conftest import REAL_DATA

from mambo_explorer.config import load_settings


def test_undoing_an_override_falls_back_to_the_session_temp_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path / "mine"))
    assert load_settings().data_dir.resolve() == (tmp_path / "mine").resolve()
    monkeypatch.undo()
    fallback = load_settings().data_dir.resolve()
    assert fallback != REAL_DATA.resolve()
    assert "session-data" in fallback.name
