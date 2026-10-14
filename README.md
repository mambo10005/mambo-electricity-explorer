# mambo-electricity-explorer

A local-first, novice-oriented platform for learning and analyzing the U.S.
electricity system from actual observations and reproducible modeling. See
[docs/PRD.md](docs/PRD.md).

**Status:** Stage 8. The application shell, the quality workflow, ERCOT's hourly actual
demand and published day-ahead forecast (EIA-930) in a local store and on the Explore
page, four beginner lessons on the Learn page that use those observations, three
market-mechanics lessons backed by verified model runs, and a direct
ERCOT connector (actual load by weather zone) shown separately on Explore, and a Model Labs
DC power flow lab and an economic-dispatch (DC optimal power flow) lab on synthetic three-bus
networks using mambo-power (pinned commit). Navigation and documentation
exist. Modeling and the finance and compliance features are **not implemented**,
and every section except Explore shows only its planned scope. One bounded live
collection (7 days + 2-day lookback, 5 requests) was verified on 2026-10-11. The test
suite itself is offline and uses synthetic data only. Feature-by-feature status:
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

## 3. Collect EIA data (optional; needs a free EIA key)

```powershell
copy .env.example .env      # then put your key after EIA_API_KEY= in .env
.venvs/py314/Scripts/mambo sources --remote        # verify route/ERCO/D/DF with EIA (5 requests max)
.venvs/py314/Scripts/mambo collect --dry-run       # scope and request budget; no key needed
.venvs/py314/Scripts/mambo collect                 # last 7 completed UTC days + 2-day lookback
.venvs/py314/Scripts/mambo collect --start 2026-10-01 --end 2026-10-08   # explicit range (end exclusive)
.venvs/py314/Scripts/mambo status                  # recent runs
.venvs/py314/Scripts/mambo validate                # checksums, orphans, interrupted runs (read-only)
.venvs/py314/Scripts/mambo storage                 # storage diagnostics
```

- One run covers at most 31 days, lookback included.
- Collection never runs automatically, including when the app opens or reruns.
- Re-collecting is safe. Unchanged values are skipped, and changed values are
  kept as new revisions.
- Nothing is deleted by default. `validate --mark-interrupted` and
  `validate --quarantine-orphans` are the only commands that change anything,
  and quarantine moves files rather than deleting them.

### ERCOT direct (no key needed)

```powershell
.venvs/py314/Scripts/mambo sources --source ercot --remote     # what ERCOT currently publishes (1 request)
.venvs/py314/Scripts/mambo collect --source ercot --dry-run    # scope and budget; sends nothing
.venvs/py314/Scripts/mambo collect --source ercot --latest 3   # the 3 most recent daily files
.venvs/py314/Scripts/mambo collect --source ercot --publish-date 2026-10-11   # a specific posting
.venvs/py314/Scripts/mambo status --source ercot ; .venvs/py314/Scripts/mambo validate --source ercot
```

This uses ERCOT's public report download for NP6-345-CD (Actual System Load by
Weather Zone). That download is what ERCOT's own product page uses; it is not a
documented developer API. One run fetches at most 7 documents. ERCOT keeps about 31
days public. The data is stored separately from EIA in
`<MAMBO_DATA_DIR>/ercot-np6-345-cd/`.

Units and time zone are not stated by ERCOT, so they are shown as published. See
`docs/datasets/ercot-np6-345-cd.md`.

### EIA net generation by energy source (same key)

```powershell
.venvs/py314/Scripts/mambo sources --source eia-generation            # reviewed contract (offline)
.venvs/py314/Scripts/mambo collect --source eia-generation --dry-run  # scope and budget; sends nothing
.venvs/py314/Scripts/mambo collect --source eia-generation            # last 7 completed UTC days
```

Route `electricity/rto/fuel-type-data` for ERCO, stored in its own namespace
(`<MAMBO_DATA_DIR>/eia930-fuel-type/`). Values are signed exactly as EIA publishes them
(net storage is negative), every category the source returns is kept, and no category sum
is called total system generation. **Explore** shows a signed chart with coverage by
category; lesson 13, *Reading the actual generation mix*, explains it. The dataset is
disabled in the default refresh plan until you enable it (ADR 0014,
`docs/datasets/eia930-fuel-type-data.md`).

### ERCOT day-ahead price at the North Hub (no key needed)

```powershell
.venvs/py314/Scripts/mambo sources --source ercot-dam-spp                # reviewed contract (offline)
.venvs/py314/Scripts/mambo collect --source ercot-dam-spp --dry-run      # scope and budget; sends nothing
.venvs/py314/Scripts/mambo collect --source ercot-dam-spp --latest 2     # 2 most recent DAM runs
```

ERCOT NP4-190-CD "DAM Settlement Point Prices", stored for one settlement point, `HB_NORTH`
(North 345 kV Hub), in `<MAMBO_DATA_DIR>/ercot-np4-190-cd/`. Each download holds every
settlement point; only the hub is kept. Prices are $/MWh (per ERCOT's Protocols), signed as
published, labeled with ERCOT's DeliveryDate/HourEnding/DSTFlag (no UTC), and never called
final. **Explore** shows the day; lesson 14, *Reading an actual day-ahead electricity
price*, explains it. Opt-in in the refresh plan (ADR 0016,
`docs/datasets/ercot-np4-190-cd.md`).

### ERCOT real-time price at the North Hub (no key needed)

```powershell
.venvs/py314/Scripts/mambo sources --source ercot-rt-spp               # reviewed contract (offline)
.venvs/py314/Scripts/mambo collect --source ercot-rt-spp --dry-run     # scope and budget; sends nothing
.venvs/py314/Scripts/mambo collect --source ercot-rt-spp --latest 4    # newest 4 intervals not stored
# bounded backfill: the 16 oldest uncollected documents with these PublishDates (rerun to resume)
.venvs/py314/Scripts/mambo collect --source ercot-rt-spp --coverage-from 2026-10-07 --coverage-to 2026-10-07 --dry-run
```

ERCOT NP6-905-CD real-time Settlement Point Prices (produced from SCED LMPs every 15
minutes, including ERCOT's reliability deployment price adder, floored at −$251/MWh), stored
for `HB_NORTH` only in `<MAMBO_DATA_DIR>/ercot-np6-905-cd/`. Each interval keeps ERCOT's
DeliveryDate/DeliveryHour/DeliveryInterval/DSTFlag (no UTC). Lesson 15 explains it. Opt-in,
under the shared ercot.com request cap (ADR 0017, `docs/datasets/ercot-np6-905-cd.md`).
About 96 documents are published a day and the list keeps about 7 days. The collector does
not keep complete history; coverage mode and bounded backfill work through a range one run
at a time (ADR 0018, `docs/refresh-runbook.md`).

Explore also has a read-only **interval-alignment diagnostic**. It shows how a day-ahead
hour's labels relate to real-time interval labels, and it reads no prices. No mapping is
accepted yet: ERCOT's official materials do not define the reports' labels. So it reports
`unsupported_semantics`, plus a clearly labelled candidate check (ADR 0019,
`docs/interval-alignment.md`). No DART spread or day-ahead/real-time comparison exists.

### Refresh both sources and check health

```powershell
.venvs/py314/Scripts/mambo refresh --dry-run    # plan, catch-up findings, and request budgets; sends nothing
.venvs/py314/Scripts/mambo refresh              # bounded, one source after another
.venvs/py314/Scripts/mambo health               # read-only freshness and storage status
```

`mambo refresh` runs the same collectors with a validated, bounded plan
(`content/refresh.yaml`). It reports partial success separately (exit 3), and plans
catch-up only from successful runs. The **System Health** page shows the same status;
it never collects. Nothing is real-time. An optional Windows scheduled task can be
previewed with `pwsh -File scripts/refresh-task.ps1`; it is not registered unless you
ask. See [docs/refresh-runbook.md](docs/refresh-runbook.md) and ADR 0013.

### Model Labs (no data or key needed)

**Model Labs** runs a DC power flow on a **synthetic** three-bus network with
[mambo-power](https://github.com/mambo10005/mambo-power), pinned to the v0.2.0 commit
`26be8c1`. You set:
- G2's output
- the demand at bus C
- line AC's reactance and whether it is in service

Results are labeled *modeled* and are checked independently. They are shown only while
they match the current inputs. Runs are saved to `<MAMBO_DATA_DIR>/model-runs/`
(gitignored).

The **economic-dispatch** lab (same page, "Lab" selector) lets the model choose the
cheapest dispatch for synthetic offers. It reports:
- the cost as a $/h rate and over an explicit 1-hour interval
- binding line limits
- **modeled** nodal prices, shown only when each run's price check verifies them

Prices are withheld at breakpoints. Only DC power flow and linear-cost DC OPF are verified
and exposed. See `docs/capability-register.md` and ADR 0007.

## 4. Learn

The **Learn** page has seven beginner lessons:
1. power versus energy
2. reading a demand series
3. demand versus the published forecast
4. missing observations
5. power flow versus economic dispatch
6. why modeled prices differ by location
7. when one marginal number is not verified

Lessons 2–4 use your locally collected ERCOT observations. Without data they still
show their text, plus collection instructions. Exercises are generated from the data
window you select.

Lessons 5–7 use the **synthetic** three-bus network from Model Labs. Nothing runs until
you press **Run this lesson's model cases**. The results are **modeled** (never ISO
prices), and every exercise answer is computed from those verified runs. Results that
no longer match the scenario or the pinned package are hidden. Each lesson links to its
cases in Model Labs, and each lab links back to its lessons.

Progress and bookmarks are saved only on this computer, in
`<MAMBO_DATA_DIR>/learn/progress.json` (gitignored; no account). A lesson moves
through three states: *viewed*, *exercise completed*, and *understanding
demonstrated* (every exercise right on the first try; a self-check, not a
certification).

To back up and reset your local progress (optional; dry run unless `--execute`; asks you
to type RESET; never shows contents): `mambo learn-reset`. See
`docs/testing-isolation.md` for restore steps.

Lessons are AI-drafted and **not yet reviewed by a person**. See
`docs/lesson-authoring.md` and `docs/calculations.md`.

## 4b. Finance (introductory)

The **Finance** page has one teaching tool: an energy-settlement calculator (day-ahead
schedule × day-ahead price + deviation × real-time price) with **synthetic** inputs, and
lesson 8, *From scheduled energy to settlement*. It is not an invoice or any market's
settlement engine (ADR 0009). You can optionally import one **verified** modeled price
from Model Labs; it stays labeled *modeled*.

It also has a **basis-exposure calculator** and lesson 9, *Why a hedge at another location
leaves basis exposure*: a physical purchase at one location plus a simplified pay-fixed,
receive-floating hedge referencing another, split into fixed-price, location-basis, and
quantity-mismatch parts (ADR 0010). Two prices can be imported together from one verified
run; the fixed price is always synthetic.

A **time-shape calculator** and lesson 10, *Why matching total energy does not remove shape
exposure*, apply a flat MW hedge to synthetic intervals with varying use and prices, and
split the total into a fixed hedge part, an aggregate energy mismatch, and a time-shape
part (ADR 0011). Forwards, full swaps, futures, block products, options, PPAs, credit,
and collateral are not implemented.

The **Compliance** page is an educational **regulatory responsibility explorer**. It lists,
by activity, official sources that describe who is responsible for what (FERC, the ERO,
regional entities, DOE, the CPUC as a California example, CAISO, ERCOT, ISO-NE, and the
CFTC). Each entry is a *relevant source to investigate*, with its section, version, dates,
limitations, and review status (ADR 0012). Lessons 11, *Who sets the rules?*, and 12, *From
a requirement to evidence*, build on it. Nothing in the app decides whether a rule
applies, files anything, certifies, tracks deadlines, or stores evidence.

## 5. Launch

```powershell
.venvs/py314/Scripts/streamlit run src/mambo_explorer/app.py
```

Then open http://localhost:8501. Explore shows setup instructions until data has
been collected. The app never needs the key.

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
| [Calculations](docs/calculations.md) | Formulas, units, exclusions, and versions |
| [ERCOT NP6-345-CD contract](docs/datasets/ercot-np6-345-cd.md) | Direct ERCOT report: schema, units, time and DST fields |
| [ERCOT NP6-905-CD contract](docs/datasets/ercot-np6-905-cd.md) | Real-time hub price: product, price definition, 15-minute interval identity, finality |
| [ERCOT NP4-190-CD contract](docs/datasets/ercot-np4-190-cd.md) | Day-ahead hub price: report, location evidence, units, labels, finality |
| [EIA-930 generation contract](docs/datasets/eia930-fuel-type-data.md) | Net generation by energy source: route, codes, sign conventions, totals |
| [Timestamp display](docs/timestamp-display.md) | Inventory of every time value shown, its kind, and its display convention; browser regression steps |
| [mambo-power capability register](docs/capability-register.md) | What is documented vs. inspected vs. verified vs. exposed |
| [Refresh runbook](docs/refresh-runbook.md) | Refresh configuration, catch-up rules, recovery, optional scheduling |
| [Backlog](docs/backlog.md) | Recorded, unscheduled tasks (e.g. ERCOT DST validation) |
| [Lesson authoring](docs/lesson-authoring.md) | Lesson schema, review rules, and checks |
| [Dependency licenses](docs/dependency-licenses.md) | Generated license inventory of locked packages |
| [Progress](docs/progress.md) | Running log of work |
| [GitHub workflow](docs/github-workflow.md) | Branching, PRs, reviews |
| [Decisions](docs/decisions/) | Architecture Decision Records |

## License

No license has been chosen. Until one is, all rights are reserved by the
owner. See [docs/decisions/0001-license.md](docs/decisions/0001-license.md).
