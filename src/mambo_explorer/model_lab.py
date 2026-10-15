"""Model Labs page: a DC power flow teaching lab on a SYNTHETIC three-bus network.

Results are labeled *modeled*, never observed. A result is shown only while it matches
the current inputs. Changing any input hides it until the model is run again, and a
failed run shows the failure, never an older success.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer.config import ConfigError, load_settings
from mambo_explorer.modeling import adapter
from mambo_explorer.modeling import teaching_network as tn
from mambo_explorer.modeling.runs import RunStore
from mambo_explorer.navigation import section_by_key

STATUS_TEXT = {
    "ok": "Solved. Every check passed.",
    "ok_with_violations": "Solved, but limits are exceeded (see checks). DC power flow does "
    "not enforce limits; it reports what the flows would be.",
    "failed": "The run failed. No results are shown.",
}

OMISSIONS = [
    "Losses, voltage magnitudes, and reactive power (DC power flow ignores them).",
    "Line limits: flows are computed, not limited. Overloads are reported, not prevented.",
    "Costs, prices, and markets: G2's output is set by you, not chosen by economics.",
    "Time: one snapshot, with no ramping, storage, or hours.",
    "Any real grid: this network is synthetic and is not ERCOT or any utility's system.",
]


def _inputs_form() -> tn.Inputs:
    lo = {k: v[0] for k, v in tn.BOUNDS.items()}
    hi = {k: v[1] for k, v in tn.BOUNDS.items()}
    default = {k: v[2] for k, v in tn.BOUNDS.items()}
    step = {k: v[3] for k, v in tn.BOUNDS.items()}
    g2 = st.slider(
        "G2 output at bus B (MW)",
        lo["g2_mw"],
        hi["g2_mw"],
        default["g2_mw"],
        step["g2_mw"],
        key="lab_g2",
    )
    load = st.slider(
        "Demand at bus C (MW)",
        lo["load_c_mw"],
        hi["load_c_mw"],
        default["load_c_mw"],
        step["load_c_mw"],
        key="lab_load",
    )
    x_ac = st.slider(
        "Line AC reactance (per unit, 100 MVA base)",
        lo["x_ac_pu"],
        hi["x_ac_pu"],
        default["x_ac_pu"],
        step["x_ac_pu"],
        key="lab_x_ac",
    )
    in_service = st.toggle("Line AC in service", value=True, key="lab_ac_in")
    return tn.Inputs(
        g2_mw=float(g2), load_c_mw=float(load), x_ac_pu=float(x_ac), ac_in_service=in_service
    )


def _show(record: adapter.RunRecord) -> None:
    (st.success if record.status == "ok" else st.warning if record.solved else st.error)(
        f"{STATUS_TEXT[record.status]}" + (f" {record.message}" if record.message else "")
    )
    st.caption(
        f"Run `{record.run_id}` · scenario {record.scenario_id} v{record.scenario_version} · "
        f"{record.package.get('name')} {record.package.get('version')} "
        f"(commit {str(record.package.get('installed_commit'))[:12]}) · solver {record.solver} · "
        f"scipy {record.package.get('scipy')}"
    )
    if not record.solved:
        return
    st.header("Modeled branch flows")
    st.caption(
        "Data label: **modeled**. These come from the model and the inputs above, not "
        "from measurements. Positive flow means from → to."
    )
    st.table(
        [
            {
                "Branch": b["branch"],
                "From → to": f"{b['from_bus']} → {b['to_bus']}",
                "Flow (MW)": round(b["flow_from_to_mw"], 3),
                "Loading (% of 100 MVA)": None
                if b["loading_pct"] is None
                else round(b["loading_pct"], 1),
            }
            for b in record.branches
        ],
        hide_index=True,
    )
    st.header("Modeled generation and bus angles")
    st.table(
        [
            {"Generator": g["generator"], "Bus": g["bus"], "Output (MW)": round(g["output_mw"], 3)}
            for g in record.generators
        ],
        hide_index=True,
    )
    st.table(
        [
            {
                "Bus": b["bus"],
                "Angle (degrees)": round(b["angle_deg"], 4),
                "Net injection (MW)": round(b["net_injection_mw"], 3),
            }
            for b in record.buses
        ],
        hide_index=True,
    )
    st.header("Checks")
    st.table(
        [
            {
                "Check": c["name"],
                "Type": c["kind"],
                "Result": "pass" if c["passed"] else "FAIL",
                "Detail": c["detail"],
            }
            for c in record.checks
        ],
        hide_index=True,
    )
    with st.expander("How these numbers are calculated"):
        st.markdown(
            "- Each line carries power in proportion to the **angle difference** across it, "
            "divided by its reactance: flow (MW) = (θ_from − θ_to) / x × 100 MVA.\n"
            "- Bus A is the reference (angle 0). G1 there supplies whatever demand the other "
            "generator does not cover: G1 = demand − G2.\n"
            "- With all three lines in, power sent from A to C splits between the direct line "
            "AC and the path A→B→C in inverse proportion to their reactances (x_AC versus "
            "0.1 + 0.1). G2's injection at B adds its own share on top (superposition). A lower "
            "x on AC pulls more flow onto AC.\n"
            "- The model solves these equations with mambo-power (`pf.solve_dc`). This app "
            "then checks the answer independently: generation equals demand, each bus "
            "balances, each flow matches its angle difference, and bus A's angle is 0."
        )


def render_model_lab() -> None:
    section = section_by_key("model-labs")
    st.title(section.title)
    st.markdown(
        "A **DC power flow** teaching lab. You set a generator, a demand, and one line. The "
        "model computes how power splits across the lines. The network is **synthetic** "
        "(three buses), and every result is **modeled**, not an observation of any real "
        "market or grid."
    )
    try:
        settings = load_settings()
        runs = RunStore(settings.data_dir)
    except ConfigError as exc:
        st.error(f"Unsafe data directory configuration: {exc}. Runs cannot be saved.")
        runs = None

    st.header("The synthetic network")
    st.markdown(
        "Three buses in a triangle, joined by lines AB, BC, and AC. Base 100 MVA; "
        "resistance and line charging are zero (DC approximation)."
    )
    st.table(tn.buses_table(), hide_index=True)
    st.table(tn.topology(), hide_index=True)

    st.header("Inputs")
    inputs = _inputs_form()
    try:
        inputs.validate()
        fingerprint = inputs.fingerprint()
    except tn.InputError as exc:
        st.error(f"Invalid input: {exc}")
        return

    if st.button("Run DC power flow", key="lab_run", type="primary"):
        record = adapter.run_dc_power_flow(inputs)
        if runs is not None:
            runs.save(record)
        st.session_state["lab_last_run"] = record

    record = st.session_state.get("lab_last_run")
    st.header("Result")
    if record is None:
        st.info("Set the inputs and press **Run DC power flow**. Nothing has been run yet.")
    elif record.input_fingerprint != fingerprint:
        st.info(
            "The inputs changed since the last run, so its results are hidden. "
            "Press **Run DC power flow** to compute results for the current inputs."
        )
    else:
        _show(record)

    st.header("What this model leaves out")
    st.markdown("\n".join(f"- {item}" for item in OMISSIONS))
    if runs is not None:
        with st.expander("Saved runs on this computer"):
            recent = runs.recent(10)
            if not recent:
                st.markdown("No saved runs yet.")
            else:
                st.table(
                    [
                        {
                            "Run": r.run_id,
                            "Status": r.status,
                            "G2 (MW)": r.inputs["g2_mw"],
                            "Demand C (MW)": r.inputs["load_c_mw"],
                            "x AC (pu)": r.inputs["x_ac_pu"],
                            "AC in service": r.inputs["ac_in_service"],
                        }
                        for r in recent
                    ],
                    hide_index=True,
                )
                st.caption(f"Stored in {runs.root} (local, gitignored).")
