"""Model sections of the market-mechanics lessons (Learn page).

Models run only when the learner presses the lesson's run button, never on a plain rerun.
Results are kept in session state as immutable, versioned records (see
modeling/cases.is_current) and are also saved to the local model-run store, never to the
observation store. Only current records reach the panels and exercises. A stale record
(changed scenario, inputs, or package) is hidden and must be run again.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer import routes
from mambo_explorer.model_exercises import _n
from mambo_explorer.modeling import adapter
from mambo_explorer.modeling import cases as mc
from mambo_explorer.modeling import opf_network as on
from mambo_explorer.opf_lab import md_dollars

STATE_KEY = "model_runs"
CUR = on.CURRENCY

UNITS = [
    {"Unit": "MW", "Used for": "Dispatch, line flows, ratings, capacities (power, a rate)"},
    {"Unit": "MWh", "Used for": "Energy over the 1-hour interval (MW × 1 h)"},
    {"Unit": "synthetic $/MWh", "Used for": "Offers, modeled prices, average change rates"},
    {"Unit": "synthetic $/h", "Used for": "Cost rate: Σ offer × MW"},
    {"Unit": "synthetic $", "Used for": "Interval cost: cost rate × 1 h"},
    {"Unit": "synthetic $/h per MW", "Used for": "Line-limit sensitivity (per MW of rating)"},
]


def _md(text: str) -> None:
    st.markdown(md_dollars(text))


def _caption(text: str) -> None:
    st.caption(md_dollars(text))


def current_records(keys: list[str]) -> tuple[dict, list[str]]:
    """(current records for these keys, keys whose stored record is stale)."""
    stored = st.session_state.get(STATE_KEY, {})
    current = {k: stored[k] for k in keys if mc.is_current(k, stored)}
    stale = [k for k in keys if k in stored and k not in current]
    return current, stale


def _run(keys: list[str], runs) -> None:
    before = dict(st.session_state.get(STATE_KEY, {}))
    after = mc.run_lesson_runs(keys, before)
    if runs is not None:
        for key in keys:
            if key in after and after[key] is not before.get(key):
                runs.save(after[key])
    st.session_state[STATE_KEY] = after


def _dispatch(record) -> dict[str, float]:
    if record.kind == "opf.dc":
        return {d["generator"]: d["dispatch_mw"] for d in record.dispatch}
    return {g["generator"]: g["output_mw"] for g in record.generators}


def _flows(record) -> dict[str, float]:
    if record.kind == "opf.dc":
        return {b["branch"]: b["flow_mw"] for b in record.branches}
    return {b["branch"]: b["flow_from_to_mw"] for b in record.branches}


def _pair(d: dict[str, float]) -> str:
    return f"{_n(d['G1'])} / {_n(d['G2'])}"


def _status(record) -> str:
    return {
        "optimal": "optimal",
        "infeasible": "infeasible",
        "ok": "solved, within limits",
        "ok_with_violations": "solved, limits exceeded",
        "failed": "FAILED (no results)",
    }[record.status]


# --- panels -------------------------------------------------------------------------------


def panel_pf_vs_opf(records: dict) -> None:
    st.subheader("Power flow versus optimal power flow (modeled)")
    keys = [k for k in ("pf-no-limit-cheapest", "pf-chosen", "congested") if k in records]
    if not keys:
        return
    who = {"pf.dispatch": "given (fixed input)", "opf.dc": "the optimizer"}
    rows, flows = [], []
    inputs = mc.run_inputs("congested")
    ratings = {"AB": inputs.rating_ab_bc, "BC": inputs.rating_ab_bc, "AC": inputs.rating_ac}
    for k in keys:
        r = records[k]
        solved = r.status not in ("failed", "infeasible")
        d = _dispatch(r) if solved else None
        rows.append(
            {
                "Run": mc.LESSON_RUNS[k].title,
                "Dispatch set by": who[r.kind],
                "G1 / G2 (MW)": _pair(d) if d else "—",
                "Cost rate ($/h)": _n(adapter.linear_cost_rate(mc.run_inputs(k), d)) if d else "—",
            }
        )
        if solved:
            f = _flows(r)
            flows.append(
                {
                    "Run": mc.LESSON_RUNS[k].title,
                    **{line: _n(f[line]) for line in ("AB", "BC", "AC")},
                    "Status": _status(r),
                }
            )
    st.table(rows, hide_index=True)
    _caption(
        "Cost rate = Σ offer × output, in synthetic $/h, computed the same way for every row. "
        "Only the optimizer's row is chosen to minimise it."
    )
    flows.insert(
        0,
        {"Run": "Rating (MW)", **{k: _n(v) for k, v in ratings.items()}, "Status": "—"},
    )
    st.table(flows, hide_index=True)
    _caption(
        "Line flows in MW, positive in the direction A → B, B → C, A → C. Power flow reports a "
        "flow above a rating as *limits exceeded*; it does not change the dispatch. The "
        "optimal power flow never chooses a dispatch that exceeds a rating."
    )
    _checks_table(records, keys)


def _checks_table(records: dict, keys: list[str]) -> None:
    rows = []
    for k in keys:
        r = records[k]
        consistency = [c for c in r.checks if c["kind"] != "limit"]
        limits = [c for c in r.checks if c["kind"] == "limit"]
        rows.append(
            {
                "Run": mc.LESSON_RUNS[k].title,
                "Checks passed": f"{sum(c['passed'] for c in consistency)} of {len(consistency)}",
                "Limits exceeded": ", ".join(
                    c["name"].replace(" within rating", "").replace(" within limits", "")
                    for c in limits
                    if not c["passed"]
                )
                or ("none" if limits else "enforced by the optimizer"),
            }
        )
    st.table(rows, hide_index=True)
    _caption(
        "Supported checks: power-flow runs check balance, the reference bus, flow = Δθ / x, and "
        "bus balance; limits are reported separately. Optimal-power-flow runs also check bounds, "
        "ratings, the recomputed cost, and the optimality (KKT) conditions."
    )


def panel_location_prices(records: dict) -> None:
    st.subheader("Why modeled prices differ by location (modeled)")
    steps = [k for k in ("uncongested", "congested", "relaxed") if k in records]
    rows, prices = [], []
    for k in steps:
        r = records[k]
        title = mc.LESSON_RUNS[k].title
        if r.status != "optimal":
            rows.append(
                {
                    "Step": title,
                    "G1 / G2 (MW)": _status(r),
                    "Binding line": "—",
                    "Cost rate ($/h)": "—",
                    "Cost, 1 h ($)": "—",
                }
            )
            continue
        bound = [b for b in r.branches if b["binding"]]
        rows.append(
            {
                "Step": title,
                "G1 / G2 (MW)": _pair(_dispatch(r)),
                "Binding line": ", ".join(
                    f"{b['branch']} ({_n(b['limit_sensitivity_per_mw'])} $/h per MW)" for b in bound
                )
                or "none",
                "Cost rate ($/h)": _n(r.cost_rate_per_h),
                "Cost, 1 h ($)": _n(r.interval_cost),
            }
        )
        p = {x["bus"]: x["price_per_mwh"] for x in r.prices}
        prices.append(
            {"Step": title, **{b: _n(p[b]) if p else "withheld" for b in ("A", "B", "C")}}
        )
    st.table(rows, hide_index=True)
    _caption(
        "Inputs for each step are in the table above. The sensitivity in brackets is the change "
        "in cost rate per +1 MW of that line's rating. Cost over the 1-hour interval = cost "
        "rate × 1 h; the numbers match only because the interval is one hour."
    )
    st.table(prices, hide_index=True)
    _caption(
        "Modeled nodal prices in synthetic $/MWh, shown only where this run's ±0.1 MW check "
        "verified them. They are not ERCOT or any ISO's prices."
    )
    extra = []
    for base, more in (("uncongested", "uncongested-plus10"), ("congested", "congested-plus10")):
        if base in records and more in records:
            a, b = records[base], records[more]
            if a.status == "optimal" and b.status == "optimal":
                da, db = _dispatch(a), _dispatch(b)
                extra.append(
                    {
                        "Case": mc.LESSON_RUNS[base].title,
                        "G1 change (MW)": _n(db["G1"] - da["G1"]),
                        "G2 change (MW)": _n(db["G2"] - da["G2"]),
                        "Cost rate change ($/h)": _n(b.cost_rate_per_h - a.cost_rate_per_h),
                    }
                )
    if extra:
        st.markdown("**What changes when demand at C rises by 10 MW** (two verified runs each):")
        st.table(extra, hide_index=True)


def panel_unverified_marginal(records: dict) -> None:
    st.subheader("When one marginal number is not verified (modeled)")
    keys = [
        k
        for k in (
            "breakpoint",
            "near-breakpoint",
            "ac-at-limit",
            "capacity-edge",
            "zero-demand",
            "equal",
            "infeasible",
        )
        if k in records
    ]
    rows, withheld = [], []
    for k in keys:
        r = records[k]
        title = mc.LESSON_RUNS[k].title
        unique = {True: "unique", False: "not unique", None: "—"}[r.dispatch_unique]
        rows.append(
            {
                "Case": title,
                "Run": _status(r),
                "Dispatch": unique if r.status == "optimal" else "—",
                "Prices": r.price_status,
            }
        )
        if r.price_status == "withheld":
            withheld.append((title, r))
    st.table(rows, hide_index=True)
    _caption(
        "Dispatch uniqueness and price verification are separate checks. A non-unique dispatch "
        "is still optimal. An infeasible run has no dispatch at all."
    )
    if withheld:
        from mambo_explorer.opf_lab import finite_change_table

        st.markdown(
            "**The price check's finite changes where prices were withheld.** For each of "
            "these runs: *A unique two-sided marginal price was not verified for this run.* "
            "Each direction is feasible or infeasible on its own."
        )
        for title, r in withheld:
            st.markdown(f"**{title}** (price gate: not passed)")
            finite_change_table(r.sensitivities)


PANELS = {
    "pf_vs_opf": panel_pf_vs_opf,
    "location_prices": panel_location_prices,
    "unverified_marginal": panel_unverified_marginal,
}


# --- section --------------------------------------------------------------------------------


def _inputs_table(keys: list[str]) -> None:
    rows = []
    for k in keys:
        i = mc.run_inputs(k)
        spec = mc.LESSON_RUNS[k]
        rows.append(
            {
                "Run": spec.title,
                "Offers G1 / G2 ($/MWh)": f"{_n(i.cost_g1)} / {_n(i.cost_g2)}",
                "Capacity G1 / G2 (MW)": f"{_n(i.cap_g1)} / {_n(i.cap_g2)}",
                "Demand C (MW)": _n(i.load_c),
                "AC rating (MW)": _n(i.rating_ac),
            }
        )
    st.table(rows, hide_index=True)
    ab_bc = {mc.run_inputs(k).rating_ab_bc for k in keys}
    pf = [k for k in keys if mc.LESSON_RUNS[k].kind == mc.PF]
    notes = [f"Lines AB and BC are rated {', '.join(_n(x) for x in sorted(ab_bc))} MW."]
    for k in pf:
        spec = mc.LESSON_RUNS[k]
        source = (
            f"G2's output from the verified run '{mc.LESSON_RUNS[spec.g2_from].title}'"
            if spec.g2_from
            else f"G2 fixed at {_n(spec.g2_mw)} MW"
        )
        notes.append(f"'{spec.title}' is a power flow with {source}; G1 covers the rest.")
    _caption(" ".join(notes))


def _provenance(records: dict, keys: list[str]) -> None:
    with st.expander("Model provenance for these runs"):
        st.table(
            [
                {
                    "Run": mc.LESSON_RUNS[k].title,
                    "Run id": records[k].run_id[-8:],
                    # Three short columns: fits a 375 px phone inside the expander.
                    "Status": f"{records[k].status} ({records[k].kind})",
                }
                for k in keys
                if k in records
            ],
            hide_index=True,
        )
        package = next((records[k].package for k in keys if k in records), {})
        _md(
            f"- Scenario `{on.SCENARIO_ID}` v{on.SCENARIO_VERSION} (synthetic; 1-hour interval)\n"
            f"- {package.get('name')} {package.get('version')}, commit "
            f"`{str(package.get('installed_commit'))[:12]}` (pinned "
            f"`{adapter.PINNED_COMMIT[:12]}`), highspy {package.get('highspy') or '—'}\n"
            f"- Adapter checks v{adapter.CHECKS_VERSION}; price check ±{adapter.PRICE_STEP_MW} MW "
            f"at every bus, tolerance {adapter.PRICE_FD_TOL} $/MWh\n"
            "- Full run ids are in the local model-run store (gitignored), not in observation "
            "storage."
        )


def _lab_links(lesson_id: str, keys: list[str]) -> None:
    lab_cases = []
    for k in keys:
        spec = mc.LESSON_RUNS[k]
        if spec.kind == mc.OPF and not spec.overrides and spec.case not in lab_cases:
            lab_cases.append(spec.case)
    if not lab_cases:
        return
    st.markdown("**Try these cases yourself in Model Labs** (economic-dispatch lab):")
    for case in lab_cases:
        if st.button(
            f"Open in Model Labs: {mc.LAB_CASES[case][0]}", key=f"lablink::{lesson_id}::{case}"
        ):
            st.session_state[routes.HANDOFF_LAB_CASE] = case
            routes.go("model-labs", "Model Labs")


def render_model_section(lesson, runs) -> dict:
    """Draw the lesson's model section; return the current records for its exercises."""
    meta = lesson.meta
    keys = list(meta["model_bindings"])
    st.header("Model runs for this lesson")
    _md(
        "Everything in this section is **modeled** on a **synthetic** three-bus network with "
        "**synthetic** offers, over a one-hour teaching interval. The model is lossless (DC "
        "approximation). It is a teaching model, not the model any real system operator runs, "
        "and its modeled prices are **not** ISO prices."
    )
    # In a lesson the ratings are fixed per run (see the run table), not learner controls.
    st.table(
        [{k: v for k, v in row.items() if k != "Rating"} for row in on.topology()], hide_index=True
    )
    _caption("G1 at bus A (reference bus), G2 at bus B, demand at bus C. Offers are linear.")
    _inputs_table(keys)

    if st.button("Run this lesson's model cases", key=f"lesson_run::{lesson.id}", type="primary"):
        with st.spinner("Running the model cases…"):
            _run(keys, runs)
    records, stale = current_records(keys)
    if stale:
        st.warning(
            "Stored results no longer match the scenario, inputs, or installed package, so they "
            "are hidden and no exercise uses them. Run the model cases again."
        )
    if len(records) < len(keys):
        st.info(
            "Press **Run this lesson's model cases** to compute the results. Models run only "
            "when you press the button."
        )
    if records:
        for panel in meta["model_panels"]:
            PANELS[panel](records)
        st.markdown("**Units used in this lesson**")
        st.table(UNITS, hide_index=True)
        _provenance(records, keys)
    _lab_links(lesson.id, keys)
    return records
