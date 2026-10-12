"""`mambo learn-reset`: dry run by default, typed confirmation, verified backup, no overwrite.

Every test uses temp directories with a sentinel progress file; nothing touches ./data.
"""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mambo_explorer import cli
from mambo_explorer import progress_reset as pr

NOW = datetime(2026, 10, 11, 20, 0, 0, tzinfo=UTC)
CONTENT = b'{"lessons": {"private-sentinel": {}}, "version": 1}'


@pytest.fixture
def setup(tmp_path):
    data = tmp_path / "data"
    (data / "learn").mkdir(parents=True)
    progress = data / "learn" / "progress.json"
    progress.write_bytes(CONTENT)
    backups = tmp_path / "backups"
    return data, progress, backups


def test_dry_run_lists_paths_without_contents_and_changes_nothing(setup, monkeypatch, capsys):
    data, progress, backups = setup
    monkeypatch.setenv("MAMBO_DATA_DIR", str(data))
    assert cli.main(["--no-dotenv", "learn-reset", "--backup-dir", str(backups)]) == 0
    out = capsys.readouterr().out
    assert str(progress) in out and str(backups) in out and "Dry run" in out
    assert "private-sentinel" not in out  # contents are never shown
    assert progress.read_bytes() == CONTENT and not backups.exists()


def test_execute_requires_the_typed_confirmation(setup):
    data, progress, backups = setup
    p = pr.plan(data, backups, now=NOW)
    with pytest.raises(pr.ResetError, match="not confirmed"):
        pr.execute(p, lambda _prompt: "yes")
    assert progress.read_bytes() == CONTENT and not p.backup.exists()


def test_execute_backs_up_verifies_then_resets_and_explains_restore(setup):
    data, progress, backups = setup
    p = pr.plan(data, backups, now=NOW)
    lines = pr.execute(p, lambda _prompt: "RESET")
    assert p.backup == backups.resolve() / "progress-20261011T200000Z.json"
    assert p.backup.read_bytes() == CONTENT  # exact copy
    assert not progress.exists()  # reset
    text = "\n".join(lines)
    assert "verified" in text and "Copy-Item -LiteralPath" in text and str(p.backup) in text
    assert "private-sentinel" not in text


def test_existing_backup_is_never_overwritten(setup):
    data, progress, backups = setup
    p = pr.plan(data, backups, now=NOW)
    backups.mkdir()
    p.backup.write_bytes(b"older backup")
    with pytest.raises(pr.ResetError, match="already exists"):
        pr.execute(p, lambda _prompt: "RESET")
    assert p.backup.read_bytes() == b"older backup" and progress.read_bytes() == CONTENT


def test_a_corrupt_backup_stops_before_the_reset(setup, monkeypatch):
    data, progress, backups = setup
    p = pr.plan(data, backups, now=NOW)
    real = pr._sha256
    monkeypatch.setattr(pr, "_sha256", lambda path: "0" * 64 if path == p.backup else real(path))
    with pytest.raises(pr.ResetError, match="does not match"):
        pr.execute(p, lambda _prompt: "RESET")
    assert progress.read_bytes() == CONTENT  # original untouched


def test_backup_inside_a_repository_is_refused_unless_ignored(setup, tmp_path):
    data, _, _ = setup
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    with pytest.raises(pr.ResetError, match="inside the Git repository"):
        pr.plan(data, repo / "backups", now=NOW)
    (repo / ".gitignore").write_text("backups/\n", "utf-8")
    assert pr.plan(data, repo / "backups", now=NOW).backup.parent == (repo / "backups").resolve()


def test_a_stray_git_folder_is_not_a_repository(setup, tmp_path):
    data, _, _ = setup
    fake = tmp_path / "home"
    (fake / ".git").mkdir(parents=True)  # like a broken .git in a home directory
    assert pr.tracking_repo(fake / "backups" / "x.json") is None
    assert pr.plan(data, fake / "backups", now=NOW).backup.parent == (fake / "backups").resolve()


def test_default_backup_dir_is_outside_this_repository():
    repo = Path(__file__).resolve().parents[1]
    assert not pr.default_backup_dir().resolve().is_relative_to(repo)
    assert pr.tracking_repo(pr.default_backup_dir() / "x.json") is None


def test_nothing_to_do_without_a_progress_file(tmp_path):
    p = pr.plan(tmp_path / "data", tmp_path / "backups", now=NOW)
    assert not p.exists
    assert pr.execute(p, lambda _prompt: pytest.fail("must not ask")) == pr.describe(p)
