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
| pytest (dev group) | `>=9.1,<10` | 9.1.1 | MIT | Tests |
| ruff (dev group) | `==0.17.0` | 0.17.0 | MIT | Lint/format; pinned exactly so rule changes don't appear without notice |
| duckdb | `>=1.5.6,<2` | 1.5.6 | MIT (classifier; wheel ships no license file) | Observation queries (Stage 3) |
| pyarrow | `>=25.0.1,<26` | 25.0.1 | Apache-2.0 | Parquet writing (Stage 3) |
| hatchling (build) | `>=1.25` | — | MIT | Build backend, src layout |

Versions were verified by installing into a fresh venv on Python 3.14.2
(Windows 11) on 2026-10-11. Licenses come from the installed package metadata.

`duckdb` and `pyarrow` were deferred until first use and added in Stage 3
(STORE-01). A test now checks that every declared runtime dependency is imported
in `src/`.

SQLite comes from the Python standard library (`sqlite3`).

## Alternatives considered

- Declaring duckdb/pyarrow now: rejected because they would be unused, which
  is a speculative dependency.
- Exact pins for runtime dependencies: rejected. Ranges stay in
  `pyproject.toml`; exact versions live in `uv.lock` (ADR 0003).

## Consequences

- Each new dependency needs a row here with its license (ADR 0001 inbound review).
- Direct and transitive licenses are inventoried in `docs/dependency-licenses.md`
  (automated metadata; reviewed evidence only where stated). Dev tools moved to a
  dependency group in ADR 0003.
