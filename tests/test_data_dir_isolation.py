"""Data-isolation regressions (Stage 9 finding, Stage 10 hardening).

Every check here uses a *fake* protected data directory inside a temp folder, holding a
sentinel file. The developer's real ./data is never written to prove anything; the session
fixture in conftest.py separately asserts it is unchanged.
"""

import ctypes
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import REAL_DATA
from streamlit.testing.v1 import AppTest

from mambo_explorer.config import FORBIDDEN_ENV, ConfigError, load_settings, same_or_inside

WINDOWS = os.name == "nt"


@pytest.fixture
def protected(tmp_path, monkeypatch):
    """A fake repository whose data/ is protected and holds a sentinel."""
    repo = tmp_path / "Fake Repo With Long Name"
    (repo / ".git").mkdir(parents=True)
    data = repo / "data"
    (data / "learn").mkdir(parents=True)
    sentinel = data / "learn" / "progress.json"
    sentinel.write_text('{"sentinel": true}', "utf-8")
    monkeypatch.setenv(FORBIDDEN_ENV, str(data))
    before = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns, sorted(data.rglob("*")))
    yield repo, data
    after = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns, sorted(data.rglob("*")))
    assert after == before, "the protected sentinel directory changed"


def _refused(data_dir: str, cwd: Path, monkeypatch) -> bool:
    monkeypatch.setenv("MAMBO_DATA_DIR", data_dir)
    try:
        load_settings(cwd)
    except ConfigError as exc:
        return "protected location" in str(exc)
    return False


def test_session_runs_with_scratch_dirs_and_the_real_data_forbidden():
    assert os.environ[FORBIDDEN_ENV] == str(REAL_DATA)
    data_dir = load_settings().data_dir
    assert not same_or_inside(data_dir, REAL_DATA)
    assert "session-data" in data_dir.name
    assert not same_or_inside(Path.cwd(), REAL_DATA.parent)  # cwd is scratch, not the repo


def test_undoing_an_override_falls_back_to_the_session_temp_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path / "mine"))
    assert load_settings().data_dir.resolve() == (tmp_path / "mine").resolve()
    monkeypatch.undo()
    fallback = load_settings().data_dir.resolve()
    assert not same_or_inside(fallback, REAL_DATA)
    assert "session-data" in fallback.name


def test_missing_configuration_falls_back_to_cwd_data_which_is_refused(protected, monkeypatch):
    repo, _ = protected
    monkeypatch.delenv("MAMBO_DATA_DIR", raising=False)
    with pytest.raises(ConfigError, match="protected location"):
        load_settings(repo)  # default ./data under that cwd is the protected one


def test_relative_paths_and_alternate_working_directories_are_refused(protected, monkeypatch):
    repo, data = protected
    sub = repo / "nested" / "deeper"
    sub.mkdir(parents=True)
    assert _refused("data", repo, monkeypatch)
    assert _refused("./data/../data", repo, monkeypatch)
    assert _refused("../../data", sub, monkeypatch)
    assert _refused(str(data / "learn"), repo, monkeypatch)  # inside it counts too
    assert not _refused(str(repo / "data-scratch"), repo, monkeypatch)  # a prefix is not inside


@pytest.mark.skipif(not WINDOWS, reason="case-insensitive paths are a Windows property")
def test_other_casing_is_refused(protected, monkeypatch):
    repo, data = protected
    assert _refused(str(data).upper(), repo, monkeypatch)
    assert _refused(str(data).swapcase(), repo, monkeypatch)


@pytest.mark.skipif(not WINDOWS, reason="case-insensitive paths are a Windows property")
def test_casing_is_refused_even_before_the_protected_dir_exists(tmp_path, monkeypatch):
    """resolve() and samefile() cannot canonicalize a path that does not exist yet (a fresh
    checkout has no data/ until first use), so only case-normalized comparison catches this."""
    repo = tmp_path / "Fresh Repo"
    (repo / ".git").mkdir(parents=True)
    data = repo / "data"  # deliberately not created
    monkeypatch.setenv(FORBIDDEN_ENV, str(data))
    assert _refused(str(data).upper(), repo, monkeypatch)
    assert _refused(str(data).swapcase() + "\\learn", repo, monkeypatch)
    assert not data.exists()


@pytest.mark.skipif(not WINDOWS, reason="8.3 short names are a Windows alias")
def test_short_name_alias_is_refused(protected, monkeypatch):
    repo, data = protected
    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(data), buf, 1024)
    short = buf.value
    if not short or short.lower() == str(data).lower():
        pytest.skip("8.3 short names are disabled on this volume")
    assert _refused(short, repo, monkeypatch)
    assert same_or_inside(Path(short), data)  # the guard itself, without config's resolve()


@pytest.mark.skipif(not WINDOWS, reason="junctions are a Windows feature")
def test_junction_to_the_protected_dir_is_refused(protected, monkeypatch, tmp_path):
    import _winapi

    repo, data = protected
    link = tmp_path / "junction-to-data"
    _winapi.CreateJunction(str(data), str(link))
    try:
        assert _refused(str(link), repo, monkeypatch)
        assert _refused(str(link / "learn"), repo, monkeypatch)
        assert same_or_inside(link / "learn", data)  # the guard itself, without config's resolve()
    finally:
        os.rmdir(link)  # removes the junction only, never its target


def test_symlink_to_the_protected_dir_is_refused(protected, monkeypatch, tmp_path):
    repo, data = protected
    link = tmp_path / "symlink-to-data"
    try:
        os.symlink(data, link, target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks needs Developer Mode or admin rights here")
    try:
        assert _refused(str(link), repo, monkeypatch)
    finally:
        link.unlink()


def _child(cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    code = "from mambo_explorer.config import load_settings; print(load_settings().data_dir)"
    return subprocess.run(
        [sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True
    )


def test_subprocesses_inherit_the_protection(protected):
    repo, _ = protected
    env = {**os.environ}
    env.pop("MAMBO_DATA_DIR", None)  # a child that lost its data-dir setting
    result = _child(repo, env)
    assert result.returncode != 0 and "protected location" in result.stderr
    scratch = repo.parent / "child-scratch"
    ok = _child(repo, {**env, "MAMBO_DATA_DIR": str(scratch)})
    assert ok.returncode == 0 and Path(ok.stdout.strip()) == scratch.resolve()


def test_app_pages_refuse_the_protected_dir_and_write_nothing(protected, monkeypatch):
    _, data = protected
    monkeypatch.setenv("MAMBO_DATA_DIR", str(data))
    for page in ("learn", "model-labs"):
        at = AppTest.from_string(
            f"from mambo_explorer.pages import render_page\nrender_page({page!r})\n"
        ).run(timeout=30)
        assert not at.exception
        assert any("Unsafe data directory configuration" in e.value for e in at.error), page


def test_gate_subprocess_environment_is_scratch():
    sys.path.insert(0, str(REAL_DATA.parent / "scripts"))
    try:
        import quality
    finally:
        sys.path.pop(0)
    env = quality.scratch_env("probe")
    assert env["MAMBO_FORBIDDEN_DATA_DIRS"] == str(REAL_DATA)
    assert not same_or_inside(Path(env["MAMBO_DATA_DIR"]), REAL_DATA)
    assert not same_or_inside(Path(env["MAMBO_DATA_DIR"]), REAL_DATA.parent)
