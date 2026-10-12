"""Streamlit entrypoint: streamlit run src/mambo_explorer/app.py"""

from collections.abc import Callable

import streamlit as st

from mambo_explorer import routes
from mambo_explorer.navigation import SECTIONS
from mambo_explorer.pages import render_home, render_page


def _section_renderer(key: str) -> Callable[[], None]:
    def render() -> None:
        render_page(key)

    return render


st.set_page_config(page_title="mambo electricity explorer", layout="wide")
sections = {
    s.key: st.Page(_section_renderer(s.key), title=s.title, icon=s.icon, url_path=s.key)
    for s in SECTIONS
}
for key, page in sections.items():
    routes.register(key, page)  # lets Learn and Model Labs link to each other
pages = [
    st.Page(render_home, title="Home", icon=":material/home:", url_path="home", default=True),
    *sections.values(),
]
st.navigation(pages).run()
