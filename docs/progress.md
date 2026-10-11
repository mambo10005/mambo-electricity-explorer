# Progress Log

Newest first. One entry per meaningful step.

## 2026-10-11 — Stage 5: direct ERCOT actual-load connector (#9)

Stacked on Stage 4 (PR #8) ← #6 ← #4 ← #2. None merged.

- **Report:** ERCOT NP6-345-CD "Actual System Load by Weather Zone" (type 13101).
  - Access: the ercot.com public listing + download, which needs no login. These are
    the URLs ERCOT's product page uses, not a documented developer API (ADR 0005).
  - The ERCOT Public API needs registration (401 without it). No account was created
    and no terms were accepted.
- **Review** (source register; `docs/datasets/ercot-np6-345-cd.md`):
  - Terms §5 permit raw-data reuse in compilations, charts, and analyses; §6 forbids
    degrading ERCOT systems.
  - Local use cleared. Publication review still pending.
  - Unverified: units, label time zone, DST representation, and the TOTAL definition.
- **Connector:**
  - one transport; budget of 10 requests and at most 7 documents per run
  - 30 s timeouts, at most 2 retries, 1 s pause between requests
  - listing and ZIP size limits; in-memory ZIP reading with path, member, and size
    checks (`safe_zip.py`)
  - strict CSV header and row validation
  - clear access and unavailable errors; no scraping fallback; never uses
    EIA_API_KEY
- **Storage:** `Store(namespace, schema, identity)`.
  - ERCOT lives in `ercot-np6-345-cd/` with its own catalog and lock. EIA is
    untouched (no migration).
  - Identity includes OperDay, HourEnding, and DSTFlag, so DST twins stay distinct.
  - Reposts become revisions with document lineage.
- **CLI:** `--source ercot` on `sources`/`collect`/`validate`/`status`/`storage`.
  ERCOT collect takes `--latest N` or `--publish-date`, plus `--dry-run`.
- **Explore:** a source selector (EIA or ERCOT direct, never joined). The ERCOT view
  shows:
  - TOTAL and zones in a tested 9-colour palette
  - original labels, with HourEnding/DSTFlag on the chart axis
  - a chart `alt` text
  - coverage and the zone-sum check
  - publication time (raw and UTC) and retrieval time
  - units "not stated", and limitations
- **Tests:** 252 offline tests. Gate 8/8 on CPython 3.11.16 and 3.14.2. Fixtures are
  synthetic; no ERCOT file is committed.
- **Live (2026-10-11, no credential):**
  - The listing showed 32 public CSV documents (published 2026-09-10..2026-10-11).
  - `--latest 3` collected OperDays 10/08–10/10/2026: 648 values, all DSTFlag N,
    0 nulls, max |zone sum − TOTAL| 0.02.
  - Stored values match the archived files 648/648.
  - The repeat collection was idempotent (648 unchanged). `validate` ok.
  - The EIA catalog sha256 was unchanged.
- **Browser (Chrome),** using scratch copies of the data:
  - EIA view still renders.
  - ERCOT view: chart, label axis, units, provenance, coverage, and limitations;
    zone selection works by keyboard.
  - 375 px dark: no page overflow.
  - Empty ERCOT store: instructions, no chart, and no store created.
  - **Gap:** the 12-column hourly table scrolls inside a container that can't take
    keyboard focus (a Streamlit limitation).
- **Processes:** the baseline had 0 Streamlit processes. Servers were started with
  recorded PIDs, and exactly those 6 PIDs (2 trees) were killed. 0 remain.
- Next: verify ERCOT's DST representation on OperDay 2026-11-01 (posted about
  2026-11-02), then reconciliation research only if units and time zones become
  documented.

## 2026-10-11 — Stage 4: beginner lessons using EIA observations (#7)

Stacked on Stage 3 (PR #6) ← #4 ← #2. None merged.

- **Lesson engine** (`lessons.py`): validated Markdown + YAML front matter with
  versions, effective dates, sources, dataset bindings, calculation ids,
  exercises, limitations, and review fields. Validation rejects "human-reviewed"
  without a named reviewer, an AI reviewer, or a reviewer who is also the author.
  All four lessons are **agent-drafted, unreviewed**.
- **Four lessons:**
  1. power vs. energy (synthetic examples only)
  2. reading a demand series
  3. demand vs. the published forecast (error = actual − forecast; mean error,
     MAE, RMSE)
  4. missing observations (absent vs. null vs. zero vs. not collected;
     coverage per series)
- **Calculations** (`calculations.py`, CALC-01; docs/calculations.md):
  - `power_energy`, `series_summary`, `coverage`, `forecast_error`, all
    pure and versioned
  - results keep selection, unit, formula version, valid counts,
    exclusions, and revision references
  - "unavailable" instead of a number for empty, duplicate, or mixed-unit input
- **Exercises:**
  - generated from a snapshot fingerprint (selection + revisions + values)
  - deterministic per snapshot; regenerated, with a notice, when the window or
    the data changes
  - answers computed by the same calculations
- **Progress:** local JSON in `<MAMBO_DATA_DIR>/learn/progress.json`
  (gitignored), with three distinct states. "Understanding demonstrated" requires
  every exercise to be right on the first attempt.
- **Learn page:**
  - status table and lesson selector; prerequisite buttons; deep links
    (`?lesson=`)
  - beginner/technical toggle and glossary with acronym expansions
  - sources and freshness
  - charts with HTML data tables
  - exercises with worked explanations; bookmarks
- **Tests:** 192 offline tests. Gate 8/8 on CPython 3.11.16 and 3.14.2.
- **Browser (Chrome),** using copies of the real local observations in scratch
  directories, so the user's own progress file was not touched:
  - all 4 lessons populated in the light theme
  - all 4 empty: text readable, no charts, instructions, data exercises marked
    unavailable
  - keyboard-only: Tab order reaches every control; arrow keys pick an option;
    Enter submits
  - 375 px dark: no page overflow
  - light theme: text contrast 12.5:1
- **Fixed from browser findings:**
  - the status table lagged one interaction behind an answer
  - lesson labels changed with progress, which can reset the selector
  - an 8-column coverage table needed sideways scrolling on phones; now 3 columns
  - the orange chart line was 2.53:1 on white; now #d95f02 at ≥ 3.7:1 in both
    themes, with a regression test
- Also found: a Stage 3 Streamlit server was still running, because TaskStop
  leaves the server process behind. It is stopped, and cleanup is now explicit.
- Not done:
  - no human review of lesson content
  - no screen-reader testing
  - charts have captions and data tables but no in-chart text alternative
  - other browsers not tested
- Next: Stage 5, a bounded ERCOT connector (R-29), after its source review.

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
