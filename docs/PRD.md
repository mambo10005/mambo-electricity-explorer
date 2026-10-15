# Product Requirements — mambo-electricity-explorer

**Status:** Stage 1. Requirements are sorted into three tiers:

- **Confirmed requirements (R-*)** come from the owner and are fixed unless the
  owner changes them.
- **Proposed design decisions (P-*)** are engineering proposals. They can be
  changed through an ADR without reopening the requirements.
- **Unresolved decisions (U-*)** are still open and need an owner decision or
  further research.

Implementation status for each feature is in [feature-matrix.md](feature-matrix.md).
Most of what this document describes is **not implemented yet**.

## 1. Product

**R-1.** A local-first, novice-oriented U.S. electricity learning and analysis
platform that uses actual observations and reproducible modeling.

### Problem

The U.S. electricity system has physical, market, financial, and regulatory
layers. Each one has its own vocabulary, institutions, and data. A newcomer
usually has to pick these up from scattered documents and has no way to tie a
concept to what actually happened on a real operating day. This platform
teaches each layer in order and grounds every lesson in observed data and
reproducible models, labeled so the learner always knows which is which.

### Users

**R-2.** Primary user: a newcomer to the U.S. electricity industry, learning and
analyzing on their own machine. Explanations assume no prior industry knowledge.

## 2. Learning sequence

**R-3.** Content and navigation follow this order:

1. Fundamentals
2. Individual regional markets
3. Settlement
4. Financial contracts and risk
5. Compliance
6. Integrated analysis

## 3. Required scope

| ID | Requirement |
|----|-------------|
| R-4 | Physical system: fuel, generation, transmission, distribution, storage, and demand. |
| R-5 | Weather, forecasting, reliability, planning, and interconnection. |
| R-6 | Industry participants and their institutional responsibilities. |
| R-7 | Markets: ERCOT, CAISO, PJM, MISO, SPP, NYISO, ISO-NE, and non-ISO markets. |
| R-8 | Replay of actual operating days. |
| R-9 | Modeling with mambo-power through a separately validated adapter. This repository does not modify mambo-power. |
| R-10 | Contracts: futures, forwards, swaps, options, PPAs, tolling, capacity, storage-service, and other long-term contracts. |
| R-11 | Hedging, basis and shape risk, settlement, credit, and collateral. |
| R-12 | Authorities: FERC, NERC and regional entities, DOE, state PUCs/PSCs, ISO/RTO rules, the CFTC, and other relevant authorities. |
| R-13 | Continuously updated data, plus lessons and rules that carry effective dates. |
| R-14 | Provenance, revisions, licensing, reproducibility, and limitations are recorded and shown to the user. |
| R-15 | Every displayed value is labeled **observed**, **derived**, **modeled**, or **synthetic**. Synthetic values are never presented as real. |

## 4. Infrastructure

| ID | Requirement |
|----|-------------|
| R-16 | No paid runtime services and no paid runtime AI. |
| R-17 | Collection, storage, and heavy modeling all run locally. |
| R-18 | Optional static public publication may come later. It is not authorized now. |
| R-19 | Claude development access is separate from runtime infrastructure. The running application does not depend on Claude or any other AI service. |

## 5. Application stack (owner-specified for Stage 1)

| ID | Requirement |
|----|-------------|
| R-20 | Python application using Streamlit. |
| R-21 | DuckDB + Parquet for observations; SQLite for metadata (both used from the data stages onward). |
| R-22 | Learning content written in Markdown/YAML. |
| R-23 | pytest and Ruff for verification. |
| R-24 | Navigation: Learn, Explore, Replay, Model Labs, Finance, Compliance, Sources, System Health. |

## 6. Data

| ID | Requirement |
|----|-------------|
| R-25 | EIA is the first planned connector. |
| R-26 | Regional operator and regulatory sources follow EIA. |
| R-27 | Each source needs its own access and redistribution review before ingestion. The review is recorded in [source-register.md](source-register.md). |
| R-28 | Credentials come from local environment variables, never from the repository. |
| R-29 | ERCOT is the first regional operator connector after EIA. |

## 7. Non-goals (current)

- Public deployment or hosting.
- Authentication or multi-user accounts.
- Trading, investment, or compliance advice. The platform is educational and
  analytical and does not replace professional or legal judgment.
- Storing data, databases, or private documents in Git.

## 8. Proposed design decisions

| ID | Proposal | Rationale |
|----|----------|-----------|
| P-1 | Store observations append-only, with source, retrieval time, and revision identifier on every record. | Satisfies R-13/R-14: revisions stay visible instead of being overwritten. |
| P-2 | Raw source responses go to Parquet under `DATA_DIR`. DuckDB queries the Parquet files in place. SQLite holds source, series, job, and model-run metadata. | Matches R-21 and keeps everything in local files with no server. |
| P-3 | One connector module per source, each with an offline test fixture. Tests never call live APIs. | Keeps the test suite reproducible and free (R-16). |
| P-4 | Lessons are Markdown files with YAML front matter (`effective_from`, `effective_to`, `sources`, `stage`). | Satisfies R-13's effective dating and R-22. |
| P-5 | The mambo-power adapter is a narrow interface with its own validation suite (comparison against reference cases) before any output is shown. Outputs are always labeled *modeled*. | R-9: validated separately, no changes to mambo-power. |
| P-6 | Feature status has one source of truth (`src/mambo_explorer/content/features.yaml`), and a test enforces that `feature-matrix.md` matches it. | Stops the status shown in the app from drifting away from the docs. |
| P-7 | Each source has its own environment variable (e.g. `EIA_API_KEY`) instead of one generic key. | Different sources have different credentials and terms. |
| P-8 | Static publication (R-18), if approved, would export only content whose sources allow redistribution. | Respects R-27. |

## 9. Unresolved decisions

| ID | Question | Blocks |
|----|----------|--------|
| U-1 | Application license (see [ADR 0001](decisions/0001-license.md)). | Any change in visibility or distribution |
| U-2 | Adapter scope beyond DC power flow (OPF, markets) and their acceptance criteria. Interface, location, and DC power-flow criteria are settled in ADR 0006. | MODEL-01 |
| U-3 | Order of regional operators after ERCOT (ERCOT itself is settled as R-29). | DATA-02 |
| U-4 | Redistribution terms for each source. | PUB-01, SRC-01 |
| U-5 | How far back history goes and the local storage budget. | STORE-01 |
| U-6 | How "continuously updated" collection is scheduled locally (manual, OS scheduler, or in-app). | HEALTH-01, DATA-* — proposed in ADR 0013: manual `mambo refresh` or an optional per-user Windows task; never in-app. Registering a task remains the owner's choice. |
| U-7 | Which balancing authorities and utilities count as "non-ISO markets" for R-7. | EXPLORE-01, LEARN-01 |
| U-8 | Who authors and reviews lessons and rules for accuracy, and the citation standard. | LEARN-01, COMP-01 |
| U-9 | Whether to test Python 3.12/3.13 and non-Windows platforms. Declared floor 3.11; tested on 3.11.16 and 3.14.2 on Windows only (ADR 0003). | — |

## 10. Traceability (implemented so far)

Requirements with at least partial implementation, plus where the evidence is.
Anything not listed is not implemented yet.

| Requirement | Feature(s) | Status | Evidence |
|---|---|---|---|
| R-1 learning and analysis with actual observations | DATA-01, DATA-05, EXPLORE-02, EXPLORE-04, LEARN-03 | partial: one BA; demand, forecast, and net generation by energy source | `tests/test_collect_storage.py`, `tests/test_learn_ui.py` |
| R-2 novice-oriented | LEARN-03, LEARN-04, FIN-03, FIN-04, FIN-05, COMP-03, EXPLORE-04 | partial: 13 lessons (agent-drafted, unreviewed) | `content/lessons/`, `docs/lesson-authoring.md` |
| R-3 learning sequence | LEARN-01, LEARN-03, LEARN-04, FIN-03, FIN-04, FIN-05, COMP-03 | partial: fundamentals (1–7), settlement (8), financial contracts and risk (9–10), compliance (11–12) | `tests/test_lessons.py` |
| R-4 physical system: demand and generation | LEARN-03, EXPLORE-04 | partial: demand (lessons 1–2) and net generation by energy source (lesson 13); no capacity, fuel, or plant-level data | lessons 1–2, 13; ADR 0014 |
| R-5 forecasting | LEARN-03 | partial: published day-ahead forecast accuracy (descriptive) | lesson 3, `docs/calculations.md` |
| R-7 ERCOT | DATA-01 | partial: EIA-930 `ERCO` only | source register |
| R-13 continuously updated data; effective-dated lessons | DATA-01, LEARN-03, COMP-02, OPS-01, HEALTH-01 | partial: bounded `mambo refresh` (manual, or an optional Windows task that is previewed but not registered), System Health freshness; lessons carry `effective_date` and `content_version`; responsibility records carry published/effective dates only when the source states them (point-in-time, not monitored) | `lessons.py` validation |
| R-14 provenance, revisions, licensing, reproducibility, limitations | STORE-01/02, CALC-01, LEARN-03 | partial: lineage, revisions, calculation references, per-lesson sources and limitations | ADR 0004, `docs/calculations.md` |
| R-15 data labels | EXPLORE-02, LEARN-03 | implemented for current pages: observed vs. synthetic | `tests/test_learn_ui.py`, `tests/guards.py` |
| R-16/R-17 local, free | all | implemented: local files only, no accounts | `progress.py`, `config.py` |
| R-20–R-24 stack and navigation | SHELL-01, STORE-01/02 | implemented | `tests/test_navigation.py` |
| R-25/R-27/R-28 EIA first, source review, credentials | DATA-01 | implemented for EIA-930 region-data; publication review pending | source register, `tests/test_eia_client.py` |
| R-9 modeling via a separately validated adapter | MODEL-01, MODEL-02, MODEL-03 | partial: DC power flow and linear-cost DC OPF on synthetic networks, independently benchmarked | ADR 0006, `docs/capability-register.md`, `tests/test_modeling.py` |
| R-11 settlement (introductory) | FIN-03 | partial: one teaching formula (DA schedule + RT deviation), synthetic inputs; no market-specific settlement, hedging, credit, or collateral | ADR 0009, `tests/test_settlement.py` |
| R-10/R-11 contracts and risk (introductory) | FIN-04, FIN-05 | partial: simplified hedge cash-flow exercises for locational basis, quantity mismatch, and time shape (flat block); no forwards, swaps, futures, options, PPAs, credit, or collateral | ADR 0010, `tests/test_basis.py` |
| R-12 authorities (introductory) | COMP-02, COMP-03 | partial: educational responsibility records for FERC, the ERO, regional entities, DOE, the CPUC (California example), CAISO, ERCOT, ISO-NE, and the CFTC, each tied to an official source section; no applicability determination, filings, or deadlines | ADR 0012, `tests/test_responsibilities.py` |
| R-29 ERCOT first operator | DATA-04, DATA-06, DATA-07, EXPLORE-03, EXPLORE-05, EXPLORE-06 | partial: NP6-345-CD actual load by weather zone, public download | ADR 0005, `tests/test_ercot.py`, source register |
