"""Learn page: lesson list, lesson content, data panels, exercises, local progress.

Reads committed observations only (never collects). Lesson text stays readable when no
observations exist. Data panels then show collection instructions instead of charts, and
synthetic numbers never appear in actual-data charts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import streamlit as st

from mambo_explorer import (
    basis_exercises,
    model_exercises,
    routes,
    settlement_exercises,
    shape_exercises,
)
from mambo_explorer import calculations as calc
from mambo_explorer.config import ConfigError, load_settings
from mambo_explorer.eia import dataset as ds
from mambo_explorer.exercises import Unavailable, generate
from mambo_explorer.explore import SETUP_INSTRUCTIONS, STALE_AFTER
from mambo_explorer.lessons import Lesson, load_glossary, load_lessons
from mambo_explorer.modeling.runs import RunStore
from mambo_explorer.opf_lab import md_dollars
from mambo_explorer.progress import UNDERSTANDING, Progress
from mambo_explorer.storage import Store

STATE_HELP = (
    "**viewed**: you opened the lesson. **exercise completed**: you answered at least one "
    "exercise. **understanding demonstrated**: every exercise in the lesson was answered "
    "correctly on the first try. This is a self-check, not a certification."
)
REVIEW_TEXT = {
    "unreviewed": "Drafted by {author} on {authored}. Not yet reviewed by a person.",
    "human-reviewed": "Drafted by {author} on {authored}. Reviewed by {reviewer} on {reviewed}.",
}


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


# --- data context --------------------------------------------------------------------------


def _data_context(store: Store | None):
    """(observations, selection, last_run) for the chosen window, or Nones if no data."""
    if store is None:
        return None, None, None
    last = store.last_committed_run()
    if last is None:
        return None, None, None
    with store.query() as con:
        first, final = con.execute(
            "SELECT min(period), max(period) FROM latest WHERE entity = ?", [ds.ENTITY]
        ).fetchone()
    if first is None:
        return None, None, last
    first_day, last_day = ds.parse_period(first).date(), ds.parse_period(final).date()
    picked = st.date_input(
        "Observation window for this lesson (UTC days, by the source's period label)",
        value=(max(first_day, last_day - timedelta(days=6)), last_day),
        min_value=first_day,
        max_value=last_day,
        key="learn_window",
    )
    if not isinstance(picked, tuple) or len(picked) != 2:
        st.info("Select a start and an end day.")
        return None, None, last
    selection = calc.Selection(ds.ENTITY, f"{picked[0]}T00", f"{picked[1]}T23")
    return calc.load_observations(store, selection), selection, last


def _freshness(last: dict | None) -> None:
    if last is None:
        st.markdown("- **Observations:** none collected on this computer yet.")
        return
    finished = datetime.fromisoformat(last["finished_at"]).astimezone(UTC)
    st.markdown(
        f"- **Observations:** EIA-930 (`{ds.ROUTE}`), entity `{ds.ENTITY}`, unit as reported "
        f"(`{ds.EXPECTED_UNIT}`). Last successful local collection {finished:%Y-%m-%d %H:%M} "
        f"UTC (run `{last['run_id']}`). Publication time is not provided by the source."
    )
    if datetime.now(UTC) - finished > STALE_AFTER:
        st.warning(
            f"These observations may be stale: the last collection finished more than "
            f"{STALE_AFTER.total_seconds() / 3600:.0f} hours ago."
        )


def _no_data() -> None:
    st.info(
        "No observations have been collected on this computer, so this part of the lesson "
        "has no actual data to show. The lesson text above still applies. Collection runs "
        "from the command line, never from this page."
    )
    st.markdown(SETUP_INSTRUCTIONS)


def _table(rows: list[dict], caption: str) -> None:
    st.caption(caption)
    st.table(rows, hide_index=True)


# --- panels ----------------------------------------------------------------------------------


def panel_power_energy_example(obs, sel) -> None:
    st.subheader("Worked conversions (SYNTHETIC example numbers)")
    examples = [
        calc.power_energy(average_mw=250, hours=4),
        calc.power_energy(energy_mwh=48_000, hours=1),
        calc.power_energy(energy_mwh=48_000, hours=2),
    ]
    rows = []
    for r in examples:
        s = r.selection
        given = (
            f"{_fmt(s['average_mw'])} MW average"
            if s["average_mw"] is not None
            else f"{_fmt(s['energy_mwh'])} MWh"
        )
        result_key = "energy_mwh" if "energy_mwh" in r.values else "average_mw"
        rows.append(
            {
                "Given": given,
                "Duration": f"{_fmt(s['hours'])} h",
                "Result": f"{_fmt(r.values[result_key])} {r.unit}",
                "Formula": "energy = power × hours"
                if result_key == "energy_mwh"
                else "power = energy ÷ hours",
            }
        )
    _table(rows, "Synthetic numbers for practice, not observations. Calculation power_energy v1.")


def panel_demand_series(obs, sel) -> None:
    st.subheader("Actual demand in the selected window (observed)")
    if obs is None:
        _no_data()
        return
    summary = calc.series_summary(obs, sel, "D")
    if not summary.ok:
        st.warning(f"Summary unavailable: {summary.reason}")
        return
    v, unit = summary.values, ds.unit_label(summary.unit)
    _table(
        [
            {
                "Measure": "Highest value",
                "Value": f"{_fmt(v['max'])} {unit}",
                "Label (UTC)": v["max_period"],
            },
            {
                "Measure": "Lowest value",
                "Value": f"{_fmt(v['min'])} {unit}",
                "Label (UTC)": v["min_period"],
            },
            {
                "Measure": "Average of valid values",
                "Value": f"{_fmt(v['mean'])} {unit}",
                "Label (UTC)": "—",
            },
            {
                "Measure": "Range (highest − lowest)",
                "Value": f"{_fmt(v['range'])} {unit}",
                "Label (UTC)": "—",
            },
            {
                "Measure": "Coverage",
                "Value": f"{v['valid_values']} valid of {v['expected_labels']} hourly labels",
                "Label (UTC)": f"{v['absent_rows']} absent",
            },
        ],
        f"Calculation series_summary v{summary.formula_version} over {sel.start_period} to "
        f"{sel.end_period}. Values are in the source unit ({summary.unit}).",
    )
    rows = [o for o in obs if o.metric == "D"]
    st.caption(
        "Line chart of hourly actual demand by UTC period label. Gaps mean no valid value. "
        "The same numbers are in the table below the chart."
    )
    st.line_chart(
        [
            {"Period label (UTC)": ds.parse_period(o.period), "Actual demand (MWh)": o.value}
            for o in rows
        ],
        x="Period label (UTC)",
        color=["#1f77b4"],
    )
    with st.expander(f"Data table for this chart ({len(rows)} rows)"):
        st.table(
            [
                {
                    "Label (UTC)": o.period,
                    "Value": o.value_raw,
                    "Unit": o.unit,
                    "Revision": o.revision,
                }
                for o in rows
            ],
            hide_index=True,
        )


def panel_forecast_comparison(obs, sel) -> None:
    st.subheader("Actual vs. published day-ahead forecast (observed)")
    if obs is None:
        _no_data()
        return
    result = calc.forecast_error(obs, sel)
    if not result.ok:
        st.warning(f"Comparison unavailable: {result.reason}")
        return
    v, unit = result.values, ds.unit_label(result.unit)
    _table(
        [
            {"Measure": "Matched valid pairs (hours)", "Value": str(v["pairs"])},
            {"Measure": "Excluded hours", "Value": str(len(result.exclusions))},
            {
                "Measure": "Mean error (actual − forecast)",
                "Value": f"{_fmt(v['mean_error'])} {unit}",
            },
            {"Measure": "MAE", "Value": f"{_fmt(v['mae'])} {unit}"},
            {"Measure": "RMSE", "Value": f"{_fmt(v['rmse'])} {unit}"},
            {
                "Measure": "Hours above forecast (positive error)",
                "Value": str(v["under_forecast_hours"]),
            },
            {
                "Measure": "Hours below forecast (negative error)",
                "Value": str(v["over_forecast_hours"]),
            },
            {
                "Measure": "Largest miss",
                "Value": f"{_fmt(v['largest_abs_error'])} {unit} at "
                f"{v['largest_abs_error_period']}",
            },
        ],
        f"Calculation forecast_error v{result.formula_version}. The forecast is the latest "
        "value collected, not necessarily the forecast as first issued.",
    )
    st.caption(
        "Line chart of hourly error (actual − forecast) for matched hours, by UTC label. "
        "Above zero: demand above forecast. Below zero: demand below forecast. "
        "The pairs are listed in the table below."
    )
    st.line_chart(
        [
            {"Period label (UTC)": ds.parse_period(p["period"]), "Error (MWh)": p["error"]}
            for p in v["pair_errors"]
        ],
        x="Period label (UTC)",
        color=["#d95f02"],
    )
    with st.expander(f"Matched pairs ({v['pairs']} rows)"):
        st.table(
            [
                {
                    "Label (UTC)": p["period"],
                    "Actual": _fmt(p["actual"]),
                    "Forecast": _fmt(p["forecast"]),
                    "Error": _fmt(p["error"]),
                }
                for p in v["pair_errors"]
            ],
            hide_index=True,
        )
    with st.expander(f"Excluded hours ({len(result.exclusions)})"):
        if result.exclusions:
            st.table(result.exclusions, hide_index=True)
        else:
            st.markdown("None. Every label in the window had a valid actual and forecast.")


def panel_coverage(obs, sel) -> None:
    st.subheader("Coverage by series (observed)")
    if obs is None:
        _no_data()
        return
    # Measures as rows and one column per series: three columns stay readable on a phone.
    measures = [
        ("Expected hourly labels", "expected_labels"),
        ("Rows present", "present_rows"),
        ("Valid values (incl. zero)", "valid_values"),
        ("Zero values", "zero_values"),
        ("Null values", "null_values"),
        ("Non-numeric values", "non_numeric_values"),
        ("Absent rows", "absent_rows"),
    ]
    results = {metric: calc.coverage(obs, sel, metric).values for metric in ds.METRICS}
    rows = [
        {"Measure": name, **{ds.DISPLAY_NAMES[m]: results[m][field] for m in ds.METRICS}}
        for name, field in measures
    ]
    runs = []
    for metric in ds.METRICS:
        v = results[metric]
        runs += [
            {
                "Series": ds.DISPLAY_NAMES[metric],
                "First absent label (UTC)": a,
                "Last absent label (UTC)": b,
                "Labels": n,
            }
            for a, b, n in v["absent_runs"]
        ]
    _table(
        rows,
        f"Calculation coverage v1 over {sel.start_period} to {sel.end_period}. "
        "Zero values are real values and are counted as valid.",
    )
    st.markdown("**Absent runs**, listed by UTC source label with no cause implied:")
    if runs:
        st.table(runs, hide_index=True)
    else:
        st.markdown("No absent rows in this window.")


PANELS = {
    "power_energy_example": panel_power_energy_example,
    "demand_series": panel_demand_series,
    "forecast_comparison": panel_forecast_comparison,
    "coverage": panel_coverage,
}


# --- exercises -------------------------------------------------------------------------------


def _exercise(lesson: Lesson, spec: dict, exercise, progress: Progress | None) -> None:
    key = f"ex::{lesson.id}::{spec['exercise_id']}"
    if isinstance(exercise, Unavailable):
        # No answer from an earlier question is shown once its results are gone or failed.
        st.session_state.pop(f"{key}::result", None)
        st.info(f"Exercise unavailable: {exercise.reason}.")
        return
    shown = st.session_state.get(f"{key}::snapshot")
    if shown is not None and shown != exercise.snapshot_id:
        st.warning(
            "The selected window, the stored data, or the model results changed, so this "
            "exercise was regenerated from the new results."
        )
        st.session_state.pop(f"{key}::result", None)
    st.session_state[f"{key}::snapshot"] = exercise.snapshot_id
    with st.form(f"{key}::{exercise.snapshot_id}::form"):
        st.markdown(f"**{md_dollars(exercise.question)}**")
        choice = st.radio(
            "Your answer",
            exercise.options,
            index=None,
            key=f"{key}::{exercise.snapshot_id}::choice",
        )
        submitted = st.form_submit_button("Check answer")
    if submitted:
        if choice is None:
            st.warning("Choose an answer first.")
        else:
            correct = exercise.options.index(choice) == exercise.answer_index
            record = (
                progress.record_answer(
                    lesson.id,
                    spec["exercise_id"],
                    exercise.snapshot_id,
                    correct,
                    exercise.result_refs,
                )
                if progress
                else None
            )
            st.session_state[f"{key}::result"] = {
                "correct": correct,
                "attempts": record["attempts"] if record else 1,
            }
            # The status table at the top was drawn before this answer was recorded;
            # rerun so it reflects the new state. The result survives in session state.
            st.rerun()
    result = st.session_state.get(f"{key}::result")
    if result:
        (st.success if result["correct"] else st.error)(
            md_dollars(
                ("Correct. " if result["correct"] else "Not quite. ")
                + f"Answer: {exercise.options[exercise.answer_index]}"
            )
        )
        st.markdown(md_dollars(f"*Worked explanation:* {exercise.explanation}"))
        if exercise.result_refs:
            st.caption(
                "Computed from model run(s) "
                + ", ".join(f"`{ref}`" for ref in exercise.result_refs)
                + " (synthetic network, modeled results)."
            )
        if result["attempts"] > 1:
            st.caption(
                "Only the first attempt on a question counts toward 'understanding demonstrated'."
            )


# --- page ------------------------------------------------------------------------------------


def _go_to(lesson_id: str) -> None:
    """Button callback: runs before the rerun, so the lesson selector can still be set."""
    st.session_state["lesson_choice"] = lesson_id


def render_learn() -> None:
    st.title("Learn")
    st.markdown(
        "Beginner lessons that use real EIA observations collected on this computer, and "
        "lessons that use **modeled** results from a **synthetic** teaching network. Lessons "
        "are drafted by an AI agent and have **not yet been reviewed by a person**."
    )
    lessons = load_lessons()
    glossary = load_glossary()
    by_id = {lesson.id: lesson for lesson in lessons}

    try:
        settings = load_settings()
        store, progress = Store(settings.data_dir), Progress(settings.data_dir)
        runs = RunStore(settings.data_dir)
    except ConfigError as exc:
        st.error(
            f"Unsafe data directory configuration: {exc}. Lessons are shown without "
            "observations, saved progress, or saved model runs."
        )
        store = progress = runs = None

    ids = [lesson.id for lesson in lessons]
    handoff = st.session_state.pop(routes.HANDOFF_LESSON, None)
    if handoff in by_id:  # from a Model Labs link; validated against the lesson list
        st.session_state["lesson_choice"] = handoff
    if st.session_state.get("lesson_choice") not in by_id:
        # First render: honor a deep link (?lesson=...), else start with lesson 1.
        requested = st.query_params.get("lesson")
        st.session_state["lesson_choice"] = requested if requested in by_id else ids[0]

    if progress:
        # Mark before drawing the list, so the open lesson's label already reads 'viewed'.
        progress.mark_viewed(st.session_state["lesson_choice"])

    if progress:
        # Status lives in its own table so the selector's labels never change (a widget
        # whose option labels change between reruns can lose its selection).
        st.table(
            [
                {
                    "Lesson": f"{lesson.meta['order']}. {lesson.title}",
                    "Status": progress.lesson_state(
                        lesson.id, [e["exercise_id"] for e in lesson.meta["exercises"]]
                    ),
                    "Bookmarked": "yes" if progress.bookmarked(lesson.id) else "",
                }
                for lesson in lessons
            ],
            hide_index=True,
        )

    chosen = st.radio(
        "Open lesson",
        ids,
        format_func=lambda i: f"{by_id[i].meta['order']}. {by_id[i].title}",
        key="lesson_choice",
    )
    st.query_params["lesson"] = chosen
    lesson = by_id[chosen]
    meta = lesson.meta
    if progress:
        progress.mark_viewed(lesson.id)  # also covers a change made by a callback
    st.caption(STATE_HELP)

    st.header(lesson.title)
    st.caption(
        REVIEW_TEXT[meta["review_status"]].format(
            author=meta["authored_by"],
            authored=meta["authored_at"],
            reviewer=meta["reviewed_by"],
            reviewed=meta["reviewed_at"],
        )
        + f" Content version {meta['content_version']}"
        + (f"; definitions as of {meta['effective_date']}." if meta["effective_date"] else ".")
    )
    for prereq_id in meta["prerequisites"]:
        prereq = by_id[prereq_id]
        viewed = progress and progress.lesson_state(prereq_id, []) != "not started"
        if not viewed:
            st.warning(f"Suggested first: **{prereq.title}** (not viewed yet).")
        st.button(
            f"Go to prerequisite: {prereq.title}",
            key=f"prereq::{lesson.id}::{prereq_id}",
            on_click=_go_to,
            args=(prereq_id,),
        )
    if progress:
        marked = st.toggle(
            "Bookmark this lesson",
            value=progress.bookmarked(lesson.id),
            key=f"bookmark::{lesson.id}",
        )
        if marked != progress.bookmarked(lesson.id):
            progress.set_bookmark(lesson.id, marked)

    # "$" is escaped in every lesson text: a pair of "$" would render as LaTeX in Markdown.
    st.markdown(
        md_dollars("**You will be able to:**\n" + "\n".join(f"- {o}" for o in meta["objectives"]))
    )
    technical = st.toggle("Show technical detail", key="technical_detail")
    st.markdown(md_dollars(lesson.beginner))
    if technical:
        st.subheader("Technical detail")
        st.markdown(md_dollars(lesson.technical))

    obs = sel = last = None
    if meta["dataset_bindings"]:
        obs, sel, last = _data_context(store)
    for panel in meta["data_panels"]:
        PANELS[panel](obs, sel)

    records = {}
    if meta["model_bindings"]:
        from mambo_explorer.model_lessons import render_model_section

        records = render_model_section(lesson, runs)
    settlement_result = None
    if "energy_settlement" in meta["calculators"]:
        from mambo_explorer.settlement_ui import render_calculator

        st.header("Energy-settlement calculator (synthetic)")
        settlement_result = render_calculator(f"learn_{lesson.id}", runs)
    basis_result = None
    if "basis_exposure" in meta["calculators"]:
        from mambo_explorer.basis_ui import render_basis_calculator

        st.header("Basis-exposure calculator (synthetic)")
        basis_result = render_basis_calculator(f"learn_{lesson.id}", runs)
    shape_result = None
    if "time_shape" in meta["calculators"]:
        from mambo_explorer.shape_ui import render_shape_calculator

        st.header("Time-shape calculator (synthetic)")
        shape_result = render_shape_calculator(f"learn_{lesson.id}")

    st.subheader("Exercises")
    for spec in meta["exercises"]:
        if spec["kind"] == "model":
            exercise = model_exercises.generate(spec, records)
        elif spec["kind"] == "settlement":
            exercise = settlement_exercises.generate(spec, settlement_result)
        elif spec["kind"] == "basis":
            exercise = basis_exercises.generate(spec, basis_result)
        elif spec["kind"] == "shape":
            exercise = shape_exercises.generate(spec, shape_result)
        else:
            exercise = generate(spec, obs, sel)
        _exercise(lesson, spec, exercise, progress)
    if progress:
        state = progress.lesson_state(lesson.id, [e["exercise_id"] for e in meta["exercises"]])
        (st.success if state == UNDERSTANDING else st.caption)(f"Lesson status: {state}.")

    with st.expander("Glossary for this lesson"):
        st.markdown(
            md_dollars(
                "\n".join(
                    f"- **{t}**"
                    + (f" ({glossary[t]['expansion']})" if glossary[t].get("expansion") else "")
                    + f": {glossary[t]['definition']}"
                    for t in meta["glossary_terms"]
                )
            )
        )
    st.subheader("Sources and freshness")
    if meta["sources"]:
        st.markdown(
            "\n".join(
                f"- [{s['title']}]({s['url']}) (accessed {s['accessed']})" for s in meta["sources"]
            )
        )
    else:
        st.markdown(
            "No external source: every number in this lesson comes from the model runs listed "
            "under *Model provenance*. The formulation and its verification are documented in "
            "the project's calculations notes and ADR 0007."
        )
    if meta["dataset_bindings"]:
        _freshness(store.last_committed_run() if store else None)
    st.subheader("Limitations")
    st.markdown(md_dollars("\n".join(f"- {item}" for item in meta["limitations"])))
