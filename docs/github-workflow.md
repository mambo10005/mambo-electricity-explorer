# GitHub Workflow

## Repository

- `mambo10005/mambo-electricity-explorer`, **private**. Changing visibility
  requires an explicit owner decision recorded as an ADR.
- Default branch: `main`.

## Branching

- Branch from `main`: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
- **Stacked stages:** if the previous stage's PR is unmerged, branch from its head and
  target that branch with a draft PR whose description names the dependency. Retarget
  to `main` after the lower PR merges.
- Keep branches short-lived; one concern per PR.

## Commits

- Imperative subject line, <= 72 chars (e.g. "Add ingestion for X").
- Before committing, stage the change, run the quality gate (it checks
  tracked *and staged* paths and scans them for secrets without printing
  matches), then review the staged list yourself:

  ```powershell
  pwsh -File scripts/check.ps1
  pwsh -File scripts/check.ps1 -Python 3.11
  git diff --cached --name-only
  ```

## Pull requests

- Use the PR template. Link the issue and update `docs/progress.md`.
- No hosted CI yet. Run `scripts/check.ps1` on Python 3.11 and 3.14 and paste
  the summary into the PR.
- Merging is done by the owner. Never force-push to `main`.

## Issues

- Use the bug or feature template under `.github/ISSUE_TEMPLATE/`.

## Never committed

Secrets, `.env`, raw data, Parquet archives, databases, contracts,
compliance evidence, logs, generated reports, local permission settings
(`.claude/settings.local.json`), local tool state (`.cw/`).
