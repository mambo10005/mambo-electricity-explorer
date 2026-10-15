# mambo-electricity-explorer

A local-first, novice-oriented platform for learning and analyzing the U.S.
electricity system from actual observations and reproducible modeling. See
[docs/PRD.md](docs/PRD.md).

**Status:** Stage 2, the application shell plus a reproducible local quality workflow. Navigation and documentation
exist. Data collection, modeling, and the finance and compliance features
are **not implemented**. The app shows no data. Feature-by-feature status:
[docs/feature-matrix.md](docs/feature-matrix.md).

## Requirements

- [uv](https://docs.astral.sh/uv/) **0.12.x** (enforced by `[tool.uv] required-version`).
- Python: declared `>=3.11`. **Tested:** CPython 3.11.16 and 3.14.2 on
  Windows 11. Other versions and operating systems are untested.
  `uv` installs a missing Python with `uv python install 3.11`.

Commands are for Windows PowerShell. Dependencies are pinned in `uv.lock`
(ADR 0003).

## 1. Set up (one time; downloads packages)

Creates an isolated environment from the lock. It refuses to run, instead of
rewriting the lock, if `uv.lock` is out of date. Any `.venv` you already have
is not touched.

```powershell
pwsh -File scripts/setup-env.ps1                # .venvs/py314
pwsh -File scripts/setup-env.ps1 -Python 3.11   # .venvs/py311
```

## 2. Routine quality check (offline)

```powershell
pwsh -File scripts/check.ps1                    # Python 3.14
pwsh -File scripts/check.ps1 -Python 3.11       # Python 3.11
```

It runs config/content validation, the lock consistency check, Ruff lint
and format check, offline pytest, an import and app startup smoke test,
the tracked-file check, and the secret scan.

- Exits nonzero if anything fails.
- Never edits files, updates `uv.lock`, or downloads anything.
- Stops the temporary Streamlit server it starts.
- Reports secret findings as file:line only, never the matched text.

## 3. Launch

```powershell
.venvs/py314/Scripts/streamlit run src/mambo_explorer/app.py
```

Then open http://localhost:8501. Copying `.env.example` to `.env` is optional
for now, because nothing reads it yet.

## Changing dependencies

Edit `pyproject.toml`, run `uv lock`, re-run setup, then regenerate the
license inventory with `.venvs/py314/Scripts/python scripts/license_inventory.py`.
A test fails if `docs/dependency-licenses.md` no longer matches the lock.

## Repository rules

- **No data in Git.** Raw data, Parquet archives, and databases live under the
  gitignored `data/` directory or outside the repo.
- **No secrets in Git.** Configuration comes from `.env` (gitignored); only
  `.env.example` with placeholders is committed.
- **No private documents.** Contracts and compliance evidence are stored
  elsewhere.
- **Every data source is reviewed first.** See
  [docs/source-register.md](docs/source-register.md).

## Docs

| Doc | Purpose |
|-----|---------|
| [PRD](docs/PRD.md) | Confirmed requirements, proposals, open decisions |
| [Architecture](docs/architecture.md) | How it's structured |
| [Feature matrix](docs/feature-matrix.md) | Feature status at a glance |
| [Source register](docs/source-register.md) | Data source access and licensing review |
| [Dependency licenses](docs/dependency-licenses.md) | Generated license inventory of locked packages |
| [Progress](docs/progress.md) | Running log of work |
| [GitHub workflow](docs/github-workflow.md) | Branching, PRs, reviews |
| [Decisions](docs/decisions/) | Architecture Decision Records |

## License

No license has been chosen. Until one is, all rights are reserved by the
owner. See [docs/decisions/0001-license.md](docs/decisions/0001-license.md).
