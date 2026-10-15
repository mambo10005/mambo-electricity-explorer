"""Model Labs page via AppTest (headless). The network is SYNTHETIC."""

import pytest
from guards import assert_no_data_elements
from streamlit.testing.v1 import AppTest

from mambo_explorer.modeling.runs import RunStore

LAB = "from mambo_explorer.pages import render_page\nrender_page('model-labs')\n"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    return path


def _table(at: AppTest, column: str):
    return next((tb.value for tb in at.table if column in tb.value.columns), None)


def _text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [x.value for x in at.info] + [x.value for x in at.success]
    parts += [x.value for x in at.warning] + [x.value for x in at.error]
    return "\n".join(parts)


def _run(at: AppTest) -> AppTest:
    at.button(key="lab_run").click()
    return at.run(timeout=30)


def test_before_any_run_shows_network_and_no_results(data_dir):
    at = AppTest.from_string(LAB).run(timeout=30)
    assert not at.exception
    assert _table(at, "Reactance (pu, 100 MVA base)") is not None  # accessible topology table
    assert _table(at, "Role") is not None
    assert _table(at, "Flow (MW)") is None
    assert "Nothing has been run yet" in _text(at)
    assert "synthetic" in _text(at).lower()
    assert_no_data_elements(at)


def test_run_shows_modeled_results_and_saves_locally(data_dir):
    at = _run(AppTest.from_string(LAB).run(timeout=30))
    flows = _table(at, "Flow (MW)")
    assert dict(zip(flows["Branch"], flows["Flow (MW)"], strict=True)) == {
        "AB": 37.5,
        "BC": 87.5,
        "AC": 62.5,
    }
    text = _text(at)
    assert "Data label: **modeled**" in text and "Every check passed" in text
    assert "commit 26be8c18b7ef" in text and "scipy.sparse.linalg.splu" in text
    checks = _table(at, "Check")
    assert set(checks["Result"]) == {"pass"}
    saved = RunStore(data_dir).recent()
    assert len(saved) == 1 and saved[0].status == "ok"


def test_changing_an_input_hides_the_previous_result(data_dir):
    at = _run(AppTest.from_string(LAB).run(timeout=30))
    assert _table(at, "Flow (MW)") is not None
    at.slider(key="lab_load").set_value(200.0).run(timeout=30)
    assert _table(at, "Flow (MW)") is None  # stale numbers are not shown
    assert "inputs changed since the last run" in _text(at)
    at = _run(at)
    flows = _table(at, "Flow (MW)")
    assert dict(zip(flows["Branch"], flows["Flow (MW)"], strict=True))["BC"] != 87.5


def test_toggle_line_out_changes_topology_result(data_dir):
    at = AppTest.from_string(LAB).run(timeout=30)
    at.toggle(key="lab_ac_in").set_value(False).run(timeout=30)
    at = _run(at)
    flows = _table(at, "Flow (MW)")
    assert set(flows["Branch"]) == {"AB", "BC"}
    assert dict(zip(flows["Branch"], flows["Flow (MW)"], strict=True)) == {"AB": 100.0, "BC": 150.0}


def test_failed_run_replaces_an_earlier_success(data_dir, monkeypatch):
    at = _run(AppTest.from_string(LAB).run(timeout=30))
    assert _table(at, "Flow (MW)") is not None

    from mambo_explorer.modeling import adapter

    original = adapter.run_dc_power_flow

    def failing(inputs, solver=None):
        def broken(net):
            raise ValueError("DC power flow: reduced B' is singular")

        return original(inputs, solver=broken)

    monkeypatch.setattr(adapter, "run_dc_power_flow", failing)
    at = _run(at)
    assert _table(at, "Flow (MW)") is None
    assert any("The run failed" in e.value for e in at.error)
    assert "singular" in _text(at)
    statuses = [r.status for r in RunStore(data_dir).recent()]
    assert sorted(statuses) == ["failed", "ok"]


def test_violations_are_visible(data_dir):
    at = AppTest.from_string(LAB).run(timeout=30)
    at.slider(key="lab_g2").set_value(0.0).run(timeout=30)
    at.slider(key="lab_load").set_value(300.0).run(timeout=30)
    at = _run(at)
    assert any("limits are exceeded" in w.value for w in at.warning)
    checks = _table(at, "Check")
    assert "FAIL" in set(checks["Result"])
