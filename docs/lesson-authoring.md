# Lesson authoring

Lessons live in `src/mambo_explorer/content/lessons/NN-slug.md`. Each one is Markdown
with YAML front matter. `lessons.load_lessons()` validates every lesson on load (and
in `tests/test_lessons.py`), so an invalid lesson fails the quality gate instead of
reaching the app.

## Front matter

| Field | Rule |
|---|---|
| `lesson_id` | lowercase-hyphen slug, unique |
| `title`, `order` | display title; integer ordering |
| `sequence_stage` | a key from `content/learning-sequence.yaml` |
| `prerequisites` | existing lesson ids; no cycles |
| `objectives` | non-empty list ("You will be able to…") |
| `content_version` | semantic version. Bump the **major** version when a definition or a calculation's meaning changes, the **minor** for new material, the **patch** for wording. |
| `effective_date` | date the described source definitions were checked, or `null` if not applicable |
| `authored_by`, `authored_at` | who wrote it and when. AI-drafted content says so (e.g. `Claude (AI agent)`). |
| `review_status` | `unreviewed` or `human-reviewed` |
| `reviewed_by`, `reviewed_at` | both `null` when unreviewed. When `human-reviewed`, a named person who is not the author and not an AI agent, plus a date. |
| `sources` | `id`, `title`, `https` `url`, `accessed` date, for every source-derived statement |
| `dataset_bindings` | `dataset`, `route`, `entity`, `metrics` for lessons that show observations |
| `calculation_ids` | from `power_energy`, `series_summary`, `coverage`, `forecast_error`, `dc_power_flow`, `dc_opf` |
| `data_panels` | from `power_energy_example`, `demand_series`, `forecast_comparison`, `coverage` |
| `exercises` | `exercise_id`, `kind` (`data`, `concept`, or `model`), `generator` (from `exercises.GENERATORS`, or `model_exercises.GENERATORS` for `model`), and `calculation_id` (one the lesson declares). Data exercises require a dataset binding. A model exercise's required runs (`model_exercises.REQUIRES`) must all be in `model_bindings`. |
| `model_bindings` | *optional* (default `[]`): keys of `modeling/cases.LESSON_RUNS`. A power-flow run that takes G2 from another run needs that run bound too. |
| `model_panels` | *optional* (default `[]`): from `pf_vs_opf`, `location_prices`, `unverified_marginal`; requires `model_bindings` |
| `glossary_terms` | terms defined in `content/glossary.yaml` |
| `limitations` | non-empty list, shown at the end of the lesson |
| `implementation_status` | `implemented` or `draft` |

## Body

The body must have `## Beginner` and then `## Technical detail`. The app shows the
beginner section by default and the technical section behind a toggle.

## Rules

1. **Creation is not review.** Never set `human-reviewed` unless a named person
   actually reviewed that `content_version`. Validation rejects AI reviewers, a
   reviewer who is also the author, and missing reviewer fields.
2. **Quote the source, don't extend it.** Definitions must match the cited pages.
   Put any interpretation in the technical section and label it as such.
3. **Never hardcode current data.** Specific period labels, row counts, and missing
   blocks belong in data panels and exercises, which are computed from the selected
   snapshot. A test rejects label-like strings and the current row counts in lesson
   text.
4. **Synthetic numbers are labeled** ("SYNTHETIC EXAMPLE") and never appear in a
   chart of observations.
5. **Respect unresolved semantics.** Do not describe hours as local times or
   operating days, or as interval starts or ends, while
   `eia/dataset.INTERVAL_CONVENTION` is `None`.
6. **No causal claims** (weather, customer sectors) unless the lesson binds data
   that supports them.
7. **Model lessons quote no results.** Dispatch, costs, prices, and sensitivities
   appear only in panels and exercises computed from current, verified runs. A test
   rejects the benchmark numbers in lesson prose. Model lessons cite no external
   source (`sources: []`) and must not describe how any real operator or ISO works.
8. **Escape nothing by hand.** The Learn page escapes `$` in lesson text, objectives,
   limitations, glossary, questions, and explanations. Exercise options are radio
   labels: keep at most one `$` in each, and no backslash.
9. New calculations go in `calculations.py` with tests and an entry in
   `docs/calculations.md`. New exercise generators go in `exercises.py`, and they
   compute answers with those same calculations.

## Checking a change

```powershell
pwsh -File scripts/check.ps1 -Python 3.11
pwsh -File scripts/check.ps1 -Python 3.14
.venvs/py314/Scripts/streamlit run src/mambo_explorer/app.py   # open Learn
```
