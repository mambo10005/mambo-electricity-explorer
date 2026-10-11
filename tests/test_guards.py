"""Self-tests: the fake-result guards reject what they should and allow what they should."""

import pytest
from guards import assert_no_data_elements, assert_no_unauthorized_data
from streamlit.testing.v1 import AppTest

CHART_PAGE = "import streamlit as st\nst.title('x')\nst.line_chart([1, 2, 3])\n"
METRIC_PAGE = "import streamlit as st\nst.metric('Load', '1 GW')\n"


@pytest.fixture(scope="module")
def chart_page() -> AppTest:
    return AppTest.from_string(CHART_PAGE).run(timeout=30)


def _features(status: str) -> list[dict]:
    return [{"id": "REPLAY-01", "name": "Replay", "section": "replay", "status": status}]


def test_unimplemented_page_with_chart_fails(chart_page):
    with pytest.raises(AssertionError, match="unimplemented section 'replay'"):
        assert_no_unauthorized_data(chart_page, "replay", _features("planned"))


def test_unimplemented_page_with_metric_fails():
    at = AppTest.from_string(METRIC_PAGE).run(timeout=30)
    with pytest.raises(AssertionError, match="metric"):
        assert_no_unauthorized_data(at, "replay", _features("in-progress"))


def test_implemented_page_with_authorized_chart_passes(chart_page):
    assert_no_unauthorized_data(chart_page, "replay", _features("done"))


def test_real_catalog_currently_rejects_charts_on_every_section(chart_page):
    # No section has a done feature in Stage 2, so a chart anywhere must fail.
    with pytest.raises(AssertionError):
        assert_no_unauthorized_data(chart_page, "explore")


def test_home_rule_rejects_charts_regardless_of_status(chart_page):
    with pytest.raises(AssertionError):
        assert_no_data_elements(chart_page)
