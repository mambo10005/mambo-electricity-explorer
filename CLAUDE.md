# CLAUDE.md — mambo-electricity-explorer

Guidance for Claude Code (and other agents) working in this repo.

## Project

Python (>=3.11) application for exploring electricity data. Requirements live
in `docs/PRD.md`; structure in `docs/architecture.md`. Read both before
non-trivial work.

## Hard rules

- Never commit secrets, `.env` files, raw data, Parquet/Arrow files,
  databases, contracts, compliance evidence, logs, or generated reports.
  `.gitignore` covers these — don't weaken it without an ADR.
- Before every commit, run the quality check (below). It also inspects
  tracked/staged paths and scans for secrets. Then review
  `git diff --cached --name-only` yourself.
- Never force-push, change repo visibility, merge PRs, or deploy without
  explicit owner approval.
- Adding a dependency or data source requires a license/terms check (see
  `docs/decisions/0001-license.md`, `docs/source-register.md`). Private
  visibility is not a substitute.
- Never edit `uv.lock` by hand, and never let a check rewrite it. Dependency
  changes are a deliberate `uv lock` followed by
  `scripts/license_inventory.py` (ADR 0003).
- Don't touch the developer's `.venv`. Verification uses `.venvs/py311` and
  `.venvs/py314`.
- EIA credential: never print, log, or archive it.
  - Anything that could carry it goes through `eia/redact.py`.
  - Errors are re-raised `from None`.
  - Tests must never need it.
  - Never run `mambo collect` from app code.
- Data stays in `MAMBO_DATA_DIR` (default `./data`, gitignored). Never commit
  archives, Parquet, or SQLite files. EIA facts live only in
  `eia/dataset.py`, backed by the source-register review (ADR 0004).

## Workflow

- Branch from `main` (or stack on an unmerged stage branch); open a draft PR
  using the template. See `docs/github-workflow.md`.
- Record significant decisions as ADRs in `docs/decisions/` (copy
  `0000-template.md`).
- Update `docs/progress.md` and `docs/feature-matrix.md` when work lands.
- Feature status lives in `src/mambo_explorer/content/features.yaml`; keep
  `docs/feature-matrix.md` in sync (a test enforces it).
- Never show fabricated data. Every displayed value must carry an
  observed/derived/modeled/synthetic label (PRD R-15). Tests reject data
  elements (charts, maps, metrics) on any section whose features are not
  `done` (`tests/guards.py`). Don't weaken that guard to make a test pass.
- Sources are stored in separate Store namespaces (`eia930`, `ercot-np6-345-cd`).
  - Never join or compare EIA and ERCOT data until the unresolved differences in the
    source register are resolved.
  - Never convert ERCOT OperDay/HourEnding to UTC.
- Browser checks: record the PIDs of Streamlit processes before starting servers, and
  kill only the ones you started. Verify zero remain at the end.
- mambo-power is used only through `modeling/adapter.py`, pinned to a full commit
  (ADR 0006).
  - Expose a capability only after independent benchmarks.
  - OPF prices are shown only through `run_dc_opf`'s per-run verification (ADR 0007).
    Never present them as ISO prices.
  - Never modify the package repository.
- Lessons follow `docs/lesson-authoring.md`.
  - Never mark content `human-reviewed` unless a named person reviewed it.
  - Never hardcode current data in lesson text.
  - Numbers come from `calculations.py`, never from UI code.
  - Model lessons take numbers only from current verified runs
    (`modeling/cases.py`, `model_exercises.py`); never quote results in prose.
  - Escape `$` in rendered Markdown (`opf_lab.md_dollars`); keep at most one `$` in
    widget labels and radio options.
  - Describe the price check's re-solves only with `modeling/sensitivity.py` terms
    (averages over the change, per-direction feasibility).
- Tests never touch the real `./data` (`tests/conftest.py` enforces it). Never call
  `monkeypatch.undo()` in a test: it also drops the `MAMBO_DATA_DIR` override.
- Browser and harness servers get a scratch `MAMBO_DATA_DIR` and
  `MAMBO_FORBIDDEN_DATA_DIRS=<repo>/data` (`docs/testing-isolation.md`).
- Never run `mambo learn-reset --execute`; the owner decides about their progress.
- Settlement is a teaching formula (ADR 0009): never present it as an ISO settlement or
  invoice, never generalize one operator's rules, never use EIA forecasts as schedules,
  and import only verified modeled prices (`settlement.modeled_price`).
- Basis/hedge is a teaching cash flow (ADR 0010): never call it a real contract or
  valuation; K is always synthetic; two modeled location prices only from one run
  (`basis.modeled_pair`).
- Time shape is a teaching cash flow (ADR 0011): intervals are elapsed durations, never
  calendar times or DST; the time-shape component is an accounting split, not a
  standard metric; never stitch OPF runs into a time series.
- Compliance content is educational (ADR 0012).
  - Records live in `content/responsibilities.yaml`, one paraphrased claim per source
    section.
  - Say "relevant source to investigate"; never conclude applicability from a title,
    label, or location.
  - Unknown dates are null. A retrieval date is never an effective date, and a
    proposal never has one.
  - Never bypass a human-verification page; record the gap instead.
  - Never attribute a synthetic requirement to a real authority.
- Generation by energy source is a separate dataset (ADR 0014).
  - Own store namespace; identity includes `energy_source`; never touch demand rows.
  - Keep every category the source returns (flag unreviewed codes); keep signs and
    units; never zero-fill; never clip negatives.
  - Never call a category sum total system generation, never equate generation with
    demand, never infer interchange or losses, never show a pie of signed values,
    and never name the price-setting unit from the mix.
  - Disabled in the default refresh plan; its success never implies demand's, or
    the reverse.
- Time display (ADR 0015): every time-axis chart of UTC labels goes through
  `timeview.utc_label_chart` (utc scale, verbatim-label tooltip); never give
  `st.line_chart`/`st.bar_chart` datetimes, never strip time zones to fix an axis,
  never place ERCOT labels on a time scale, never give synthetic intervals calendar
  times. Retrieval times print with `format_utc`. See `docs/timestamp-display.md`.
- Refresh and health (ADR 0013).
  - `mambo refresh` only orchestrates the existing collectors: no second ingestion
    path, sequential, bounded by `content/refresh.yaml`.
  - Plan catch-up from committed runs, never from absent rows; never fill gaps.
  - System Health and the app never collect. Freshness comes from observation labels
    or source publication time, never from request time; "unknown" when
    undeterminable.
  - Never register, change, or remove a scheduled task without the owner's explicit
    request (`scripts/refresh-task.ps1` defaults to Preview).
- `focus.css` is the only CSS the app adds (ADR 0008): focus-only, stable selectors,
  no generated classes, no script. New CSS needs an ADR.
- Theme colors live in `.streamlit/config.toml`; re-measure rendered contrast
  (`docs/accessibility.md`) when it or Streamlit changes.
- Tested Python versions (3.11, 3.14) are recorded separately from the
  declared `requires-python`; never change `requires-python` to hide a failure.

## Commands (Windows PowerShell; uv 0.12.x)

```powershell
pwsh -File scripts/setup-env.ps1 [-Python 3.11]   # one-time; downloads; uses uv.lock
pwsh -File scripts/check.ps1 [-Python 3.11]       # routine; offline; nonzero on failure
.venvs/py314/Scripts/streamlit run src/mambo_explorer/app.py
.venvs/py314/Scripts/python scripts/license_inventory.py   # after any uv lock
.venvs/py314/Scripts/mambo collect --dry-run               # never needs a key
.venvs/py314/Scripts/mambo validate                        # read-only store check
.venvs/py314/Scripts/mambo refresh --dry-run              # refresh plan; sends nothing
pwsh -File scripts/refresh-task.ps1                        # task preview only
```
