"""The one place that adds CSS to the app: a keyboard-focus indicator (focus.css).

The stylesheet ships with the package and is never built from user input. It is injected
as a <style> element only (no script). See focus.css for the selectors and their limits.
"""

from __future__ import annotations

from importlib.resources import files

import streamlit as st

FOCUS_COLOR = "#3B82F6"


def focus_css() -> str:
    return files("mambo_explorer").joinpath("focus.css").read_text("utf-8")


def inject_focus_style() -> None:
    st.html(f"<style>{focus_css()}</style>")
