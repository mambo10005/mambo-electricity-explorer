# 0004 — EIA collection, credential handling, and observation storage

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

Stage 3 collects the first real observations: EIA-930 hourly demand (`D`) and
day-ahead demand forecast (`DF`) for ERCOT (`ERCO`). The design has to satisfy:
- PRD R-13/R-14: revisions, provenance, reproducibility
- PRD R-15: labels
- PRD R-16/R-17: local and free
- the EIA terms review: key in the URL, rate guidance, attribution

## Decision

**Connector** (`src/mambo_explorer/eia/`):
- Standard-library HTTP (`urllib`) behind an injectable transport. No new HTTP
  dependency, and offline tests use a fake transport.
- Every request is bounded:
  - explicit timeout (30 s)
  - at most 3 retries, with exponential backoff, only for network errors, 429,
    and 5xx
  - a per-invocation request budget that counts retries
- Pagination uses `offset`/`length` with the sort fixed to (period, respondent,
  type). The run fails, instead of storing partial data, on:
  - a short page before `total`
  - `total` changing between pages
  - out-of-order or duplicate rows
  - rows outside the requested entity, metrics, or window
  - more rows than the plan allows
- An HTTP 200 is not trusted on its own: JSON shape, `error` payloads, and
  every row's fields are validated.
- **Credentials:**
  - The key exists only in `EIAClient._key` and the URL built inside `_get()`.
  - Every error, failure note, and archived body passes through `redact()`,
    which removes the raw, percent-encoded, and plus-encoded key, any
    `api_key=` query value, and any JSON `"api_key"` field.
  - Exceptions are raised with `from None`, so unredacted bodies are never
    chained.
  - `repr()` omits the key.

**Plan bounds:**
- The default is 7 completed UTC days plus a 2-day revision lookback.
- A run may cover at most 31 days, lookback included. Future days are rejected.
- `--dry-run` prints the scope and request budget. It needs no key and writes
  nothing.

**Raw archive:**
- Each page is stored as JSON after redaction.
- If redaction changed anything (for example, EIA echoing the key in
  `request.params`), the file is recorded as **sanitized**, so it is not
  byte-identical to the response.
- The sha256 is of the stored bytes.

**Observations:**
- One row per source value, with:
  - source, dataset, route, frequency, entity, metric
  - original `period`
  - `value_raw` (string as received) and the parsed `value`
  - the source `unit`
  - `quality_flags` (`missing`, `non_numeric`, `negative`): flagged, never
    imputed, clipped, or dropped
  - `revision`, `retrieved_at_utc`
  - `publication_time_utc`, always null because the source doesn't provide it
  - request window, run id, archive path, and checksum
- `interval_start_utc`/`interval_end_utc` stay null, because hour-ending is
  documented for EIA-930 but not for the API field (source register).
  `dataset.INTERVAL_CONVENTION` is the single switch.

**Identity and revisions:**
- Identity = (source, dataset, route, frequency, entity, metric, period).
- A re-collected value that matches the latest `value_raw` and `unit` is
  counted as unchanged and not written, so repeated ingestion is idempotent.
- A changed value is appended as `revision + 1`, keeping its own run and
  archive lineage.
- `latest` is a DuckDB view: highest revision per identity.

**Storage and commit sequence** (`storage.py`): Parquet partitioned
`entity=/metric=/run=`, a SQLite catalog (`runs`, `run_files`), and DuckDB for
reads. The sequence is:
1. take the writer lock (`O_EXCL` lock file)
2. insert the run row as `started`
3. write files atomically (temp file, fsync, `os.replace`)
4. in **one SQLite transaction**, register every file with its sha256 and mark
   the run `committed`

Readers only see files registered by committed runs. So a crash between steps
3 and 4 leaves invisible orphans and a `started` run.

**Recovery:**
- `mambo validate` reports missing files, checksum mismatches, orphans,
  interrupted runs, and a held lock.
- It changes nothing unless asked: `--mark-interrupted` and
  `--quarantine-orphans` (a move, never a delete).
- A stale lock is never broken automatically. The message names the file to
  delete after checking that no collection is running.

**Configuration:**
- `MAMBO_DATA_DIR` defaults to `./data` (gitignored). Paths are rejected if
  they are:
  - inside the repository but outside `data/`
  - an ancestor of the repository
  - under a publication-style directory (`public`, `publish`, `site`, `www`,
    `static`, `dist`, `docs`)
- The CLI loads `./.env` for `EIA_API_KEY`/`MAMBO_DATA_DIR` only, never
  overrides the environment, and refuses a `.env` that git does not ignore.
- Tests and app startup never need a key.

**DuckDB sessions:** UTC time zone (ICU is statically linked in 1.5.6) and
`autoinstall_known_extensions = false`, so queries never download extensions.

## Alternatives considered

- **`requests`/`httpx`:** their exceptions embed the full URL, query string
  included, which would put the key in error messages. The standard library
  plus explicit redaction is smaller and easier to audit.
- **Upserting a single table:** this loses revision lineage (R-14).
- **SQLite for observations too:** the owner specified DuckDB + Parquet (R-21).

## Consequences

- Live behaviour was verified on 2026-10-11 (source register): field names,
  missing hours as absent rows, and no key echo for this route. The period
  convention is still unstated by the API, so intervals stay underived.
- History beyond a run's lookback is not re-checked for revisions.
