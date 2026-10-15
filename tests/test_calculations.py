"""Calculation services. Observations here are SYNTHETIC values built in the test."""

import math
from datetime import date

import pytest
from eia_fixtures import FAKE_KEY, FakeEIA, synthetic_rows

from mambo_explorer import calculations as calc
from mambo_explorer.calculations import Observation, Selection
from mambo_explorer.collect import collect, plan_collection
from mambo_explorer.eia.client import EIAClient
from mambo_explorer.storage import Store

U = "megawatthours"
SEL = Selection("ERCO", "2026-10-01T00", "2026-10-01T03")


def ob(metric, period, value, raw=None, unit=U, revision=1, entity="ERCO"):
    raw = raw if raw is not None else (None if value is None else str(value))
    return Observation(entity, metric, period, value, raw, unit, "", revision, f"run{revision}")


def series(metric, values, start_hour=0):
    return [ob(metric, f"2026-10-01T{h + start_hour:02d}", v) for h, v in enumerate(values)]


# --- labels --------------------------------------------------------------------------------


def test_labels_between_is_inclusive_label_arithmetic():
    assert calc.labels_between("2026-10-01T22", "2026-10-02T01") == [
        "2026-10-01T22",
        "2026-10-01T23",
        "2026-10-02T00",
        "2026-10-02T01",
    ]
    assert calc.labels_between("2026-10-01T05", "2026-10-01T05") == ["2026-10-01T05"]


def test_label_runs_group_contiguous_labels():
    labels = ["2026-10-01T01", "2026-10-01T02", "2026-10-01T05", "2026-10-01T23", "2026-10-02T00"]
    assert calc.label_runs(labels) == [
        ("2026-10-01T01", "2026-10-01T02", 2),
        ("2026-10-01T05", "2026-10-01T05", 1),
        ("2026-10-01T23", "2026-10-02T00", 2),
    ]
    assert calc.label_runs([]) == []


def test_selection_rejects_reversed_window():
    with pytest.raises(ValueError):
        Selection("ERCO", "2026-10-02T00", "2026-10-01T00")


# --- power / energy -------------------------------------------------------------------------


def test_power_energy_known_examples():
    assert calc.power_energy(average_mw=250, hours=4).values == {"energy_mwh": 1000}
    one_hour = calc.power_energy(energy_mwh=48_000, hours=1)
    assert one_hour.values == {"average_mw": 48_000} and one_hour.unit == "MW"
    assert calc.power_energy(energy_mwh=48_000, hours=2).values == {"average_mw": 24_000}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hours": 1},
        {"average_mw": 1, "energy_mwh": 1, "hours": 1},
        {"average_mw": 1, "hours": 0},
        {"average_mw": 1, "hours": -2},
        {"average_mw": 1, "hours": float("nan")},
    ],
)
def test_power_energy_rejects_invalid_input(kwargs):
    result = calc.power_energy(**kwargs)
    assert result.status == "unavailable" and result.reason and not result.values


# --- series summary ----------------------------------------------------------------------


def test_series_summary_known_example_with_exclusions_and_references():
    obs = [
        ob("D", "2026-10-01T00", 100.0),
        ob("D", "2026-10-01T01", None),
        ob("D", "2026-10-01T02", 300.0, revision=2),
    ]  # T03 absent
    r = calc.series_summary(obs, SEL, "D")
    assert r.ok and r.unit == U and r.formula_version == "1"
    assert r.values["max"] == 300 and r.values["max_period"] == "2026-10-01T02"
    assert r.values["min"] == 100 and r.values["mean"] == 200 and r.values["range"] == 200
    assert (r.values["expected_labels"], r.values["present_rows"], r.values["absent_rows"]) == (
        4,
        3,
        1,
    )
    assert r.valid_count == 2
    assert {(e["period"], e["reason"]) for e in r.exclusions} == {
        ("2026-10-01T01", "null value"),
        ("2026-10-01T03", "absent row"),
    }
    assert {
        "metric": "D",
        "period": "2026-10-01T02",
        "revision": 2,
        "run_id": "run2",
    } in r.references
    assert r.selection == {
        "entity": "ERCO",
        "start_period": "2026-10-01T00",
        "end_period": "2026-10-01T03",
        "metric": "D",
    }


def test_series_summary_empty_input_is_unavailable_not_zero():
    r = calc.series_summary([], SEL, "D")
    assert r.status == "unavailable" and "no valid observations" in r.reason
    assert r.values == {} and len(r.exclusions) == 4


def test_series_summary_duplicates_are_unavailable():
    r = calc.series_summary([ob("D", "2026-10-01T00", 1.0), ob("D", "2026-10-01T00", 2.0)], SEL)
    assert r.status == "unavailable" and "duplicate" in r.reason


def test_series_summary_mixed_units_are_unavailable():
    r = calc.series_summary(
        [ob("D", "2026-10-01T00", 1.0), ob("D", "2026-10-01T01", 2.0, unit="MW")], SEL
    )
    assert r.status == "unavailable" and "mixed units" in r.reason


def test_window_change_changes_result():
    obs = series("D", [10.0, 20.0, 90.0, 40.0])
    narrow = calc.series_summary(obs, Selection("ERCO", "2026-10-01T00", "2026-10-01T01"), "D")
    wide = calc.series_summary(obs, SEL, "D")
    assert narrow.values["max"] == 20 and wide.values["max"] == 90


def test_other_entities_and_metrics_are_ignored():
    obs = series("D", [5.0, 5.0, 5.0, 5.0]) + [
        ob("D", "2026-10-01T00", 999.0, entity="CISO"),
        ob("DF", "2026-10-01T00", 888.0),
    ]
    assert calc.series_summary(obs, SEL, "D").values["max"] == 5


# --- coverage ----------------------------------------------------------------------------


def test_coverage_distinguishes_absent_null_zero_and_non_numeric():
    obs = [
        ob("DF", "2026-10-01T00", 0.0),
        ob("DF", "2026-10-01T01", None),
        ob("DF", "2026-10-01T02", None, raw="n/a"),
    ]  # T03 absent
    v = calc.coverage(obs, SEL, "DF").values
    assert (v["expected_labels"], v["present_rows"], v["valid_values"]) == (4, 3, 1)
    assert (v["zero_values"], v["null_values"], v["non_numeric_values"], v["absent_rows"]) == (
        1,
        1,
        1,
        1,
    )
    assert v["absent_runs"] == [("2026-10-01T03", "2026-10-01T03", 1)]
    assert v["zero_periods"] == ["2026-10-01T00"]


def test_coverage_is_separate_per_metric():
    obs = series("D", [1.0, 2.0, 3.0, 4.0]) + series("DF", [1.0, 2.0])
    assert calc.coverage(obs, SEL, "D").values["absent_rows"] == 0
    assert calc.coverage(obs, SEL, "DF").values["absent_runs"] == [
        ("2026-10-01T02", "2026-10-01T03", 2)
    ]


# --- forecast error ------------------------------------------------------------------------


def test_forecast_error_known_example_and_sign_convention():
    obs = series("D", [100.0, 100.0, 100.0, 100.0]) + series("DF", [90.0, 110.0, 100.0, 120.0])
    r = calc.forecast_error(obs, SEL)
    v = r.values
    assert [p["error"] for p in v["pair_errors"]] == [10.0, -10.0, 0.0, -20.0]
    assert v["pairs"] == 4 and r.valid_count == 4
    assert v["mean_error"] == pytest.approx(-5.0)
    assert v["mae"] == pytest.approx(10.0)
    assert v["rmse"] == pytest.approx(math.sqrt((100 + 100 + 0 + 400) / 4))
    assert (v["under_forecast_hours"], v["over_forecast_hours"], v["exact_hours"]) == (1, 2, 1)
    assert v["largest_abs_error"] == -20.0 and v["largest_abs_error_period"] == "2026-10-01T03"
    assert len(r.references) == 8  # both sides of every pair


def test_forecast_error_excludes_unmatched_and_invalid_without_filling():
    obs = [
        ob("D", "2026-10-01T00", 100.0),
        ob("DF", "2026-10-01T00", 90.0),
        ob("D", "2026-10-01T01", 100.0),  # forecast absent
        ob("D", "2026-10-01T02", None),
        ob("DF", "2026-10-01T02", 50.0),  # actual null
        ob("D", "2026-10-01T03", 100.0),
        ob("DF", "2026-10-01T03", 1.0, unit="MW"),
    ]
    r = calc.forecast_error(obs, SEL)
    assert r.values["pairs"] == 1 and r.values["mae"] == 10
    reasons = {e["period"]: e["reason"] for e in r.exclusions}
    assert reasons == {
        "2026-10-01T01": "forecast absent",
        "2026-10-01T02": "actual null value",
        "2026-10-01T03": "unit mismatch (megawatthours vs MW)",
    }


def test_forecast_error_without_pairs_is_unavailable():
    r = calc.forecast_error(series("D", [1.0, 2.0, 3.0, 4.0]), SEL)
    assert r.status == "unavailable" and r.values == {} and len(r.exclusions) == 4
    assert calc.forecast_error([], SEL).status == "unavailable"


def test_forecast_error_duplicates_are_unavailable():
    obs = series("D", [1.0]) + series("DF", [1.0]) + [ob("DF", "2026-10-01T00", 2.0)]
    assert "duplicate" in calc.forecast_error(obs, SEL).reason


# --- snapshots and the real store -------------------------------------------------------


def test_snapshot_id_is_order_independent_and_tracks_revisions_and_selection():
    obs = series("D", [1.0, 2.0])
    base = calc.snapshot_id(obs, SEL)
    assert base == calc.snapshot_id(list(reversed(obs)), SEL)
    revised = [obs[0], ob("D", "2026-10-01T01", 2.5, revision=2)]
    assert calc.snapshot_id(revised, SEL) != base
    assert calc.snapshot_id(obs, Selection("ERCO", "2026-10-01T00", "2026-10-01T02")) != base


def test_load_observations_uses_latest_revision_from_store(tmp_path):
    store = Store(tmp_path / "data")
    plan = plan_collection(days=1, lookback_days=0, today=date(2026, 10, 11))
    for value in ("40000", "40100"):  # second run revises one hour
        rows = synthetic_rows(plan.fetch_start_day, 1, overrides={("D", "2026-10-10T12"): value})
        client = EIAClient(FAKE_KEY, transport=FakeEIA(rows), sleep=lambda s: None)
        collect(plan, client, store)
    sel = Selection("ERCO", "2026-10-10T00", "2026-10-10T23")
    obs = calc.load_observations(store, sel)
    assert len(obs) == 48 and len({(o.metric, o.period) for o in obs}) == 48
    revised = next(o for o in obs if (o.metric, o.period) == ("D", "2026-10-10T12"))
    assert revised.value == 40100 and revised.revision == 2
    ref = next(
        r for r in calc.series_summary(obs, sel, "D").references if r["period"] == "2026-10-10T12"
    )
    assert ref["revision"] == 2 and ref["run_id"] == revised.run_id
