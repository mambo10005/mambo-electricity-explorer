# CLAUDE.md — mambo-electricity-explorer

Guidance for Claude Code (and other agents) working in this repo.

## Project

Python (>=3.11) application for exploring electricity data. Requirements live
in `docs/PRD.md`; structure in `docs/architecture.md`. Read both before
non-trivial work.

## Hard rules

- Never commit secrets, `.env` files, raw data, Parquet/Arrow files,
  databases, contracts, compliance evidence, logs, or generated reports.
  `.gitignore` covers these — don't weaken it without an ADR.
- Before every commit, run the quality check (below). It also inspects
  tracked/staged paths and scans for secrets. Then review
  `git diff --cached --name-only` yourself.
- Never force-push, change repo visibility, merge PRs, or deploy without
  explicit owner approval.
- Adding a dependency or data source requires a license/terms check (see
  `docs/decisions/0001-license.md`, `docs/source-register.md`). Private
  visibility is not a substitute.
- Never edit `uv.lock` by hand, and never let a check rewrite it. Dependency
  changes are a deliberate `uv lock` followed by
  `scripts/license_inventory.py` (ADR 0003).
- Don't touch the developer's `.venv`. Verification uses `.venvs/py311` and
  `.venvs/py314`.
- EIA credential: never print, log, or archive it.
  - Anything that could carry it goes through `eia/redact.py`.
  - Errors are re-raised `from None`.
  - Tests must never need it.
  - Never run `mambo collect` from app code.
- Data stays in `MAMBO_DATA_DIR` (default `./data`, gitignored). Never commit
  archives, Parquet, or SQLite files. EIA facts live only in
  `eia/dataset.py`, backed by the source-register review (ADR 0004).

## Workflow

- Branch from `main` (or stack on an unmerged stage branch); open a draft PR
  using the template. See `docs/github-workflow.md`.
- Record significant decisions as ADRs in `docs/decisions/` (copy
  `0000-template.md`).
- Update `docs/progress.md` and `docs/feature-matrix.md` when work lands.
- Feature status lives in `src/mambo_explorer/content/features.yaml`; keep
  `docs/feature-matrix.md` in sync (a test enforces it).
- Never show fabricated data. Every displayed value must carry an
  observed/derived/modeled/synthetic label (PRD R-15). Tests reject data
  elements (charts, maps, metrics) on any section whose features are not
  `done` (`tests/guards.py`). Don't weaken that guard to make a test pass.
- Lessons follow `docs/lesson-authoring.md`.
  - Never mark content `human-reviewed` unless a named person reviewed it.
  - Never hardcode current data in lesson text.
  - Numbers come from `calculations.py`, never from UI code.
- Tested Python versions (3.11, 3.14) are recorded separately from the
  declared `requires-python`; never change `requires-python` to hide a failure.

## Commands (Windows PowerShell; uv 0.12.x)

```powershell
pwsh -File scripts/setup-env.ps1 [-Python 3.11]   # one-time; downloads; uses uv.lock
pwsh -File scripts/check.ps1 [-Python 3.11]       # routine; offline; nonzero on failure
.venvs/py314/Scripts/streamlit run src/mambo_explorer/app.py
.venvs/py314/Scripts/python scripts/license_inventory.py   # after any uv lock
.venvs/py314/Scripts/mambo collect --dry-run               # never needs a key
.venvs/py314/Scripts/mambo validate                        # read-only store check
```
