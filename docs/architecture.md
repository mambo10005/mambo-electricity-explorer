# Architecture — mambo-electricity-explorer

**Status:** Draft. Will be filled in as the PRD firms up.

## Constraints already fixed

- **Language:** Python >= 3.11, packaged via `pyproject.toml`.
- **Data stays out of Git.** Ingested and derived data live under `data/`
  (gitignored) or an external path set by `DATA_DIR`.
- **Config via environment.** Secrets and paths come from `.env`
  (gitignored); `.env.example` documents the variables.

## Intended layout (provisional)

```
src/mambo_electricity_explorer/   # application package (not yet created)
tests/                            # pytest suite (not yet created)
docs/                             # PRD, architecture, ADRs, progress
data/                             # local only, gitignored
```

## Components

_TBD — ingestion, storage, analysis, presentation. Record choices as ADRs._
