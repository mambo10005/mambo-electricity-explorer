"""Cross-page links between Learn and Model Labs.

app.py registers its st.Page objects here on every run, because st.switch_page needs the
Page object for a page defined by a callable. Only validated identifiers cross pages, and
they go through session state: a lesson id (`HANDOFF_LESSON`) or a lab case key
(`HANDOFF_LAB_CASE`). The receiving page validates the identifier again before using it.
"""

from __future__ import annotations

import streamlit as st

PAGES: dict[str, object] = {}
HANDOFF_LESSON = "handoff_lesson"
HANDOFF_LAB_CASE = "handoff_lab_case"


def register(key: str, page) -> None:
    PAGES[key] = page


def go(key: str, title: str) -> None:
    """Switch to a registered page; without one (e.g. a single-page test), say where to go."""
    page = PAGES.get(key)
    if page is not None:
        st.switch_page(page)
    st.info(f"Open **{title}** from the navigation menu; your selection is waiting there.")
