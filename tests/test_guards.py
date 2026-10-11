"""Self-tests: the fake-result guards reject what they should and allow what they should."""

import pytest
from guards import assert_no_data_elements, assert_no_unauthorized_data
from streamlit.testing.v1 import AppTest

CHART_PAGE = "import streamlit as st\nst.title('x')\nst.line_chart([1, 2, 3])\n"
METRIC_PAGE = "import streamlit as st\nst.metric('Load', '1 GW')\n"


@pytest.fixture(scope="module")
def chart_page() -> AppTest:
    return AppTest.from_string(CHART_PAGE).run(timeout=30)


def _features(status: str, ui: bool = True) -> list[dict]:
    return [{"id": "REPLAY-01", "name": "Replay", "section": "replay", "status": status, "ui": ui}]


def test_unimplemented_page_with_chart_fails(chart_page):
    with pytest.raises(AssertionError, match="unimplemented section 'replay'"):
        assert_no_unauthorized_data(chart_page, "replay", _features("planned"))


def test_unimplemented_page_with_metric_fails():
    at = AppTest.from_string(METRIC_PAGE).run(timeout=30)
    with pytest.raises(AssertionError, match="metric"):
        assert_no_unauthorized_data(at, "replay", _features("in-progress"))


def test_implemented_page_with_authorized_chart_passes(chart_page):
    assert_no_unauthorized_data(chart_page, "replay", _features("done"))


def test_done_backend_feature_does_not_authorize_charts(chart_page):
    # e.g. a finished connector filed under a section whose page is not built.
    with pytest.raises(AssertionError, match="unimplemented section 'replay'"):
        assert_no_unauthorized_data(chart_page, "replay", _features("done", ui=False))


def test_real_catalog_rejects_charts_on_unimplemented_sections(chart_page):
    # Replay has no done feature, so a chart there must fail.
    with pytest.raises(AssertionError):
        assert_no_unauthorized_data(chart_page, "replay")


def test_real_catalog_authorizes_charts_only_where_a_feature_is_done(chart_page):
    from guards import section_is_implemented

    assert section_is_implemented("explore")  # EXPLORE-02 is done
    assert_no_unauthorized_data(chart_page, "explore")
    # Includes Sources and System Health, which hold done backend features
    # (DATA-01, STORE-01/02) but whose pages are not built.
    others = ("learn", "replay", "model-labs", "finance", "compliance", "sources", "system-health")
    assert not any(section_is_implemented(k) for k in others)


def test_page_dispatcher_matches_ui_feature_status():
    from guards import section_is_implemented

    from mambo_explorer.navigation import SECTIONS
    from mambo_explorer.pages import IMPLEMENTED

    assert set(IMPLEMENTED) == {s.key for s in SECTIONS if section_is_implemented(s.key)}


def test_home_rule_rejects_charts_regardless_of_status(chart_page):
    with pytest.raises(AssertionError):
        assert_no_data_elements(chart_page)
