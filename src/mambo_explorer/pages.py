"""Page renderers. Only Explore shows data (see explore.py); every other section is a
"Not implemented" page with no charts, numbers, or model output."""

import streamlit as st

from mambo_explorer.catalog import data_labels, features, learning_sequence
from mambo_explorer.compliance import render_compliance
from mambo_explorer.explore import render_explore
from mambo_explorer.finance import render_finance
from mambo_explorer.learn import render_learn
from mambo_explorer.model_lab import render_model_lab
from mambo_explorer.navigation import section_by_key

NOT_IMPLEMENTED = "Not implemented"


def render_home() -> None:
    st.title("mambo electricity explorer")
    st.markdown(
        "A local-first platform for learning and analyzing the U.S. electricity system "
        "from **actual observations** and **reproducible modeling**, written for "
        "newcomers to the industry. Everything runs on your own machine; no paid "
        "services are required."
    )

    st.header("Learning sequence")
    for number, stage in enumerate(learning_sequence(), start=1):
        st.markdown(f"**{number}. {stage['title']}** — {stage['description']}")

    st.header("Implementation status")
    st.info(
        "Stage 3: one dataset is implemented. Explore charts ERCOT's actual demand and its "
        "published day-ahead forecast (EIA-930), collected on demand from the command line. "
        "No models run, and no other page shows prices, observations, or model results."
    )
    # st.table renders plain HTML: readable by screen readers, unlike the canvas-based st.dataframe.
    st.table(
        [
            {"ID": f["id"], "Feature": f["name"], "Area": f["section"], "Status": f["status"]}
            for f in features()
        ],
        hide_index=True,
    )

    st.header("Data labels")
    st.markdown("Every value the platform shows will carry exactly one of these labels.")
    for label in data_labels():
        st.markdown(f"**{label['title']}** — {label['description']}")


def render_section(key: str) -> None:
    section = section_by_key(key)
    st.title(section.title)
    st.markdown(section.summary)
    st.warning(f"{NOT_IMPLEMENTED}. This page describes planned scope only.")

    st.header("Planned scope")
    st.markdown("\n".join(f"- {item}" for item in section.scope))

    st.header("Tracked features")
    st.markdown(
        "\n".join(
            f"- `{f['id']}` {f['name']} — **{f['status']}**"
            for f in features()
            if f["section"] == key
        )
    )


# Sections with a real implementation; every other section renders the generic
# "Not implemented" page. Tests render through this same dispatcher.
IMPLEMENTED = {
    "explore": render_explore,
    "learn": render_learn,
    "model-labs": render_model_lab,
    "finance": render_finance,
    "compliance": render_compliance,
}


def render_page(key: str) -> None:
    IMPLEMENTED.get(key, lambda: render_section(key))()
