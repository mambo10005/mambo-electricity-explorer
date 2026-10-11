"""Local quality gate. Normally run through scripts/check.ps1.

Runs every check even after a failure, prints a summary, and exits nonzero if any
check failed. It never edits files, never updates uv.lock, never downloads, and
stops the temporary Streamlit server it starts. Secret findings report the file,
line, and pattern name only, never the matched text.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from collections.abc import Callable
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable

FORBIDDEN_PATHS = {
    "env file": r"(^|/)\.env(\.(?!example$)[^/]*)?$",
    "local tool state": r"(^|/)\.cw/",
    "virtual environment": r"(^|/)\.venvs?/",
    "stack dump": r"\.stackdump$",
    "database": r"\.(db|db-shm|db-wal|sqlite3?|duckdb)$",
    "data archive": r"\.(parquet|pq|arrow|feather|csv\.gz|zip)$",
    "data directory": r"^(data|raw)/",
    "private document": r"^(contracts|compliance|evidence|private)/",
    "log or report": r"(\.log$|^logs/|^reports/|^output/|^out/)",
    "local settings": r"(^|/)settings\.local\.json$",
    "key material": r"\.(pem|key|p12|pfx)$",
    "build or cache output": r"(__pycache__/|\.egg-info/|^build/|^dist/|_cache/)",
}

SECRET_PATTERNS = {
    "GitHub token": r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "Slack token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    "OpenAI/Anthropic-style key": r"\bsk-(ant-)?[A-Za-z0-9_-]{20,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "credential assignment": (
        r"(?i)\b[A-Z0-9_]*(api_?key|secret|token|password)[A-Z0-9_]*\s*[:=]\s*"
        r"['\"]?[A-Za-z0-9/+_\-]{16,}"
    ),
}


def _run(args: list[str], env: dict[str, str] | None = None) -> bool:
    print("  $", " ".join(args), flush=True)
    return subprocess.run(args, cwd=REPO, env=env).returncode == 0


def check_config() -> bool:
    ok = True
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))
    project = pyproject["project"]
    if "Private :: Do Not Upload" not in project.get("classifiers", []):
        print("  private-publication classifier missing")
        ok = False
    if "license" in project:
        print("  license set in pyproject.toml, but ADR 0001 keeps it pending")
        ok = False
    yaml_files = [*REPO.glob("src/**/*.yaml"), *REPO.glob(".github/**/*.yml")]
    for path in yaml_files:
        try:
            yaml.safe_load(path.read_text("utf-8"))
        except yaml.YAMLError as exc:
            print(f"  invalid YAML: {path.relative_to(REPO)}: {exc}")
            ok = False
    print(f"  pyproject.toml parsed; {len(yaml_files)} YAML files parsed")
    return ok


def check_lock() -> bool:
    # Uses the interpreter's own environment as the project environment so the check
    # inspects exactly the environment that runs the remaining checks.
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": sys.prefix}
    return _run(["uv", "lock", "--check", "--offline"], env) and _run(
        ["uv", "sync", "--locked", "--check", "--offline", "--python", PY], env
    )


def check_ruff_lint() -> bool:
    return _run([PY, "-m", "ruff", "check", "--no-fix", "."])


def check_ruff_format() -> bool:
    return _run([PY, "-m", "ruff", "format", "--check", "."])


def check_pytest() -> bool:
    return _run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"])


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def check_smoke() -> bool:
    if not _run([PY, "-c", "import mambo_explorer, mambo_explorer.pages; print('  import ok')"]):
        return False
    port = _free_port()
    args = [
        PY, "-m", "streamlit", "run", "src/mambo_explorer/app.py",
        "--server.headless", "true",
        "--server.address", "127.0.0.1",
        "--server.port", str(port),
        "--browser.gatherUsageStats", "false",
    ]  # fmt: skip
    print("  $", " ".join(args), flush=True)
    server = subprocess.Popen(
        args, cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(120):
            if server.poll() is not None:
                print(f"  server exited early: {server.stderr.read()[-2000:]}")
                return False
            try:
                with urllib.request.urlopen(f"{base}/_stcore/health", timeout=2) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.5)
        else:
            print("  server did not become healthy within 60 s")
            return False
        with urllib.request.urlopen(base + "/", timeout=5) as resp:
            print(f"  health 200, GET / {resp.status}")
            return resp.status == 200
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        print(f"  server stopped (pid {server.pid})")


def _candidate_files() -> list[str]:
    def git(*args: str) -> list[str]:
        out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True)
        return [line for line in out.stdout.splitlines() if line]

    tracked = git("ls-files")
    staged = git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    # Untracked but not ignored: what `git add -A` would pick up next.
    untracked = git("ls-files", "--others", "--exclude-standard")
    return sorted(set(tracked) | set(staged) | set(untracked))


def check_tracked_files() -> bool:
    ok = True
    files = _candidate_files()
    for path in files:
        for label, pattern in FORBIDDEN_PATHS.items():
            if re.search(pattern, path):
                print(f"  forbidden ({label}): {path}")
                ok = False
    print(f"  {len(files)} tracked/staged/untracked paths checked")
    return ok


def check_secrets() -> bool:
    ok = True
    compiled = {name: re.compile(p) for name, p in SECRET_PATTERNS.items()}
    for rel in _candidate_files():
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text("utf-8")
        except UnicodeDecodeError:
            print(f"  binary file not scanned: {rel}")
            ok = False
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for name, regex in compiled.items():
                if regex.search(line):
                    print(f"  possible secret ({name}): {rel}:{number}")
                    ok = False
    print("  secret scan finished (matches are never printed)")
    return ok


CHECKS: list[tuple[str, Callable[[], bool]]] = [
    ("config and content validation", check_config),
    ("lock consistency (uv, offline)", check_lock),
    ("ruff lint", check_ruff_lint),
    ("ruff format check", check_ruff_format),
    ("pytest (offline)", check_pytest),
    ("package and app smoke", check_smoke),
    ("tracked/staged/untracked path check", check_tracked_files),
    ("secret scan", check_secrets),
]


def main() -> int:
    print(f"Python {sys.version.split()[0]} at {sys.prefix}")
    results = []
    for name, check in CHECKS:
        print(f"\n== {name}", flush=True)
        try:
            passed = check()
        except Exception as exc:  # report and continue so every check runs
            print(f"  error: {type(exc).__name__}: {exc}")
            passed = False
        results.append((name, passed))
    print("\n== summary")
    for name, passed in results:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    failed = sum(not passed for _, passed in results)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
