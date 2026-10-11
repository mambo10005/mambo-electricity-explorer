"""Streamlit entrypoint: streamlit run src/mambo_explorer/app.py"""

from collections.abc import Callable

import streamlit as st

from mambo_explorer.navigation import SECTIONS
from mambo_explorer.pages import render_home, render_section


def _section_renderer(key: str) -> Callable[[], None]:
    def render() -> None:
        render_section(key)

    return render


st.set_page_config(page_title="mambo electricity explorer", layout="wide")
pages = [
    st.Page(render_home, title="Home", icon=":material/home:", url_path="home", default=True),
    *(
        st.Page(_section_renderer(s.key), title=s.title, icon=s.icon, url_path=s.key)
        for s in SECTIONS
    ),
]
st.navigation(pages).run()
