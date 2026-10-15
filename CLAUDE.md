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
- Before every commit: `git diff --cached --name-only` and a secret scan of
  the staged diff (see `docs/github-workflow.md`).
- Never force-push, change repo visibility, merge PRs, or deploy without
  explicit owner approval.
- Adding a dependency or data source requires a license/terms check (see
  `docs/decisions/0001-license.md`). Private visibility is not a substitute.

## Workflow

- Branch from `main`; open a PR using the template. See `docs/github-workflow.md`.
- Record significant decisions as ADRs in `docs/decisions/` (copy
  `0000-template.md`).
- Update `docs/progress.md` and `docs/feature-matrix.md` when work lands.

- Feature status lives in `src/mambo_explorer/content/features.yaml`; keep
  `docs/feature-matrix.md` in sync (a test enforces it).
- Never show fabricated data. Every displayed value must carry an
  observed/derived/modeled/synthetic label (PRD R-15).

## Commands (Windows; venv at `.venv`)

```bash
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/streamlit run src/mambo_explorer/app.py
.venv/Scripts/ruff check .
.venv/Scripts/ruff format --check .
.venv/Scripts/pytest
```
