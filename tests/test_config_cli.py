import os
import subprocess
from pathlib import Path

import pytest
from eia_fixtures import FAKE_KEY

from mambo_explorer import cli
from mambo_explorer.config import ConfigError, load_dotenv, load_settings, validate_data_dir

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("rel", ["src/data", "docs/x", "tests/x", ".", "scripts", "public/data"])
def test_unsafe_data_dirs_inside_repo_are_rejected(rel):
    with pytest.raises(ConfigError):
        validate_data_dir(REPO / rel, REPO)


def test_repo_ancestor_and_publication_dirs_are_rejected(tmp_path):
    with pytest.raises(ConfigError, match="contain the repository"):
        validate_data_dir(REPO.parent, REPO)
    with pytest.raises(ConfigError, match="publication"):
        validate_data_dir(tmp_path / "site" / "obs", REPO)


def test_safe_data_dirs_are_accepted(tmp_path, monkeypatch):
    # Validation only (nothing is read or written). The suite protects REPO/data, so lift
    # that protection for this one production-behavior check.
    monkeypatch.delenv("MAMBO_FORBIDDEN_DATA_DIRS", raising=False)
    assert validate_data_dir(REPO / "data", REPO) == (REPO / "data").resolve()
    assert validate_data_dir(tmp_path / "obs", REPO) == (tmp_path / "obs").resolve()


def test_data_dir_is_gitignored():
    result = subprocess.run(["git", "check-ignore", "-q", "data/x.parquet"], cwd=REPO)
    assert result.returncode == 0


def test_settings_never_expose_key(monkeypatch, tmp_path):
    monkeypatch.setenv("EIA_API_KEY", FAKE_KEY)
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path / "d"))  # never the real REPO/data
    settings = load_settings(REPO)
    assert settings.has_api_key and FAKE_KEY not in repr(settings)


def test_dotenv_loads_allowed_keys_without_overriding(tmp_path, monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    monkeypatch.setenv("MAMBO_DATA_DIR", "already-set")
    env = tmp_path / ".env"
    env.write_text(f"EIA_API_KEY={FAKE_KEY}\nMAMBO_DATA_DIR=other\nUNRELATED=1\n", "utf-8")
    assert load_dotenv(env, repo_root=None) == ["EIA_API_KEY"]
    assert os.environ["EIA_API_KEY"] == FAKE_KEY and os.environ["MAMBO_DATA_DIR"] == "already-set"
    assert "UNRELATED" not in os.environ


def test_dotenv_inside_repo_must_be_gitignored(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".env").write_text("EIA_API_KEY=x\n", "utf-8")
    with pytest.raises(ConfigError, match="not ignored by git"):
        load_dotenv(repo / ".env", repo)
    (repo / ".gitignore").write_text(".env\n", "utf-8")
    assert load_dotenv(repo / ".env", repo) in (["EIA_API_KEY"], [])


def test_cli_dry_run_needs_no_key_and_never_prints_it(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("EIA_API_KEY", FAKE_KEY)
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path / "d"))
    assert cli.main(["--no-dotenv", "collect", "--dry-run", "--days", "3"]) == 0
    out = capsys.readouterr()
    assert "request_budget" in out.out and "Dry run" in out.out
    assert FAKE_KEY not in out.out + out.err
    assert not (tmp_path / "d").exists()  # dry run writes nothing


def test_cli_collect_without_key_fails_cleanly(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path / "d"))
    assert cli.main(["--no-dotenv", "collect"]) == 2
    assert "EIA_API_KEY is not set" in capsys.readouterr().err


def test_cli_rejects_oversized_range(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path / "d"))
    assert cli.main(["--no-dotenv", "collect", "--dry-run", "--days", "40"]) == 2
    assert "per-run maximum" in capsys.readouterr().err


@pytest.mark.parametrize("command", [["status"], ["storage"], ["validate"], ["sources"]])
def test_cli_read_commands_work_offline_on_empty_store(command, monkeypatch, tmp_path):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path / "d"))
    assert cli.main(["--no-dotenv", *command]) == 0
