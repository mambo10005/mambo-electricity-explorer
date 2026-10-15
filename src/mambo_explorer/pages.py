"""Page renderers. Stage 1 shell: no data, charts, or model output anywhere."""

import streamlit as st

from mambo_explorer.catalog import data_labels, features, learning_sequence
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
        "Stage 1: application shell only. No data is collected, no models are run, "
        "and no page shows prices, observations, or model results yet."
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
