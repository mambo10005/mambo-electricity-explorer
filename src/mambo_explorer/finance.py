"""Finance page. Only the introductory energy-settlement calculator (FIN-03) is
implemented; contracts, hedging, derivatives, credit, and collateral are not."""

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
        "One teaching tool is implemented here: an **introductory energy-settlement "
        "calculator** with **synthetic** inputs. It is not a market settlement engine, not an "
        "invoice, and not a model of any ISO's rules. Futures, forwards, options, swaps, PPAs, "
        "hedging, credit, and collateral are **not implemented**."
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
    st.header("Status of Finance features")
    st.table(
        [
            {"ID": f["id"], "Feature": f["name"], "Status": f["status"]}
            for f in features()
            if f["section"] == "finance"
        ],
        hide_index=True,
    )
