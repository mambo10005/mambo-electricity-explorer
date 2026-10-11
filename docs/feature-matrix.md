# Feature Matrix

Status key: `planned` · `in-progress` · `done` · `dropped`

The source of truth is `src/mambo_explorer/content/features.yaml`.
`tests/test_feature_status.py` fails if this table and that file disagree on
IDs or statuses.

| ID | Feature | Section | Status | Notes |
|----|---------|---------|--------|-------|
| DOCS-01 | Product documents (PRD, architecture, source register) | platform | done | Stage 1 |
| SHELL-01 | Application shell and navigation | platform | done | Stage 1; no data on any page |
| SHELL-02 | Home page with status and data labels | platform | done | Stage 1 |
| QA-01 | Local quality workflow | platform | done | Stage 2: uv lock, `scripts/check.ps1`, Python 3.11 + 3.14 |
| LEARN-01 | Lesson content following the learning sequence | learn | planned | U-8 |
| LEARN-02 | Effective-dated lessons and rules | learn | planned | PRD P-4 |
| DATA-01 | EIA connector | sources | planned | Next milestone; EIA terms reviewed |
| DATA-02 | Regional operator connectors | sources | planned | ERCOT first (R-29) |
| DATA-03 | Regulatory source connectors | sources | planned | |
| SRC-01 | Source register with provenance and licensing review | sources | planned | Doc register exists; in-app view not built |
| STORE-01 | DuckDB/Parquet observation store | system-health | planned | U-5 |
| STORE-02 | SQLite metadata store | system-health | planned | |
| HEALTH-01 | Collection, freshness, and storage status | system-health | planned | U-6 |
| EXPLORE-01 | Observation explorer across regions | explore | planned | U-7 |
| REPLAY-01 | Actual operating-day replay | replay | planned | |
| MODEL-01 | Validated mambo-power adapter | model-labs | planned | U-2 |
| FIN-01 | Financial and long-term contract library | finance | planned | |
| FIN-02 | Hedging, basis/shape risk, settlement, credit, collateral | finance | planned | |
| COMP-01 | Regulatory authorities and effective-dated rules | compliance | planned | U-8 |
| PUB-01 | Optional static public publication | platform | planned | Not authorized; U-1, U-4 |
