"""Finance page. Implemented: the introductory energy-settlement calculator (FIN-03) and
a simplified fixed-price hedge / basis-exposure cash-flow calculator (FIN-04), and a
flat-block hedge / time-shape cash-flow calculator (FIN-05). Contracts,
forwards, swaps, futures, options, PPAs, credit, and collateral are not implemented."""

from __future__ import annotations

import streamlit as st

from mambo_explorer import routes
from mambo_explorer.catalog import features
from mambo_explorer.config import ConfigError, load_settings
from mambo_explorer.modeling.runs import RunStore
from mambo_explorer.navigation import section_by_key
from mambo_explorer.settlement_ui import render_calculator


def render_finance() -> None:
    section = section_by_key("finance")
    st.title(section.title)
    st.markdown(
        "Three teaching tools are implemented here, all with **synthetic** inputs: an "
        "**introductory energy-settlement calculator**, a **basis-exposure calculator** for a "
        "simplified fixed-price financial hedge, and a **time-shape calculator** for a flat-block "
        "hedge over several intervals. None is a market settlement engine, an invoice, a "
        "contract valuation, or a model of any ISO's rules. Futures, forwards, options, full "
        "swaps, block products, PPAs, credit, and collateral are **not implemented**."
    )
    try:
        runs = RunStore(load_settings().data_dir)
    except ConfigError as exc:
        st.error(f"Unsafe data directory configuration: {exc}. Model runs cannot be listed.")
        runs = None
    st.header("Energy-settlement calculator")
    render_calculator("finance", runs)
    if st.button("Open the lesson: From scheduled energy to settlement", key="finance_lesson"):
        st.session_state[routes.HANDOFF_LESSON] = "energy-settlement"
        routes.go("learn", "Learn")
    st.header("Basis exposure with a simplified fixed-price hedge")
    from mambo_explorer.basis_ui import render_basis_calculator

    render_basis_calculator("finance_basis", runs)
    if st.button(
        "Open the lesson: Why a hedge at another location leaves basis exposure",
        key="finance_basis_lesson",
    ):
        st.session_state[routes.HANDOFF_LESSON] = "basis-exposure"
        routes.go("learn", "Learn")
    st.header("Time-shape exposure under a flat-block hedge")
    from mambo_explorer.shape_ui import render_shape_calculator

    render_shape_calculator("finance_shape")
    if st.button(
        "Open the lesson: Why matching total energy does not remove shape exposure",
        key="finance_shape_lesson",
    ):
        st.session_state[routes.HANDOFF_LESSON] = "shape-exposure"
        routes.go("learn", "Learn")
    st.header("Status of Finance features")
    st.table(
        [
            {"ID": f["id"], "Feature": f["name"], "Status": f["status"]}
            for f in features()
            if f["section"] == "finance"
        ],
        hide_index=True,
    )
