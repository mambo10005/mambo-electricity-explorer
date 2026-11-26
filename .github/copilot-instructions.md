# Copilot instructions — mambo-electricity-explorer

Local-first Python (>=3.11) Streamlit app for exploring U.S. electricity data
(EIA-930, ERCOT direct, DC power flow / OPF modeling). Requirements:
`docs/PRD.md`. Structure: `docs/architecture.md`. Read both before non-trivial
work. `CLAUDE.md` has the full, authoritative rule set — this file summarizes
what's needed to act effectively; when in doubt, defer to `CLAUDE.md`.

## Build, test, lint (Windows PowerShell; uv 0.12.x)

```powershell
pwsh -File scripts/setup-env.ps1 [-Python 3.11]   # one-time env setup from uv.lock
pwsh -File scripts/check.ps1 [-Python 3.11]       # full offline quality gate; run before every commit
```

`scripts/check.ps1` runs `scripts/quality.py`, which does: config/content
validation, lock consistency check, Ruff lint + format check, offline pytest,
an import/app-startup smoke test, tracked/staged-path checks, and a secret
scan (reports file:line only, never the matched text). It exits nonzero on
any failure, never edits files or `uv.lock`, and never downloads anything.

Run narrower checks directly with the venv interpreter:

```powershell
.venvs/py314/Scripts/python -m pytest tests/test_calculations.py -k test_name   # single test
.venvs/py314/Scripts/python -m ruff check src tests
.venvs/py314/Scripts/python -m ruff format --check src tests
```

Two tested interpreters exist side by side: `.venvs/py311` and `.venvs/py314`.
Never touch the developer's own `.venv`. Full test suite is offline and uses
only synthetic/fixture data — never the real `./data` dir or the EIA key.

Other useful commands:

```powershell
.venvs/py314/Scripts/streamlit run src/mambo_explorer/app.py    # launch app (http://localhost:8501)
.venvs/py314/Scripts/mambo collect --dry-run                    # plan only; never needs a key
.venvs/py314/Scripts/mambo validate                              # read-only store check
.venvs/py314/Scripts/mambo refresh --dry-run                     # refresh plan; sends nothing
.venvs/py314/Scripts/python scripts/license_inventory.py          # regenerate docs/dependency-licenses.md after `uv lock`
```

## Architecture (see `docs/architecture.md` for full detail)

- `app.py` builds one `st.Page` per section from `navigation.SECTIONS`
  (pure-data module, no Streamlit import). `pages.render_section(key)` renders
  a generic "not implemented" view driven by `content/features.yaml`
  (single source of truth for feature status); `pages.render_page` dispatches
  **Explore** to `explore.py` instead.
- **Pages never compute numbers.** Every displayed value flows from a
  `CalcResult` (`calculations.py`) carrying selection, unit, formula version,
  and exclusions, or from a verified model `run` record. Lesson/model code
  reads only current, verified records (`modeling/cases.is_current`), never
  recomputes inline.
- **Each data source is an independent `Store(data_dir, namespace, schema,
  identity)`**: own directory, SQLite catalog, writer lock, Parquet schema,
  identity tuple. Collection flow: `mambo collect` → source client (`eia/`,
  `ercot/`) → validated/sanitized pages → SQLite run row (`started` →
  `committed` in one transaction) → `raw/...json` + `observations/...parquet`
  → DuckDB `latest` view over committed files only → page.
- `modeling/adapter.py` is the **only** caller into the external `mambo-power`
  package (pinned full commit, ADR 0006); it performs independent
  verification (primal/KKT/decomposition checks) before anything is shown as
  "modeled".
- ERCOT features build in layers, each gated by its own ADR and a
  `*_policy.py` module that owns the versioned rule/assumption (never infer
  semantics elsewhere): alignment (`ercot/alignment.py`, ADR 0019) →
  assumption M1 (`ercot/m1_policy.py` + `ercot/approvals.py`, ADR 0020) →
  hourly aggregation (`ercot/aggregation_policy.py`/`aggregation.py`, ADR 0021)
  → comparison (`ercot/comparison_policy.py`/`comparison.py`, ADR 0022) →
  governance (`ercot/governance.py`, `governance_cli.py`, ADR 0023), which is
  the only path that may activate/approve any of the above in production.
- `tests/conftest.py` enforces that no test ever touches the real `./data`:
  it redirects `MAMBO_DATA_DIR` to a session temp dir, sets
  `MAMBO_FORBIDDEN_DATA_DIRS` to the real `data/`, and fingerprints `data/`
  before/after the whole session. **Never call `monkeypatch.undo()`** in a
  test — it also reverts the `MAMBO_DATA_DIR` override.

## Key conventions

- **Provenance labels**: every displayed value must be `observed`,
  `derived`, `modeled`, or `synthetic` (PRD R-15). `tests/guards.py` rejects
  data elements (charts, maps, metrics) on any section whose features in
  `content/features.yaml` aren't `done` — don't weaken that guard to pass a
  test.
- **Never commit** secrets, `.env`, raw data, Parquet/Arrow files, databases,
  contracts, compliance evidence, logs, or generated reports; `.gitignore`
  covers these.
- **`uv.lock` is only changed via `uv lock`** (ADR 0003), followed by
  `scripts/license_inventory.py`; never hand-edit it or let a tool rewrite it.
- **EIA credential**: never print/log/archive it; anything that could carry
  it routes through `eia/redact.py`; related errors are re-raised `from
  None`; tests must never need the key; **never run `mambo collect` from app
  code** (only user-invoked CLI).
- **ERCOT ↔ EIA data must never be joined or compared** until differences in
  `docs/source-register.md` are resolved. ERCOT `OperDay`/`HourEnding` are
  never converted to UTC — ERCOT values are shown exactly as published with
  their own labels (see `docs/timestamp-display.md`, ADR 0015 —
  `timeview.utc_label_chart` is the only path for time-axis charts).
  Real-time vs. day-ahead ERCOT comparisons only via the governed
  `comparison.compare` after all policy approvals (ADR 0022); never a default
  sign, never called DART/settlement/P&L.
  Mambo-power results are only ever labeled "modeled", never an ISO price.
- **Lessons** (`content/lessons/*.md`): never mark `human-reviewed` unless a
  named person reviewed it; never hardcode current data in lesson prose;
  numbers come only from `calculations.py`/verified model runs, never from UI
  code (`docs/lesson-authoring.md`).
- **Settlement / basis / time-shape** (`settlement.py`, `basis.py`,
  `shape.py`) are teaching formulas, not real ISO settlement, contracts, or
  valuations (ADR 0009–0011); synthetic inputs stay labeled synthetic.
- **Compliance content** (`responsibilities.py`, `content/responsibilities.yaml`)
  is educational: one paraphrased claim per source section, phrased as "a
  relevant source to investigate" — never conclude applicability from a
  title/label/location, never attribute a synthetic requirement to a real
  authority.
- **Dependency/data-source changes** need a license/terms check (ADR 0001,
  `docs/source-register.md`) before adding.
- `focus.css` is the only CSS the app adds (ADR 0008, focus-only, stable
  selectors); any new CSS needs an ADR.
- Keep `docs/feature-matrix.md` in sync with
  `src/mambo_explorer/content/features.yaml` — a test enforces this.
- Browser/harness checks use a scratch `MAMBO_DATA_DIR` and
  `MAMBO_FORBIDDEN_DATA_DIRS=<repo>/data`; record Streamlit PIDs you start
  and kill only those, verifying zero remain (`docs/testing-isolation.md`).
- Never run `mambo learn-reset --execute` or register/change a scheduled
  task (`scripts/refresh-task.ps1`) without the owner's explicit request.

## Workflow

- The owner is the sole developer: commit and push directly to `main`; do not
  open PRs or feature branches unless asked. Run `scripts/check.ps1` before
  every commit.
- Record significant decisions as ADRs in `docs/decisions/` (copy
  `0000-template.md`); update `docs/progress.md` and `docs/feature-matrix.md`
  when work lands.
- Never force-push, change repo visibility, or deploy without explicit owner
  approval.
