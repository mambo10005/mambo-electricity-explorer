# Feature Matrix

Status key: `planned` · `in-progress` · `done` · `dropped`

The source of truth is `src/mambo_explorer/content/features.yaml`.
`tests/test_feature_status.py` fails if this table and that file disagree on
IDs or statuses. Only EXPLORE-02, EXPLORE-03, EXPLORE-04, EXPLORE-05, EXPLORE-06, LEARN-03, LEARN-04, MODEL-02, MODEL-03, FIN-03, FIN-04, FIN-05, COMP-02, and HEALTH-01 are pages (`ui: true`
in the YAML), so Explore, Learn, Model Labs, Finance, Compliance, and System Health are the only sections allowed to show data elements. Compliance shows none: its tables are source records, not data. Done backend features (DATA-01, STORE-01/02)
do not unlock charts on Sources or System Health.

| ID | Feature | Section | Status | Notes |
|----|---------|---------|--------|-------|
| DOCS-01 | Product documents (PRD, architecture, source register) | platform | done | Stage 1 |
| SHELL-01 | Application shell and navigation | platform | done | Stage 1; no data on any page |
| SHELL-02 | Home page with status and data labels | platform | done | Stage 1 |
| QA-01 | Local quality workflow | platform | done | Stage 2: uv lock, `scripts/check.ps1`, Python 3.11 + 3.14 |
| QA-02 | Theme contrast for buttons (light and dark) with automated checks | platform | done | Stage 9: `.streamlit/config.toml`; measured ratios in `docs/accessibility.md`; not a WCAG claim (BL-6) |
| QA-03 | Human-review package for lessons and glossary (review itself pending) | platform | done | Stage 9: `docs/review/human-review-checklist.md`; BL-3 stays open |
| QA-04 | Data-isolation safeguards (tests, gate, harnesses) and optional progress backup/reset | platform | done | Stage 10: `MAMBO_FORBIDDEN_DATA_DIRS`, `tests/conftest.py`, gate check; `mambo learn-reset` (never run); `docs/testing-isolation.md` |
| QA-05 | Keyboard focus indicator (focus-only CSS, measured in both themes) | platform | done | Stage 10: `focus.css`, ADR 0008; not a WCAG claim; screen reader untested (BL-6) |
| QA-06 | Timestamp display consistency: UTC labels on axes, tooltips, and tables regardless of browser time zone | platform | done | Stage 17: `timeview.py`, ADR 0015, `docs/timestamp-display.md`; source semantics unchanged |
| LEARN-01 | Lesson content following the learning sequence | learn | planned | 7 fundamentals lessons exist (LEARN-03, LEARN-04); stages 2–6 not written. U-8 |
| LEARN-02 | Effective-dated lessons and rules | learn | planned | PRD P-4; lessons carry `effective_date`, but rules are not built |
| LEARN-03 | Beginner lessons on demand and forecasts (4 lessons, exercises, local progress) | learn | done | Stage 4; agent-drafted, not human-reviewed |
| LEARN-04 | Market-mechanics lessons backed by verified model runs (3 lessons, model exercises) | learn | done | Stage 8: power flow vs. dispatch, modeled nodal prices, unverified marginal numbers; synthetic network; agent-drafted, not human-reviewed |
| CALC-01 | Shared calculation services (power/energy, summary, coverage, forecast error) | platform | done | Stage 4; docs/calculations.md |
| DATA-01 | EIA connector (EIA-930 ERCOT demand and forecast) | sources | done | Live-verified 2026-10-11 (metadata, collection, repeat ingest); one BA, two metrics |
| DATA-02 | Regional operator connectors | sources | planned | ERCOT started (DATA-04); other operators planned |
| DATA-04 | ERCOT direct connector: NP6-345-CD actual load by weather zone | sources | done | Stage 5; public download, live-verified 2026-10-11 (ADR 0005) |
| DATA-07 | ERCOT direct connector: NP6-905-CD real-time settlement point price at HB_NORTH (15-minute intervals, own store namespace) | sources | done | Stage 20: ADR 0017; opt-in; counts against the shared ercot.com cap (not raised) |
| DATA-06 | ERCOT direct connector: NP4-190-CD DAM settlement point price at HB_NORTH (one hub, own store namespace) | sources | done | Stage 19: ADR 0016; opt-in in refresh; shared ercot.com cap |
| DATA-05 | EIA connector: EIA-930 hourly net generation by energy source (ERCO), own store namespace | sources | done | Stage 16: route `fuel-type-data`, ADR 0014; disabled in the default refresh plan |
| DATA-03 | Regulatory source connectors | sources | planned | |
| SRC-01 | Source register with provenance and licensing review | sources | planned | Doc register exists; in-app view not built |
| STORE-01 | DuckDB/Parquet observation store | system-health | done | Stage 3: append-only revisions, latest view (ADR 0004) |
| STORE-02 | SQLite metadata store | system-health | done | Stage 3: run catalog, recoverable commit (ADR 0004) |
| HEALTH-01 | Collection, freshness, and storage status | system-health | done | Stage 15: System Health page (read-only; never collects) and `mambo health`; ADR 0013. U-6 |
| OPS-02 | Coverage-aware real-time price collection: document inventory, snapshot and coverage modes, bounded backfill, revision recheck, freshness vs completeness | system-health | done | Stage 21: ADR 0018; shared ercot.com cap unchanged (18); never claims complete history |
| OPS-01 | Bounded local refresh of existing collectors (plan, budgets, catch-up, logs) and optional Windows task scripts | system-health | done | Stage 15: `mambo refresh`, `content/refresh.yaml`, `scripts/refresh-task.ps1` (preview by default; no task registered) |
| EXPLORE-01 | Observation explorer across regions | explore | planned | U-7 |
| EXPLORE-02 | ERCOT actual demand vs. published day-ahead forecast | explore | done | Stage 3; browser-checked with synthetic and live data |
| EXPLORE-03 | ERCOT direct actual load by weather zone (separate from EIA) | explore | done | Stage 5; no EIA join |
| EXPLORE-06 | Real-time price view at HB_NORTH: source-label chart, interval viewer, table, coverage, provenance, and lesson 15 | explore | done | Stage 20; ERCOT interval labels, no UTC; no day-ahead comparison; finality not determined |
| EXPLORE-05 | Day-ahead price view at HB_NORTH: source-label chart, table, coverage, publication and revision provenance, and lesson 14 | explore | done | Stage 19; ERCOT labels, no UTC; finality not determined; no join with EIA |
| EXPLORE-04 | Net generation by energy source: signed chart, category coverage, totals with completeness rules, and lesson 13 | explore | done | Stage 16; no pie chart, no system total, shares withheld when misleading; lesson agent-authored, unreviewed |
| REPLAY-01 | Actual operating-day replay | replay | planned | |
| MODEL-01 | Validated mambo-power adapter | model-labs | in-progress | DC power flow (ADR 0006) and linear-cost DC OPF (ADR 0007) verified; the rest inspected, not verified |
| MODEL-02 | DC power flow teaching lab (synthetic 3-bus network) | model-labs | done | Stage 6; capability register |
| MODEL-03 | Economic-dispatch lab: independently verified DC OPF (synthetic 3-bus) | model-labs | done | Stage 7; prices shown only when verified per run |
| FIN-01 | Financial and long-term contract library | finance | planned | |
| FIN-02 | Hedging, basis/shape risk, settlement, credit, collateral | finance | planned | |
| FIN-03 | Introductory energy-settlement calculator and lesson (synthetic, teaching formula) | finance | done | Stage 11: `settlement.py`, Finance page, lesson 8; ISO-NE two-settlement concept only; not an invoice or market engine (ADR 0009). Futures, options, PPAs, hedging, credit, and collateral remain planned |
| FIN-04 | Basis exposure with a simplified fixed-price hedge: cash-flow calculator and lesson (synthetic) | finance | done | Stage 12: `basis.py`, Finance page, lesson 9; a simplified hedge cash-flow exercise only, not a forward, swap, future, or PPA implementation (ADR 0010) |
| FIN-05 | Time-shape exposure under a flat-block hedge: multi-interval cash-flow calculator and lesson (synthetic) | finance | done | Stage 13: `shape.py`, Finance page, lesson 10; a teaching cash-flow exercise only, not an exchange block product, forward curve, or valuation (ADR 0011) |
| COMP-01 | Regulatory authorities and effective-dated rules | compliance | planned | U-8; an operational, maintained rules database is not built |
| COMP-02 | Regulatory responsibility explorer: source-backed educational records by activity (no applicability determination) | compliance | done | Stage 14: `responsibilities.yaml` + `responsibilities.py`, ADR 0012; agent-authored, unreviewed |
| COMP-03 | Introductory compliance lessons: who sets the rules; from a requirement to evidence | compliance | done | Stage 14: lessons 11 and 12; agent-authored, unreviewed (BL-3) |
| COMP-04 | Operational compliance: applicability assessment, filings, certification, deadlines, evidence management | compliance | planned | Out of scope for Stage 14 |
| PUB-01 | Optional static public publication | platform | planned | Not authorized; U-1, U-4 |
