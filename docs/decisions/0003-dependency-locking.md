# 0003 — Dependency locking and local verification environments

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

Stage 1 declared version ranges but had no lock, so a fresh install could
resolve different versions. Python 3.11 compatibility was declared but
untested. The developer's existing `.venv` must not be replaced.

## Decision

- **uv** manages the lock. `uv.lock` is committed. It is a universal lock:
  one file resolves for all platforms and for Python >= 3.11, and covers
  runtime dependencies plus the `dev` dependency group.
- **uv version:** 0.12.5 was used to create the lock.
  `[tool.uv] required-version = ">=0.12.5,<0.13"` makes other uv versions
  refuse to run, rather than silently re-locking differently.
- **Dev tools move to a PEP 735 `[dependency-groups]` `dev` group.** It is
  locked, installed by default by `uv sync`, and never published as a package
  extra. `pip install -e ".[dev]"` no longer works.
- **Verification environments** live in `.venvs/py311` and `.venvs/py314`
  (gitignored), created with
  `UV_PROJECT_ENVIRONMENT=.venvs/pyXY uv sync --locked --python 3.XY`
  (wrapped by `scripts/setup-env.ps1`). `.venv` is left alone.
- **Checks never update the lock.**
  - Setup uses `--locked`: it fails if the lock is stale instead of
    rewriting it.
  - The quality gate runs `uv lock --check --offline` and
    `uv sync --locked --check --offline`. Both only report.
  - Changing dependencies is a deliberate `uv lock` (or `uv add`) commit.
- **Tested versus declared.** `requires-python = ">=3.11"` is declared. Tested:
  CPython 3.11.16 and 3.14.2 on Windows 11. 3.12, 3.13 and other OSes resolve
  in the lock but are **not tested**.

Commands were taken from the uv docs (docs.astral.sh/uv: "Locking and
syncing", "Project environment path", "Dependency groups").

## Alternatives considered

- **pip-tools (`pip-compile`):** produces per-platform, per-Python lock files
  and handles dependency groups less directly. It would need a separate lock
  for 3.11 vs 3.14 because of the numpy fork.
- **Hashed `requirements.txt` exported from uv:** a possible addition if pip
  installs are ever needed. Not needed now.

## Consequences

- Contributors need uv 0.12.x.
- The lock forks numpy by Python version: 2.4.6 on 3.11, 2.5.4 on >= 3.12.
  Both forks are installed and tested, one per environment.
- `docs/dependency-licenses.md` is generated from the lock, and a test fails
  if the two drift apart.
