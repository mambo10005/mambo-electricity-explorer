# Progress Log

Newest first. One entry per meaningful step.

## 2026-10-11 — Stage 3: first bounded EIA collection, storage, and chart (#5)

Stacked on Stage 2 (PR #4), which is stacked on Stage 1 (PR #2). None merged.

- **Dataset review** (source register):
  - EIA-930 `electricity/rto/region-data`; `ERCO` verified in EIA's official
    reference tables; metrics `D`/`DF`; units `megawatthours`.
  - Hour-ending is documented for EIA-930 but **not for the API `period`
    field**, so interval boundaries are not derived.
  - Cleared for local collection and use. Public redistribution not yet reviewed.
  - Without a key, EIA metadata returns HTTP 403, so live facet verification
    is pending.
- **Dependencies:** `duckdb 1.5.6` and `pyarrow 25.0.1` declared and locked.
  The license inventory has 46 packages. A new test replaces the Stage 2 ban:
  every declared runtime dependency must be imported in `src/`.
- **Connector:**
  - bounded queries, deterministic pagination, strict validation
  - timeouts, bounded retries with backoff, a request budget
  - redaction of raw, encoded, query, and echoed keys; errors raised `from None`
- **Storage:**
  - Parquet partitioned by entity/metric/run, a SQLite run catalog, DuckDB
    `observations`/`latest` views
  - idempotent re-ingest; revisions with lineage
  - atomic file writes plus a one-transaction commit; single-writer lock
  - `validate` for recovery (reports by default; quarantine moves, never deletes)
- **CLI** (`mambo`): `sources [--remote]`, `collect [--dry-run]`, `validate`,
  `status`, `storage`.
- **Explore page:**
  - ERCOT actual demand vs. the BA-published day-ahead forecast
  - date range, completeness and missing-value indicators, observation table
  - source, units, and interval text; last collection and a stale warning
  - limitations
  - instructions instead of a chart when no data exists
- **Tests:** 118 offline tests. The gate passes 8/8 on CPython 3.11.16 and
  3.14.2. All fixtures are **synthetic**, generated in `tests/eia_fixtures.py`.
- **Browser (Chrome, desktop):**
  - Populated state, using a scratch store seeded with *synthetic* rows: the
    chart draws two lines with a gap at the missing hour, and the table expands.
  - Empty state: instructions, no chart or table, no store created.
  - Fixed during the check: legend labels were truncated, and both series were
    drawn in near-identical blues.
- **Live (2026-10-11):** a key appeared in the gitignored `.env` partway
  through the stage. All live commands ran through a guard that suppresses
  output containing any form of the key; no leak was detected.
  - Metadata verified with 3 requests.
  - One bounded collection (1 request): 408 rows. Demand complete; 24
    forecast hours absent from the source.
  - All 408 stored rows match the archived response.
  - The repeat collection was idempotent (408 unchanged).
  - Field names confirmed. Missing data appears as absent rows. The period
    convention is still not stated by the API.
  - DATA-01 → `done`.
  - Explore browser-checked with the real data: two lines, the forecast gap
    shown, the absent-hours warning shown.
- **Guard fix:** the Stage 2 chart guard counted *any* done feature as unlocking
  its section. That meant done backend features would have authorized charts on
  the "Not implemented" Sources and System Health pages. Features that deliver a
  page are now marked `ui: true`, and only those unlock charts. A test also
  checks that the page dispatcher matches these flags.
- Next: beginner lessons using these observations.

## 2026-10-11 — Stage 2: reproducible local quality workflow (#3)

Stacked on Stage 1 (PR #2, unmerged).

- **Lock:** `uv.lock` (uv 0.12.5, universal) covers runtime dependencies and
  the `dev` group. The dev tools moved from an extra to a PEP 735 dependency
  group (ADR 0003). DuckDB and PyArrow are still not declared.
- **Environments:** `.venvs/py311` (CPython 3.11.16) and `.venvs/py314`
  (CPython 3.14.2), built with `uv sync --locked`. The developer's `.venv`
  was not touched.
- **Quality gate** (`scripts/check.ps1` → `scripts/quality.py`), 8 checks:
  - config/content validation, offline lock check, Ruff lint and format check
  - offline pytest (42 tests), import + headless startup smoke test
  - tracked/staged/untracked path check, secret scan
- **Results:** 8/8 pass on both Python 3.11.16 and 3.14.2 (Windows 11).
- **The gate fails when it should:**
  - It exited 1 on a real lint/format slip.
  - It exited 1 on a planted token-shaped string and a force-staged
    stack dump, without printing the token.
  - Its temporary server is stopped, and it changes no source or tracked
    files.
- **Guards:** the fake-result guards are now feature-status-aware
  (`tests/guards.py`). Self-tests show that a chart on an unimplemented page
  fails, an authorized chart on an implemented page passes, and feature-status
  drift fails.
- **Licenses:** `docs/dependency-licenses.md` covers 45 locked packages.
  - 10 are flagged "needs review": compound expressions, a bare "BSD
    License" classifier, or MPL.
  - 3 shipped license files were read by hand (pytest, pyyaml, ruff).
  - Streamlit's wheel ships no license file, so it is unresolved.
- **Sources:** ERCOT recorded as the first operator after EIA (R-29). EIA
  terms reviewed (source register); the source notes of each EIA route are
  still pending.
- Not done: hosted CI, Python 3.12/3.13, non-Windows platforms, a browser
  re-check (no UI change except QA-01's status).
- Next: DATA-01 bounded EIA collection and storage.

## 2026-10-11 — Stage 1: product specification and application shell (#1)

- PRD filled in from the owner's requirements and split into confirmed
  requirements (R-1..R-28), proposed design decisions (P-1..P-8), and
  unresolved decisions (U-1..U-9). The license is still pending.
- Added the source register (EIA first; every source's review still pending)
  and ADR 0002 (stack and dependency versions).
- Streamlit shell in `src/mambo_explorer`: Home plus 8 sections. Every
  section shows its scope and "Not implemented". The app shows no data,
  charts, or model output.
- `.env.example`: the generic `DATA_SOURCE_API_KEY` is replaced by
  `EIA_API_KEY` (PRD P-7). `DATA_DIR`, `CACHE_DIR`, and `LOG_LEVEL` are kept.
- Offline tests: import, navigation, feature-status consistency, docs/content
  structure, and Streamlit `AppTest` rendering of every page.
- Not done: data collection, storage, modeling, finance/compliance engines,
  authentication, CI.
- Next: QA-01 local quality workflow, then DATA-01 EIA connector.

## 2026-10-11 — Repository initialized

- Created private repo `mambo10005/mambo-electricity-explorer`.
- Added scaffold: README, CLAUDE.md, .gitignore, .env.example,
  pyproject.toml, docs, ADRs, issue and PR templates.
- No application code or dependencies yet.
