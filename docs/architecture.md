# Architecture — mambo-electricity-explorer

**Status:** Stage 1. Only the application shell exists. Everything under
"Planned components" is unimplemented.

## Fixed constraints

- Local-first. No paid runtime services or AI (PRD R-16, R-17, R-19).
- Python >= 3.11, Streamlit UI, DuckDB + Parquet observations, SQLite
  metadata, Markdown/YAML content (R-20 to R-22). Versions:
  [ADR 0002](decisions/0002-application-stack.md).
- Data stays out of Git. Data lives under `DATA_DIR` (default `./data`,
  gitignored).
- Config comes from environment variables. `.env` is gitignored, and
  `.env.example` documents the variables.

## Implemented (Stage 1)

```
src/mambo_explorer/
  __init__.py           version
  app.py                Streamlit entrypoint: st.navigation over Home + 8 sections
  navigation.py         Section definitions (pure data, no Streamlit import)
  pages.py              Home renderer and generic "Not implemented" section renderer
  catalog.py            Loads packaged YAML content
  content/
    features.yaml           Feature status (single source of truth, PRD P-6)
    learning-sequence.yaml  The six learning stages
    data-labels.yaml        Observed / derived / modeled / synthetic definitions
tests/                  Offline pytest suite, including Streamlit AppTest
```

How it fits together: `app.py` builds one `st.Page` per section from
`navigation.SECTIONS`. Each section page calls `pages.render_section(key)`,
which shows the summary, a "Not implemented" warning, planned scope, and the
tracked features from `features.yaml`. The home page reads all three YAML
files. No page reads data or environment variables.

## Local quality workflow (Stage 2)

```
uv.lock                      Universal lock: runtime + dev group (ADR 0003)
scripts/setup-env.ps1        uv sync --locked into .venvs/pyXY (network, one time)
scripts/check.ps1            Runs scripts/quality.py with .venvs/pyXY's interpreter
scripts/quality.py           Offline gate: config, lock check, ruff, pytest, smoke,
                             tracked/staged paths, secret scan; nonzero on failure
scripts/license_inventory.py Regenerates docs/dependency-licenses.md from the lock
tests/guards.py              Fake-result guards, keyed to features.yaml status
```

## Planned components (not implemented)

| Component | Responsibility | Feature | Notes |
|-----------|----------------|---------|-------|
| Connectors | One module per source, fetching into raw Parquet | DATA-01..03 | EIA first (R-25) |
| Observation store | Append-only Parquet + DuckDB views | STORE-01 | PRD P-1, P-2 |
| Metadata store | SQLite: sources, series, jobs, revisions, model runs | STORE-02 | |
| Content | Markdown lessons with effective-dated front matter | LEARN-01..02, COMP-01 | PRD P-4 |
| Model adapter | Validated interface to mambo-power | MODEL-01 | PRD P-5, U-2 |
| Replay | Assembles one operating day from stored observations | REPLAY-01 | |
| Finance | Contract and risk education/analysis | FIN-01..02 | |
| Health | Job status, freshness, storage, versions | HEALTH-01 | |

## Data flow (planned)

```
source API ──connector──▶ DATA_DIR/raw/*.parquet ──DuckDB──▶ pages
                 │
                 └──────▶ SQLite metadata (source, retrieval time, revision)
mambo-power ◀──validated adapter──▶ modeled outputs (labeled "modeled")
```

## Provenance labels

Every displayed value is labeled observed, derived, modeled, or synthetic
(PRD R-15). The definitions are in `content/data-labels.yaml` and appear on
the home page.
