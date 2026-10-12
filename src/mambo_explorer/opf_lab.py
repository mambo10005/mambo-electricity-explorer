"""Economic-dispatch (DC OPF) teaching lab on a SYNTHETIC three-bus network.

Shows only results that passed the adapter's checks (`modeling/adapter.run_dc_opf`). Modeled
nodal prices appear only when the per-run perturbation check verified them. A result is
hidden as soon as an input changes, and a failed or infeasible run never shows older numbers.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer.modeling import adapter
from mambo_explorer.modeling import cases as mc
from mambo_explorer.modeling import opf_network as on

CASES = mc.LAB_CASES  # shared with the lessons (modeling/cases.py)
LABELS = {
    # Widget labels keep a plain "$": a single "$" cannot open a LaTeX span, and Streamlit
    # copies the raw label into aria-label, so an escape would be read aloud as "\$".
    "cost_g1": "G1 offer at bus A (synthetic $/MWh)",
    "cost_g2": "G2 offer at bus B (synthetic $/MWh)",
    "cap_g1": "G1 capacity (MW)",
    "cap_g2": "G2 capacity (MW)",
    "load_c": "Demand at bus C (MW)",
    "rating_ac": "Line AC rating (MW)",
    "rating_ab_bc": "Lines AB and BC rating (MW)",
}
STATUS = {
    "optimal": "Optimal dispatch found, and every check passed.",
    "infeasible": "Infeasible.",
    "failed": "The run failed. No results are shown.",
}


def apply_case(key: str | None = None) -> None:
    """Set the sliders to a preset. As the selector's callback it runs before the rerun;
    a Learn link calls it before any widget is drawn. Either way the sliders can be set."""
    key = key or st.session_state["opf_case"]
    st.session_state["opf_case"] = key
    values = mc.case_inputs(key)
    for name in on.BOUNDS:
        st.session_state[f"opf_{name}"] = float(getattr(values, name))


def _inputs() -> on.OpfInputs:
    st.selectbox(
        "Start from a teaching case",
        list(CASES),
        format_func=lambda k: CASES[k][0],
        key="opf_case",
        on_change=apply_case,
    )
    values = {}
    for name, (low, high, default, step) in on.BOUNDS.items():
        values[name] = float(
            st.slider(
                LABELS[name],
                low,
                high,
                st.session_state.get(f"opf_{name}", default),
                step,
                key=f"opf_{name}",
            )
        )
    return on.OpfInputs(**values)


def md_dollars(text: str) -> str:
    """Escape every "$" so Streamlit markdown shows it literally instead of starting LaTeX."""
    return text.replace("$", "\\$")


def _money(x: float) -> str:
    return f"{x:,.2f}"


def _show(record: adapter.OpfRunRecord) -> None:
    alert = {"optimal": st.success, "infeasible": st.error, "failed": st.error}[record.status]
    alert(STATUS[record.status] + (f" {record.message}" if record.message else ""))
    st.caption(
        f"Run `{record.run_id}` · scenario {record.scenario_id} v{record.scenario_version} · "
        f"{record.package.get('name')} {record.package.get('version')} (commit "
        f"{str(record.package.get('installed_commit'))[:12]}) · solver {record.solver} "
        f"(highspy {record.package.get('highspy')}) · status {record.solver_status}"
    )
    if not record.solved:
        return

    st.header("Modeled dispatch")
    st.caption(
        "Data label: **modeled**, from synthetic offers. Energy is dispatch × the "
        "1-hour teaching interval."
    )
    st.table(
        [
            {
                # Five short columns: fits a 375 px phone without sideways scrolling.
                "Generator": f"{d['generator']} at {d['bus']}",
                "Offer ($/MWh)": d["offer_per_mwh"],
                "Dispatch (MW)": round(d["dispatch_mw"], 3),
                "Energy, 1 h (MWh)": round(d["energy_mwh"], 3),
                "At capacity": "yes" if d["at_capacity"] else "no",
            }
            for d in record.dispatch
        ],
        hide_index=True,
    )
    if record.dispatch_unique is False:
        st.info(record.dispatch_note)

    st.header("Cost")
    # "$" is escaped: Streamlit markdown treats a pair of "$" as a LaTeX math span, which
    # swallowed the units here (found in the browser check).
    st.markdown(
        md_dollars(
            f"- **Cost rate:** {_money(record.cost_rate_per_h)} synthetic $/h "
            "(Σ offer [$/MWh] × dispatch [MW]).\n"
            f"- **Cost over the 1-hour teaching interval:** {_money(record.interval_cost)} "
            "synthetic $ (cost rate × 1 h). The numbers match only because the interval is "
            "exactly one hour."
        )
    )

    st.header("Modeled line flows and binding limits")
    st.table(
        [
            {
                "Line": b["branch"],
                "From → to": f"{b['from_bus']} → {b['to_bus']}",
                "Flow (MW)": round(b["flow_mw"], 3),
                "Rating (MW)": b["rating_mw"],
                "Binding": "yes" if b["binding"] else "no",
                "Cost change per +1 MW rating ($/h)": round(b["limit_sensitivity_per_mw"], 3)
                if b["binding"]
                else "—",
            }
            for b in record.branches
        ],
        hide_index=True,
    )

    st.header("Modeled nodal prices")
    if record.price_status == "verified":
        st.caption(
            "**Modeled** marginal cost of serving 1 more MWh at each bus in this synthetic "
            "network. These are not ERCOT or any ISO's prices. This run's prices were checked "
            "by re-solving with ±0.1 MW of demand at each bus."
        )
        st.table(
            [
                {
                    "Bus": p["bus"],
                    "Modeled price ($/MWh)": round(p["price_per_mwh"], 4),
                    "Energy part": round(p["energy_per_mwh"], 4),
                    "Congestion part": round(p["congestion_per_mwh"], 4),
                }
                for p in record.prices
            ],
            hide_index=True,
        )
    else:
        st.warning(record.price_note or "Prices are not available for this run.")
        st.table(
            [
                {
                    "Bus": s["bus"],
                    "+0.1 MW demand ($/MWh)": "infeasible"
                    if s["up_per_mwh"] is None
                    else round(s["up_per_mwh"], 4),
                    "−0.1 MW demand ($/MWh)": "infeasible"
                    if s["down_per_mwh"] is None
                    else round(s["down_per_mwh"], 4),
                }
                for s in record.sensitivities
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


def render_opf_lab(runs) -> None:
    st.markdown(
        "**Power flow** works out the flows for a dispatch you choose. **Optimal power flow** "
        "chooses the dispatch itself: the cheapest one that meets demand without exceeding "
        "any generator capacity or line rating.\n\n"
        "This model is lossless (DC approximation). The offers are **synthetic** assumptions, "
        "the network is **synthetic**, and any modeled nodal prices are **not** actual ISO "
        "prices. One run covers an exactly **one-hour** teaching interval."
    )
    st.header("The synthetic network")
    st.table(on.topology(), hide_index=True)
    st.markdown(
        "G1 at bus A (reference bus) · G2 at bus B · demand at bus C. Offers are "
        "linear: cost rate = offer × MW."
    )

    st.header("Inputs")
    inputs = _inputs()
    try:
        fingerprint = inputs.validate().fingerprint()
    except on.InputError as exc:
        st.error(f"Invalid input: {exc}")
        return

    if st.button("Find the cheapest dispatch", key="opf_run", type="primary"):
        record = adapter.run_dc_opf(inputs)
        if runs is not None:
            runs.save(record)
        st.session_state["opf_last_run"] = record

    record = st.session_state.get("opf_last_run")
    st.header("Result")
    if record is None:
        st.info("Choose a case or set the inputs, then press **Find the cheapest dispatch**.")
    elif record.input_fingerprint != fingerprint:
        st.info(
            "The inputs changed since the last run, so its results are hidden. Run it "
            "again for the current inputs."
        )
    else:
        _show(record)

    st.header("What this model leaves out")
    st.markdown(
        "\n".join(
            f"- {x}"
            for x in [
                "Losses, voltages, reactive power, and AC physics (DC approximation).",
                "Unit commitment: start-up costs, minimum run times, and on/off decisions.",
                "Bids from demand: demand is fixed and is never shed automatically.",
                "Time: one hour, with no ramping or storage.",
                "Real offers, real networks, and settlement. Nothing here is calibrated "
                "to a market.",
            ]
        )
    )
    if runs is not None:
        with st.expander("Saved economic-dispatch runs on this computer"):
            recent = runs.recent(10, kind="opf.dc")
            if recent:
                st.table(
                    [
                        {
                            "Run": r.run_id[-8:],  # short id: fits a phone-width expander
                            "Status": r.status,
                            "Prices": r.price_status,
                            "Cost ($/h)": None
                            if r.cost_rate_per_h is None
                            else round(r.cost_rate_per_h, 2),
                        }
                        for r in recent
                    ],
                    hide_index=True,
                )
            else:
                st.markdown("No saved runs yet.")
