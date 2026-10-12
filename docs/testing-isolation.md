# Test and harness data isolation

**Rule:** nothing automated may read or write the developer's real data directory:
- `./data`, including learning progress, saved model runs, and observations;
- any `MAMBO_DATA_DIR` the developer uses.

## What happened (Stage 8, found in Stage 9)

A Stage 8 test called `monkeypatch.undo()` mid-test. That reverted its `MAMBO_DATA_DIR`
override, and the next AppTest rerun wrote a lesson-6 "viewed" mark into the real
`data/learn/progress.json`. The file and its `learn/` folder were created at 18:15:35
local time on 2026-10-11, the time of that test run, and its only entry matches what the
test does.

This is strong evidence that the entry came from the test. It does **not** prove the file
holds no legitimate activity, so the file has been left exactly as it is. The owner can
back it up and reset it with the optional command below.

## Safeguards (Stage 10)

| Layer | Where | What it does |
|---|---|---|
| Protected directories | `config.validate_data_dir`, `MAMBO_FORBIDDEN_DATA_DIRS` | Refuses a data directory that is a protected directory or inside one. Catches other casing (case-normalized compare), relative paths (resolved against the working directory), symlinks and Windows junctions (`resolve()`), and other aliases of existing folders such as 8.3 short names (`samefile`). |
| Test session | `tests/conftest.py` | Every test runs with a session temp `MAMBO_DATA_DIR`, `MAMBO_FORBIDDEN_DATA_DIRS=<repo>/data`, and a temp working directory (marked as its own repository root, because the home folder above the temp folder contains a `.git` folder). A test that deletes both variables still cannot reach `./data` or a repository `.env`. At the end, the real `./data` tree must be unchanged (paths and modification times, compared in memory). |
| Quality gate | `scripts/quality.py` | The pytest and smoke-server subprocesses get an explicit scratch data directory and the protection variable. A final check, **real data directory unchanged**, compares `data/` before and after the whole gate (in memory, names only on failure). |
| Browser harnesses | manual (below) | Servers are started with a scratch `MAMBO_DATA_DIR` **and** `MAMBO_FORBIDDEN_DATA_DIRS` pointing at the real `./data`. |
| Test style | `CLAUDE.md` | Never call `monkeypatch.undo()`; restore the one item you changed. |

Evidence: `tests/test_data_dir_isolation.py` uses a **fake** protected directory with a
sentinel file in a temp folder. It covers:
- missing configuration;
- relative paths and nested working directories;
- other casing (including a protected directory that does not exist yet);
- 8.3 short names and junctions;
- symlinks (skipped where Windows does not allow creating them);
- subprocess inheritance;
- the app pages refusing the directory;
- the gate's subprocess environment.

It never writes to the real `./data`. Mutation checks confirmed that a test fails when
the guard's casing normalization, its link and alias handling, or the session's
protection variable is removed. The working-directory and gate layers were not
mutation-tested.

## Starting a browser-check server safely

```powershell
$env:MAMBO_DATA_DIR = "<scratch folder>\data"
$env:MAMBO_FORBIDDEN_DATA_DIRS = "$PWD\data"
.venvs/py314/Scripts/python -m streamlit run src/mambo_explorer/app.py --server.port 8597 --server.headless true
```

Record the process ID and its child processes, and stop only those.

## Optional: back up and reset learning progress (not run by any stage)

```powershell
.venvs/py314/Scripts/mambo learn-reset                       # dry run: paths, size, time only
.venvs/py314/Scripts/mambo learn-reset --execute             # asks you to type RESET
.venvs/py314/Scripts/mambo learn-reset --execute --backup-dir D:\backups
```

With `--execute` it:
1. copies `progress.json` to a new, timestamped file in a folder outside any repository
   that would track it (default: `%LOCALAPPDATA%\mambo-electricity-explorer\progress-backups`),
   and refuses to overwrite an existing backup;
2. verifies the copy byte-for-byte (SHA-256) and checks that the original did not change;
3. only then removes the original.

It never prints the file's contents.

**Restore:** stop the app, then:

```powershell
Copy-Item -LiteralPath "<backup file>" -Destination "data\learn\progress.json"
```

`Copy-Item` will not overwrite an existing progress file without `-Force`. Decide which
file to keep first.
