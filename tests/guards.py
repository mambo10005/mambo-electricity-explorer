"""Guards against fake results. Shared by the app tests and the guard self-tests.

A section is authorized to show data elements (charts, maps, metrics) only once at
least one of its features in content/features.yaml is `done`. Until then, any data
element on that page is treated as a fabricated result. The Home page is never a data
page and is always held to the strict rule.
"""

from streamlit.testing.v1 import AppTest

from mambo_explorer.catalog import features as load_features

# AppTest element types that would indicate data or charts being shown. Names were
# checked against Streamlit 1.65 (st.line_chart -> vega_lite_chart, st.map -> deck_gl_json_chart).
DATA_ELEMENTS = (
    "vega_lite_chart",
    "plotly_chart",
    "deck_gl_json_chart",
    "graphviz_chart",
    "metric",
)


def data_elements(at: AppTest) -> dict[str, int]:
    return {kind: len(at.get(kind)) for kind in DATA_ELEMENTS if len(at.get(kind))}


def section_is_implemented(section: str, features: list[dict] | None = None) -> bool:
    features = load_features() if features is None else features
    return any(f["section"] == section and f["status"] == "done" for f in features)


def assert_no_data_elements(at: AppTest) -> None:
    found = data_elements(at)
    assert not found, f"data elements on a page that must not show data: {found}"


def assert_no_unauthorized_data(
    at: AppTest, section: str, features: list[dict] | None = None
) -> None:
    if section_is_implemented(section, features):
        return
    found = data_elements(at)
    assert not found, f"unimplemented section {section!r} shows data elements: {found}"
