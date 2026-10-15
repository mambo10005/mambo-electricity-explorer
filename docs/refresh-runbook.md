# Local refresh: configuration and operational runbook

Stage 15, ADR 0013. Everything runs on this computer. Nothing is real-time: data is as
current as your last successful refresh and the sources' own publication schedules.

## Commands (from the repository root)

```powershell
.venvs\py314\Scripts\mambo.exe refresh --dry-run              # plan + budgets; sends nothing
.venvs\py314\Scripts\mambo.exe refresh                        # enabled sources, one after another
.venvs\py314\Scripts\mambo.exe refresh --source ercot         # explicit selection (repeatable)
.venvs\py314\Scripts\mambo.exe refresh --config D:\mambo\plan.yaml
.venvs\py314\Scripts\mambo.exe refresh --dry-run --source eia --source eia-generation  # combined EIA budget preview
.venvs\py314\Scripts\mambo.exe health                         # read-only status as JSON
.venvs\py314\Scripts\mambo.exe validate --source eia          # storage check (read-only by default)
```

- **Exit codes:**
  - 0: complete, nothing to do, or a dry run;
  - 3: partial (at least one source succeeded and at least one failed);
  - 2: every source failed, the configuration is invalid, or another refresh holds the
    lock.
- **Credentials:** EIA needs `EIA_API_KEY` in the environment or the gitignored `.env`.
  ERCOT needs no credential. A missing key fails only the EIA part.

## Configuration

The packaged plan is `src/mambo_explorer/content/refresh.yaml`. To change it, copy it
**outside the repository** (or to a gitignored path). Then pass `--config <file>`, or set
`MAMBO_REFRESH_CONFIG=<file>` so that the CLI and the System Health page both use it.

| Setting | EIA default | ERCOT default | Bound | Meaning |
|---|---|---|---|---|
| `enabled` | true | true | — | include the source when `--source` is not given |
| `publication_cadence` | text | text | — | what the source says about publishing (from the source register) |
| `collection_interval_hours` | 24 | 24 | 1–744 | how often you intend to refresh (used only to flag missed collections) |
| `window_days` / `window_documents` | 3 days | 3 documents | ≤ 31 days / ≤ 7 | first refresh into an empty store |
| `revision_lookback_days` / `_documents` | 3 days | 1 document | days + window ≤ 31 / ≤ 3 | already-collected data requested again to detect revisions or reposts |
| `max_catchup_days` / `_documents` | 14 days | 7 documents | ≤ 31 incl. lookback / ≤ 7 | most new data one refresh requests after a gap |
| `request_budget` | 12 | 12 | ≤ 50 / ≥ 1 + max docs | requests per refresh, including retries |
| `freshness_threshold_hours` | 48 | 48 | 1–1440 | System Health's fresh/stale boundary |
| `logs.retention_days`, `logs.max_files` | 30, 200 | | 1–365, 1–10,000 | pruning of `<data>/refresh/logs/refresh-*.json` |

Keys that look like credentials (`api_key`, `token`, `password`, …) are rejected.

**ERCOT day-ahead price dataset (`ercot-dam-spp`, Stage 19).** ERCOT settings shape
(window 2, lookback 1, catch-up cap 3 documents, budget 6), **disabled by default** and
optional in plan files. Each document is about 190 KB and holds every settlement point;
only HB_NORTH is stored. Planning counts DeliveryDates; the newest expected is tomorrow
(the DAM posts the day before). A successful refresh never makes a price final (Protocols:
final at 1000 on the second Business Day; not computed).

**Shared host limits (`hosts`).** `hosts: {ercot.com: {max_requests_per_refresh: 18}}`
caps requests to one host across all its datasets in one refresh (load 12 + prices 6 by
default). A later dataset that would exceed the cap is skipped with a `host-budget`
finding, and a dataset budget larger than its host cap is rejected. Dry runs show
`host_requests_budgeted`.

**Generation dataset (`eia-generation`, Stage 16).** A third section with the same
settings as `eia` (window, lookback, catch-up cap, budget, threshold), **disabled by
default**. A plan file without the section is valid and treats it as disabled. Enable it
deliberately (`enabled: true`) or select it explicitly (`--source eia-generation`). Its
budget is separate from the demand budget; both are EIA API requests, and the refresh
output shows the combined figure as `eia_api_requests_budgeted` so you can see it before
a run. Its collection success, coverage, and health come from its own store: a successful
demand refresh never implies generation was refreshed.

## What a refresh does

1. Takes the refresh lock `<data>/refresh/.refresh.lock`. If it already exists, the
   refresh stops. A lock left by a crash must be removed by you, after you check that no
   refresh is running.
2. Plans each selected source from **committed runs only**:
   - **EIA.** Continues from the day after the last committed UTC day, plus
     `revision_lookback_days`. With more than `max_catchup_days` new days, it requests the
     newest ones and names the skipped days. Request those yourself with
     `mambo collect --start … --end …`, at most 31 days at a time.
   - **ERCOT.** Counts OperDays by calendar label (no time-zone conversion). It requests
     new documents plus `revision_lookback_documents`, capped at `max_catchup_documents`.
     Days older than ERCOT's public list (about 31 days) are reported as outside available
     history: not available through the public report listing this app uses (ERCOT
     may offer them another way). Within the list, use
     `mambo collect --source ercot --publish-date YYYY-MM-DD`.
3. Runs the sources one at a time, each with its own budget, using the existing
   collectors. A failure in one is recorded and the next still runs. Earlier committed
   runs are never touched.
4. Writes a redacted JSON log and prunes old logs.

**Findings in the plan:**
- `never-collected`
- `missed-collection`: no successful run within two intervals, judged from run times
  only
- `missing-observations`: absent rows, reported and never filled
- `source-unavailable`: the last attempt failed or was interrupted
- `outside-available-history`
- `beyond-catch-up-limit`
- `revision-lookback`
- `no-new-period-expected`

An absent row is not proof of a missed job.

## Recovering from problems

| Symptom | What to do |
|---|---|
| "another refresh is running" | Check Task Manager for a running `mambo`. If none is running, delete `<data>/refresh/.refresh.lock`. |
| A source shows an interrupted run | `mambo validate --source <s>` reports it. `--mark-interrupted` marks it abandoned, and `--quarantine-orphans` moves unregistered files to `quarantine/`. Nothing is deleted. |
| `WriterLockError` for one source | A `mambo collect` for that source is running, or its `.writer.lock` is stale. Check, then delete that lock. |
| Partial result (exit 3) | Read the per-source error in the output or the log; the other source's data is intact. |

## Optional Windows scheduling (not registered by default)

```powershell
pwsh -File scripts/refresh-task.ps1                     # Preview (default): prints XML, registers nothing
pwsh -File scripts/refresh-task.ps1 -Action Register    # registers \mambo-electricity-explorer\refresh
pwsh -File scripts/refresh-task.ps1 -Action Inspect     # state, last result, next run
pwsh -File scripts/refresh-task.ps1 -Action Disable
pwsh -File scripts/refresh-task.ps1 -Action Remove
```

Options: `-At HH:mm` (default 07:15, daily), `-Python 3.11|3.14`, `-TimeLimitMinutes`
(5–120, default 30), `-NoCatchUpStart`, and `-Replace` (with Register).

**Task settings:**
- runs as the current user, only while you are logged on (no stored password, so the
  script never asks for one);
- least privilege, never SYSTEM or highest;
- no overlapping instances (IgnoreNew); stopped after the time limit;
- starts only when a network is available;
- never wakes the computer; power settings are untouched (battery behavior keeps Task
  Scheduler's defaults).

**Missed starts:** if the computer was off, asleep, or you were logged off at 07:15, the
task runs once as soon as possible afterwards. Pass `-NoCatchUpStart` to skip missed
starts instead. A refresh happens only when the computer and network are available under
these settings.

**Manual equivalent** of the scheduled command, from the repository root:
`.venvs\py314\Scripts\mambo.exe refresh`.

The task XML contains your user name and local paths. Do not commit an export of it.
