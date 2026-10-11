# mambo-electricity-explorer

A Python application for exploring electricity data. Scope, users, and data
sources are still being defined — see [docs/PRD.md](docs/PRD.md).

**Status:** project scaffold only. No application code yet.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install pytest ruff        # dev tools; runtime deps TBD
cp .env.example .env           # fill in locally; never commit .env
```

## Repository rules

- **No data in Git.** Raw data, Parquet archives, and databases live under the
  gitignored `data/` directory or outside the repo.
- **No secrets in Git.** Configuration comes from `.env` (gitignored); only
  `.env.example` with placeholders is committed.
- **No private documents.** Contracts and compliance evidence are stored
  elsewhere.

## Docs

| Doc | Purpose |
|-----|---------|
| [PRD](docs/PRD.md) | What we're building and why |
| [Architecture](docs/architecture.md) | How it's structured |
| [Feature matrix](docs/feature-matrix.md) | Feature status at a glance |
| [Progress](docs/progress.md) | Running log of work |
| [GitHub workflow](docs/github-workflow.md) | Branching, PRs, reviews |
| [Decisions](docs/decisions/) | Architecture Decision Records |

## License

No license has been chosen. Until one is, all rights are reserved by the
owner. See [docs/decisions/0001-license.md](docs/decisions/0001-license.md).
