# 0002 — Application stack and dependency versions

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

The owner specified Python, Streamlit, DuckDB + Parquet, SQLite,
Markdown/YAML content, pytest, and Ruff (PRD R-20 to R-23). Stage 1 builds
only the application shell, which uses none of the storage technologies yet.

## Decision

Direct dependencies are declared only once code uses them:

| Package | Constraint | Verified version | License | Used for |
|---------|-----------|------------------|---------|----------|
| streamlit | `>=1.65,<2` | 1.65.0 | Apache-2.0 | UI, `st.navigation`, `AppTest` |
| pyyaml | `>=6.0.3,<7` | 6.0.3 | MIT | Packaged YAML content |
| pytest (dev) | `>=9.1,<10` | 9.1.1 | MIT | Tests |
| ruff (dev) | `==0.17.0` | 0.17.0 | MIT | Lint/format; pinned exactly so rule changes don't appear without notice |
| hatchling (build) | `>=1.25` | — | MIT | Build backend, src layout |

Versions were verified by installing into a fresh venv on Python 3.14.2
(Windows 11) on 2026-10-11. Licenses come from the installed package metadata.

**Deferred:** `duckdb` and a direct `pyarrow` dependency are added in the
stage that first reads or writes observations (STORE-01). Streamlit already
pulls in pyarrow transitively. Nothing in this repository should depend on
that until it is declared.

SQLite comes from the Python standard library (`sqlite3`).

## Alternatives considered

- Declaring duckdb/pyarrow now: rejected because they would be unused, which
  is a speculative dependency.
- Exact pins for runtime dependencies: rejected for now. Upper bounds plus a
  recorded verified version are enough for a single-user local app. Revisit
  with a lock file in QA-01.

## Consequences

- Each new dependency needs a row here with its license (ADR 0001 inbound review).
- Transitive dependency licenses have not been audited yet. That belongs to QA-01.
