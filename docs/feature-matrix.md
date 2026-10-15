# Feature Matrix

Status key: `planned` · `in-progress` · `done` · `dropped`

The source of truth is `src/mambo_explorer/content/features.yaml`.
`tests/test_feature_status.py` fails if this table and that file disagree on
IDs or statuses. Only EXPLORE-02, EXPLORE-03, LEARN-03, LEARN-04, MODEL-02, and MODEL-03 are pages (`ui: true`
in the YAML), so Explore, Learn, and Model Labs are the only sections allowed to show charts. Done backend features (DATA-01, STORE-01/02)
do not unlock charts on Sources or System Health.

| ID | Feature | Section | Status | Notes |
|----|---------|---------|--------|-------|
| DOCS-01 | Product documents (PRD, architecture, source register) | platform | done | Stage 1 |
| SHELL-01 | Application shell and navigation | platform | done | Stage 1; no data on any page |
| SHELL-02 | Home page with status and data labels | platform | done | Stage 1 |
| QA-01 | Local quality workflow | platform | done | Stage 2: uv lock, `scripts/check.ps1`, Python 3.11 + 3.14 |
| QA-02 | Theme contrast for buttons (light and dark) with automated checks | platform | done | Stage 9: `.streamlit/config.toml`; measured ratios in `docs/accessibility.md`; not a WCAG claim (BL-6) |
| QA-03 | Human-review package for lessons and glossary (review itself pending) | platform | done | Stage 9: `docs/review/human-review-checklist.md`; BL-3 stays open |
| LEARN-01 | Lesson content following the learning sequence | learn | planned | 7 fundamentals lessons exist (LEARN-03, LEARN-04); stages 2–6 not written. U-8 |
| LEARN-02 | Effective-dated lessons and rules | learn | planned | PRD P-4; lessons carry `effective_date`, but rules are not built |
| LEARN-03 | Beginner lessons on demand and forecasts (4 lessons, exercises, local progress) | learn | done | Stage 4; agent-drafted, not human-reviewed |
| LEARN-04 | Market-mechanics lessons backed by verified model runs (3 lessons, model exercises) | learn | done | Stage 8: power flow vs. dispatch, modeled nodal prices, unverified marginal numbers; synthetic network; agent-drafted, not human-reviewed |
| CALC-01 | Shared calculation services (power/energy, summary, coverage, forecast error) | platform | done | Stage 4; docs/calculations.md |
| DATA-01 | EIA connector (EIA-930 ERCOT demand and forecast) | sources | done | Live-verified 2026-10-11 (metadata, collection, repeat ingest); one BA, two metrics |
| DATA-02 | Regional operator connectors | sources | planned | ERCOT started (DATA-04); other operators planned |
| DATA-04 | ERCOT direct connector: NP6-345-CD actual load by weather zone | sources | done | Stage 5; public download, live-verified 2026-10-11 (ADR 0005) |
| DATA-03 | Regulatory source connectors | sources | planned | |
| SRC-01 | Source register with provenance and licensing review | sources | planned | Doc register exists; in-app view not built |
| STORE-01 | DuckDB/Parquet observation store | system-health | done | Stage 3: append-only revisions, latest view (ADR 0004) |
| STORE-02 | SQLite metadata store | system-health | done | Stage 3: run catalog, recoverable commit (ADR 0004) |
| HEALTH-01 | Collection, freshness, and storage status | system-health | planned | CLI `status`/`storage`/`validate` exist; no UI page yet. U-6 |
| EXPLORE-01 | Observation explorer across regions | explore | planned | U-7 |
| EXPLORE-02 | ERCOT actual demand vs. published day-ahead forecast | explore | done | Stage 3; browser-checked with synthetic and live data |
| EXPLORE-03 | ERCOT direct actual load by weather zone (separate from EIA) | explore | done | Stage 5; no EIA join |
| REPLAY-01 | Actual operating-day replay | replay | planned | |
| MODEL-01 | Validated mambo-power adapter | model-labs | in-progress | DC power flow (ADR 0006) and linear-cost DC OPF (ADR 0007) verified; the rest inspected, not verified |
| MODEL-02 | DC power flow teaching lab (synthetic 3-bus network) | model-labs | done | Stage 6; capability register |
| MODEL-03 | Economic-dispatch lab: independently verified DC OPF (synthetic 3-bus) | model-labs | done | Stage 7; prices shown only when verified per run |
| FIN-01 | Financial and long-term contract library | finance | planned | |
| FIN-02 | Hedging, basis/shape risk, settlement, credit, collateral | finance | planned | |
| COMP-01 | Regulatory authorities and effective-dated rules | compliance | planned | U-8 |
| PUB-01 | Optional static public publication | platform | planned | Not authorized; U-1, U-4 |
