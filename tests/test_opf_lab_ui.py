"""Economic-dispatch lab via AppTest (headless). The network and offers are SYNTHETIC."""

import pytest
from streamlit.testing.v1 import AppTest

from mambo_explorer.modeling.runs import RunStore

LAB = "from mambo_explorer.pages import render_page\nrender_page('model-labs')\n"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    return path


def _open() -> AppTest:
    at = AppTest.from_string(LAB)
    at.session_state["lab_choice"] = "opf"
    return at.run(timeout=30)


def _case(at: AppTest, key: str) -> AppTest:
    at.selectbox(key="opf_case").set_value(key).run(timeout=30)
    return at


def _run(at: AppTest) -> AppTest:
    at.button(key="opf_run").click()
    return at.run(timeout=60)


def _table(at: AppTest, column: str):
    return next((tb.value for tb in at.table if column in tb.value.columns), None)


def _text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return "\n".join(parts)


def test_power_flow_lab_remains_the_default(data_dir):
    at = AppTest.from_string(LAB).run(timeout=30)
    assert at.radio(key="lab_choice").value == "pf"
    assert at.button(key="lab_run") is not None


def test_opf_lab_explains_scope_before_any_run(data_dir):
    at = _open()
    assert not at.exception
    text = _text(at)
    assert "chooses the dispatch itself" in text and "lossless" in text
    assert "not** actual ISO prices" in text and "one-hour" in text
    assert _table(at, "Dispatch (MW)") is None


def test_congested_default_run_shows_verified_prices_units_and_provenance(data_dir):
    at = _run(_open())
    dispatch = _table(at, "Dispatch (MW)")
    assert dict(zip(dispatch["Generator"], dispatch["Dispatch (MW)"], strict=True)) == {
        "G1 at A": 90.0,
        "G2 at B": 60.0,
    }
    prices = _table(at, "Modeled price ($/MWh)")
    assert dict(zip(prices["Bus"], prices["Modeled price ($/MWh)"], strict=True)) == {
        "A": 20.0,
        "B": 30.0,
        "C": 40.0,
    }
    flows = _table(at, "Binding")
    assert dict(zip(flows["Line"], flows["Binding"], strict=True))["AC"] == "yes"
    text = _text(at)
    # "$" is escaped for markdown (otherwise a pair renders as LaTeX and swallows the units)
    assert "3,600.00 synthetic \\$/h" in text
    assert "3,600.00 synthetic \\$ (cost rate × 1 h)" in text
    assert "highspy 1.15.1" in text and "commit 26be8c18b7ef" in text
    assert "not ERCOT or any ISO's prices" in text
    assert RunStore(data_dir).recent(kind="opf.dc")[0].price_status == "verified"


def test_breakpoint_case_withholds_prices_and_shows_average_rates(data_dir):
    at = _run(_case(_open(), "breakpoint"))
    assert _table(at, "Modeled price ($/MWh)") is None
    rates = _table(at, "Average rate ($/MWh)")
    c = rates[rates["Bus"] == "C"].set_index("Change (MW)")
    # Hand derivation: +0.1 MW needs G2 (30); −0.1 MW saves G1 (20). ΔC = ±rate × 0.1.
    assert c.loc["+0.1", "Average rate ($/MWh)"] == "30"
    assert c.loc["+0.1", "Cost-rate change ($/h)"] == "+3"
    assert c.loc["−0.1", "Average rate ($/MWh)"] == "20"
    assert c.loc["−0.1", "Cost-rate change ($/h)"] == "−2"
    assert any("Price gate: **not passed**" in w.value for w in at.warning)
    assert not any("one-sided rates" in w.value.lower() for w in at.warning)


def test_infeasible_case_shows_failure_without_stale_results(data_dir):
    at = _run(_open())  # a successful run first
    assert _table(at, "Dispatch (MW)") is not None
    at = _run(_case(at, "infeasible"))
    assert _table(at, "Dispatch (MW)") is None and _table(at, "Modeled price ($/MWh)") is None
    assert any("Infeasible" in e.value and "never sheds load" in e.value for e in at.error)


def test_changing_an_input_hides_the_previous_result(data_dir):
    at = _run(_open())
    assert _table(at, "Dispatch (MW)") is not None
    at.slider(key="opf_cost_g2").set_value(25.0).run(timeout=30)
    assert _table(at, "Dispatch (MW)") is None
    assert "inputs changed since the last run" in _text(at)


def test_equal_offers_case_explains_nonunique_dispatch(data_dir):
    at = _run(_case(_open(), "equal"))
    assert any("one optimal dispatch, not the only one" in i.value for i in at.info)
    assert _table(at, "Modeled price ($/MWh)") is not None


def test_no_unescaped_dollar_in_rendered_markdown(data_dir):
    """Streamlit markdown renders a pair of "$" as LaTeX and swallows the text between them.
    Found in the Stage 7 browser check (the cost units vanished). Every rendered markdown,
    caption, and alert on this page must escape "$".

    Widget labels are the exception: Streamlit copies the raw label into aria-label, so an
    escape would be read aloud as a backslash. Labels instead must never hold two unescaped
    "$" (a single one cannot open a math span) and must contain no backslash."""
    import re

    unescaped = re.compile(r"(?<!\\)\$")
    at = _run(_open())
    texts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        texts += [x.value for x in group]
    assert [t for t in texts if unescaped.search(t)] == []
    labels = [s.label for s in at.slider] + [s.label for s in at.selectbox]
    assert [lb for lb in labels if len(unescaped.findall(lb)) > 1 or "\\" in lb] == []


def test_result_from_older_checks_is_hidden_with_its_old_wording(data_dir):
    """A result whose explanation was produced by older checks is never shown (BL-5)."""
    at = _run(_case(_open(), "breakpoint"))
    old = at.session_state["opf_last_run"]
    old.checks_version = "1.1.0"
    old.price_note = "Breakpoint at bus(es) A, B, C: ... One-sided rates are shown instead."
    at.session_state["opf_last_run"] = old
    at.run(timeout=30)
    assert _table(at, "Average rate ($/MWh)") is None and _table(at, "Dispatch (MW)") is None
    assert "older version of the checks" in _text(at)
    assert "One-sided rates" not in _text(at)
