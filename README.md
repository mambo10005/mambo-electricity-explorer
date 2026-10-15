# mambo-electricity-explorer

A local-first, novice-oriented platform for learning and analyzing the U.S.
electricity system from actual observations and reproducible modeling. See
[docs/PRD.md](docs/PRD.md).

**Status:** Stage 1, the application shell. Navigation and documentation
exist. Data collection, modeling, and the finance and compliance features
are **not implemented**. The app shows no data. Feature-by-feature status:
[docs/feature-matrix.md](docs/feature-matrix.md).

## Install

Requires Python 3.11+ (verified on 3.14.2 only). Commands below are for
Windows (Git Bash or PowerShell); on macOS/Linux use `.venv/bin/` instead
of `.venv/Scripts/`.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env           # optional in Stage 1; never commit .env
```

## Launch

```bash
.venv/Scripts/streamlit run src/mambo_explorer/app.py
```

Then open http://localhost:8501.

## Test

```bash
.venv/Scripts/ruff check .
.venv/Scripts/ruff format --check .
.venv/Scripts/pytest
```

The tests are offline. They include Streamlit `AppTest` renders of every page.

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
| [Progress](docs/progress.md) | Running log of work |
| [GitHub workflow](docs/github-workflow.md) | Branching, PRs, reviews |
| [Decisions](docs/decisions/) | Architecture Decision Records |

## License

No license has been chosen. Until one is, all rights are reserved by the
owner. See [docs/decisions/0001-license.md](docs/decisions/0001-license.md).
