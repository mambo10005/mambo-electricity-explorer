# Architecture — mambo-electricity-explorer

**Status:** Stage 3. The shell, the quality workflow, and EIA-930 collection,
storage, and Explore exist. Everything under "Planned components" is unimplemented.

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
tracked features from `features.yaml`. Explore is the exception (`pages.render_page`
dispatches it to `explore.py`). The home page reads all three YAML
files. Only Explore reads observations, and no page ever collects data.

## EIA collection and storage (Stage 3, ADR 0004)

```
src/mambo_explorer/
  config.py        MAMBO_DATA_DIR safety checks; EIA_API_KEY; optional gitignored .env
  eia/dataset.py   Reviewed EIA-930 facts (route, ERCO, D/DF, units, interval convention)
  eia/client.py    Bounded API v2 client: timeouts, retries, budget, strict validation
  eia/redact.py    Credential redaction (raw, %-encoded, +-encoded, query, JSON echo)
  collect.py       Plan (bounded days + lookback), normalize, revisions, collect()
  storage.py       Parquet + SQLite catalog + DuckDB views; lock; validate/recover
  cli.py           `mambo sources|collect|validate|status|storage`
  explore.py       Explore page (reads committed observations only)
```

Data flow (implemented):

```
mambo collect --EIAClient--> api.eia.gov (key in URL; never logged)
     |                          | validated, sanitized pages
     v                          v
 SQLite runs: started --> raw/run=.../page-*.json --> observations/entity=.../metric=.../run=....parquet
     +-------- one transaction: register files + sha256, status=committed <----+
Explore page --DuckDB (UTC, no extension downloads)--> `latest` view over committed files only
```

## Economic dispatch (Stage 7, ADR 0007)

```
src/mambo_explorer/
  modeling/opf_network.py  SYNTHETIC dispatch network: linear offers, capacities, ratings, 1-h interval
  modeling/adapter.py      + run_dc_opf: opf.solve_dc_opf, primal/KKT/decomposition checks,
                           two-sided price sensitivities, non-unique dispatch detection
  opf_lab.py               Economic-dispatch lab (teaching-case presets, verified prices only)
```

## Modeling (Stage 6, ADR 0006)

```
src/mambo_explorer/
  modeling/teaching_network.py  SYNTHETIC 3-bus network, bounded inputs, topology tables
  modeling/adapter.py           Only caller of mambo-power (pf.solve_dc); independent checks;
                                status ok / ok_with_violations / failed; provenance incl. commit
  modeling/runs.py              Run records in <MAMBO_DATA_DIR>/model-runs/ (atomic, never overwritten)
  model_lab.py                  Model Labs page; results hidden when inputs change
```

## ERCOT direct connector (Stage 5, ADR 0005)

```
src/mambo_explorer/
  safe_zip.py          In-memory ZIP reading with path, member, and size limits (no extraction)
  ercot/dataset.py     NP6-345-CD contract: header, zones, schema, identity, strict CSV parser
  ercot/client.py      Public listing + download; budget, timeouts, retries, pauses, validation
  ercot/collect.py     Selection (latest N / publish dates), normalize, revisions, collect()
  ercot_explore.py     Explore view for ERCOT (source selector in explore.py)
```

`Store(data_dir, namespace, schema, identity)`: each source gets its own directory,
SQLite catalog, writer lock, Parquet schema, and identity. EIA uses the defaults
(`eia930`). ERCOT uses `ercot-np6-345-cd`, with identity
(source, dataset, entity, metric, oper_day, hour_ending, dst_flag).

## Learning engine (Stage 4)

```
src/mambo_explorer/
  calculations.py   Pure calculations: power_energy, series_summary, coverage,
                    forecast_error; snapshot_id; load_observations (latest view)
  lessons.py        Load + validate lessons (front matter schema, review rules, prereqs)
  exercises.py      Exercise generators; answers from calculations; deterministic per snapshot
  progress.py       Local progress/bookmarks: <MAMBO_DATA_DIR>/learn/progress.json
  learn.py          Learn page: status table, lesson, panels, exercises, glossary, sources
  content/lessons/  01..08 *.md (YAML front matter + Beginner / Technical detail)
  settlement.py     Stage 11: teaching energy-settlement formula, bounds, provenance,
                    verified modeled-price import (ADR 0009)
  settlement_ui.py  calculator shared by the Finance page and lesson 8
  settlement_exercises.py  exercises from the calculator's current result
  basis.py          Stage 12: basis-exposure teaching cash flows, decomposition,
                    same-run modeled price pairs (ADR 0010)
  basis_ui.py, basis_exercises.py  calculator (Finance, lesson 9) and exercises
  shape.py          Stage 13: flat-block hedge time-shape cash flows, two decompositions,
                    predefined synthetic scenarios (ADR 0011)
  shape_ui.py, shape_exercises.py  accessible interval editor/viewer and exercises
  finance.py        Finance page (FIN-03, FIN-04, FIN-05 only)
  responsibilities.py  Stage 14: loads and validates content/responsibilities.yaml
                    (versioned, source-backed records; ADR 0012)
  compliance.py     Compliance page: responsibility explorer (COMP-02); no fetching
  compliance_exercises.py  lesson 11-12 exercises keyed on the record-set fingerprint
  model_exercises.py  Stage 8: exercise answers from verified model records; snapshot
                    = inputs, pin, check versions, statuses; result refs = run ids
  model_lessons.py  Stage 8: lesson model section (explicit run button, panels,
                    units, provenance, lab links)
  modeling/cases.py Stage 8: lab presets and fixed lesson runs; is_current guard
  routes.py         Learn <-> Model Labs links (validated ids via session state)
  content/glossary.yaml
```

Pages never compute numbers themselves. Every value shown in a lesson panel or used
as an exercise answer comes from a `CalcResult`, which keeps its selection, unit,
formula version, exclusions, and revision references (docs/calculations.md).
Model lessons (5–7) take their numbers only from current, verified model records
(`modeling/cases.is_current`), saved in the model-run store, never the observation
store.

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
| Connectors | One module per source | DATA-02..03 | EIA-930 built (DATA-01 in progress, live unverified); ERCOT next (R-29) |
| Content | Markdown lessons with effective-dated front matter | LEARN-01..02, COMP-01 | PRD P-4 |
| Model adapter | Further mambo-power capabilities (OPF, markets) | MODEL-01 | DC power flow done (ADR 0006); OPF needs independent verification (BL-2) |
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
