# Feature Matrix

Status key: `planned` · `in-progress` · `done` · `dropped`

The source of truth is `src/mambo_explorer/content/features.yaml`.
`tests/test_feature_status.py` fails if this table and that file disagree on
IDs or statuses. Only EXPLORE-02 is a page (`ui: true` in the YAML), so Explore is
the only section allowed to show charts. Done backend features (DATA-01, STORE-01/02)
do not unlock charts on Sources or System Health.

| ID | Feature | Section | Status | Notes |
|----|---------|---------|--------|-------|
| DOCS-01 | Product documents (PRD, architecture, source register) | platform | done | Stage 1 |
| SHELL-01 | Application shell and navigation | platform | done | Stage 1; no data on any page |
| SHELL-02 | Home page with status and data labels | platform | done | Stage 1 |
| QA-01 | Local quality workflow | platform | done | Stage 2: uv lock, `scripts/check.ps1`, Python 3.11 + 3.14 |
| LEARN-01 | Lesson content following the learning sequence | learn | planned | U-8 |
| LEARN-02 | Effective-dated lessons and rules | learn | planned | PRD P-4 |
| DATA-01 | EIA connector (EIA-930 ERCOT demand and forecast) | sources | done | Live-verified 2026-10-11 (metadata, collection, repeat ingest); one BA, two metrics |
| DATA-02 | Regional operator connectors | sources | planned | ERCOT first (R-29) |
| DATA-03 | Regulatory source connectors | sources | planned | |
| SRC-01 | Source register with provenance and licensing review | sources | planned | Doc register exists; in-app view not built |
| STORE-01 | DuckDB/Parquet observation store | system-health | done | Stage 3: append-only revisions, latest view (ADR 0004) |
| STORE-02 | SQLite metadata store | system-health | done | Stage 3: run catalog, recoverable commit (ADR 0004) |
| HEALTH-01 | Collection, freshness, and storage status | system-health | planned | CLI `status`/`storage`/`validate` exist; no UI page yet. U-6 |
| EXPLORE-01 | Observation explorer across regions | explore | planned | U-7 |
| EXPLORE-02 | ERCOT actual demand vs. published day-ahead forecast | explore | done | Stage 3; browser-checked with synthetic and live data |
| REPLAY-01 | Actual operating-day replay | replay | planned | |
| MODEL-01 | Validated mambo-power adapter | model-labs | planned | U-2 |
| FIN-01 | Financial and long-term contract library | finance | planned | |
| FIN-02 | Hedging, basis/shape risk, settlement, credit, collateral | finance | planned | |
| COMP-01 | Regulatory authorities and effective-dated rules | compliance | planned | U-8 |
| PUB-01 | Optional static public publication | platform | planned | Not authorized; U-1, U-4 |
