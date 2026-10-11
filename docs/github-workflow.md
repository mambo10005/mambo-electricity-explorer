# GitHub Workflow

## Repository

- `mambo10005/mambo-electricity-explorer`, **private**. Changing visibility
  requires an explicit owner decision recorded as an ADR.
- Default branch: `main`.

## Branching

- Branch from `main`: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
- Keep branches short-lived; one concern per PR.

## Commits

- Imperative subject line, <= 72 chars (e.g. "Add ingestion for X").
- Before committing, inspect what's staged and scan for secrets:

  ```bash
  git diff --cached --name-only
  git diff --cached | grep -nEi "(api[_-]?key|secret|token|password)[\"' ]*[:=]|BEGIN .*PRIVATE KEY" || echo clean
  ```

## Pull requests

- Use the PR template. Link the issue and update `docs/progress.md`.
- CI is not configured yet; until it is, run `ruff check .` and `pytest`
  locally and paste the result in the PR.
- Merging is done by the owner. Never force-push to `main`.

## Issues

- Use the bug or feature template under `.github/ISSUE_TEMPLATE/`.

## Never committed

Secrets, `.env`, raw data, Parquet archives, databases, contracts,
compliance evidence, logs, generated reports, local permission settings
(`.claude/settings.local.json`), local tool state (`.cw/`).
