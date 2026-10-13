"""EIA-930 net generation by energy source: collection, isolation, refresh, health, exercises.

Offline and credential-free. All data is SYNTHETIC (tests/generation_fixtures.py).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from eia_fixtures import FAKE_KEY, FakeEIA, synthetic_rows
from ercot_fixtures import FakeErcot
from generation_fixtures import CATEGORIES, FakeGeneration, generation_rows, response_body
from refresh_helpers import Clock, WindowEIA, clients, config, ercot_docs, patch_clock, stores

from mambo_explorer import calculations as calc
from mambo_explorer import cli, generation, health, refresh
from mambo_explorer import collect as demand
from mambo_explorer import generation_exercises as ge
from mambo_explorer.eia import dataset as ds
from mambo_explorer.eia.client import BudgetExceeded, EIAClient, ResponseValidationError
from mambo_explorer.exercises import Unavailable
from mambo_explorer.storage import Store

TODAY = date(2026, 3, 10)
SEL = calc.Selection("ERCO", "2026-03-08T00", "2026-03-09T23")


def plan(days=2, lookback=0, **kw):
    return generation.plan_generation(days=days, lookback_days=lookback, today=TODAY, **kw)


def client(transport, budget=12):
    return EIAClient(FAKE_KEY, transport=transport, sleep=lambda s: None, max_requests=budget)


def run(data_dir, transport=None, p=None, budget=12):
    p = p or plan()
    return generation.collect(
        p, client(transport or FakeGeneration(), budget), generation.store(data_dir)
    )


def load(data_dir, sel=SEL):
    return calc.load_generation(generation.store(data_dir), sel)


# --- dataset facts --------------------------------------------------------------------------


def test_reviewed_route_facet_codes_and_store_are_what_the_metadata_showed():
    assert ds.GENERATION_ROUTE == "electricity/rto/fuel-type-data"
    assert ds.GENERATION_FACET == "fueltype" and ds.GENERATION_METRIC == "NG"
    instructions = (
        "COL",
        "NG",
        "NUC",
        "OIL",
        "WAT",
        "PS",
        "SUN",
        "SNB",
        "WND",
        "WNB",
        "BAT",
        "OES",
        "GEO",
        "OTH",
        "UNK",
    )
    assert ds.ENERGY_SOURCE_CODES[: len(instructions)] == instructions
    assert (
        "UES" in ds.ENERGY_SOURCE_CODES
        and "not in the form instructions" in ds.ENERGY_SOURCE_NAMES["UES"]
    )
    assert set(ds.STORAGE_CODES) <= set(ds.ENERGY_SOURCE_CODES)
    assert ds.GENERATION_STORE != "eia930" and ds.GENERATION_STORE != "ercot-np6-345-cd"
    assert "energy_source" in generation.IDENTITY and "period" in generation.IDENTITY
    assert ds.energy_source_name("XYZ").endswith("(not in the reviewed code list)")


def test_plan_bounds_match_the_demand_collector():
    p = plan(days=3, lookback=1)
    assert (p.start_day, p.end_day, p.fetch_days) == (date(2026, 3, 7), TODAY, 4)
    assert p.start_period == "2026-03-06T00" and p.end_period == "2026-03-09T23"
    assert p.expected_rows == 4 * 24 * len(ds.ENERGY_SOURCE_CODES)
    assert p.max_rows == 4 * 24 * ds.MAX_CATEGORIES
    assert p.pages_needed == 1 and p.max_requests == 1 + demand.RETRY_ALLOWANCE
    with pytest.raises(demand.PlanError, match="per-run maximum"):
        plan(days=31, lookback=1)
    with pytest.raises(demand.PlanError, match="below"):
        plan(days=30, page_size=100, max_requests=2)
    d = p.describe()
    assert "every category the source returns is kept" in d["series"]
    assert "never shown" in d["credential"]


# --- collection -----------------------------------------------------------------------------


def test_collection_keeps_categories_signs_units_and_flags(tmp_path):
    fake = FakeGeneration(
        overrides={("COL", "2026-03-09T10"): None, ("NG", "2026-03-09T11"): "n/a"},
        drop={("SUN", "2026-03-08T03")},
    )
    summary = run(tmp_path, fake)
    assert summary["categories"] == sorted(CATEGORIES) and summary["unreviewed_categories"] == []
    assert summary["rows_received"] == 2 * 24 * len(CATEGORIES) - 1 and summary["requests"] == 1
    assert "facets[fueltype][]" not in fake.urls[0]  # no category filter: new codes are kept
    assert "electricity/rto/fuel-type-data/data/" in fake.urls[0]
    got = {(o.metric, o.period): o for o in load(tmp_path)}
    assert (
        got[("BAT", "2026-03-08T02")].value == -600
        and "negative" in got[("BAT", "2026-03-08T02")].quality_flags
    )
    assert got[("BAT", "2026-03-08T02")].value_raw == "-600"  # never clipped
    assert (
        got[("COL", "2026-03-09T10")].value is None
        and "missing" in got[("COL", "2026-03-09T10")].quality_flags
    )
    assert (
        got[("NG", "2026-03-09T11")].value is None
        and "non_numeric" in got[("NG", "2026-03-09T11")].quality_flags
    )
    assert ("SUN", "2026-03-08T03") not in got  # absent rows stay absent, never zero
    assert {o.unit for o in got.values()} == {"megawatthours"}
    with generation.store(tmp_path).query() as con:
        route, metric, name = con.execute(
            "SELECT DISTINCT route, metric, energy_source_name FROM latest WHERE energy_source='NG'"
        ).fetchone()
    assert (route, metric, name) == (ds.GENERATION_ROUTE, "NG", ds.ENERGY_SOURCE_NAMES["NG"])


def test_unknown_categories_are_kept_and_flagged_not_dropped(tmp_path):
    summary = run(tmp_path, FakeGeneration(categories=("NG", "ZZZ", "UES")))
    assert summary["categories"] == ["NG", "UES", "ZZZ"] and summary["unreviewed_categories"] == [
        "ZZZ"
    ]
    obs = load(tmp_path)
    assert {o.metric for o in obs} == {"NG", "UES", "ZZZ"}
    assert all("unreviewed_category" in o.quality_flags for o in obs if o.metric == "ZZZ")
    assert not any("unreviewed_category" in o.quality_flags for o in obs if o.metric == "UES")


def test_pagination_is_followed_and_truncation_refused(tmp_path):
    p = plan(page_size=100)
    assert p.pages_needed == 8  # estimate from reviewed codes; actual rows are fewer
    fake = FakeGeneration()
    summary = run(tmp_path, fake, p)
    assert summary["pages"] == 3 and summary["requests"] == 3  # 288 rows / 100 per page
    assert summary["rows_new"] == 288

    class Truncated(FakeGeneration):
        def __call__(self, url, timeout):
            status, body = super().__call__(url, timeout)
            payload = json.loads(body)
            payload["response"]["data"] = payload["response"]["data"][:50]
            return status, json.dumps(payload).encode()

    with pytest.raises(ResponseValidationError):
        run(tmp_path / "b", Truncated(), p)


def test_too_many_categories_is_refused_as_out_of_scope(tmp_path):
    many = tuple(f"C{i:02d}" for i in range(ds.MAX_CATEGORIES + 1))
    with pytest.raises(ResponseValidationError, match="above the expected maximum"):
        run(tmp_path, FakeGeneration(categories=many))
    assert generation.store(tmp_path).runs()[0]["status"] == "failed"


def test_rows_outside_scope_or_wrong_respondent_are_refused(tmp_path):
    rows = generation_rows(date(2026, 3, 8), 2)
    rows[5]["respondent"] = "MISO"
    with pytest.raises(ResponseValidationError, match="respondent"):
        run(tmp_path, lambda url, t: (200, response_body(rows)))
    rows = generation_rows(date(2026, 3, 8), 2)
    rows[0]["fueltype"] = ""
    with pytest.raises(ResponseValidationError, match="fueltype"):
        run(tmp_path / "b", lambda url, t: (200, response_body(rows)))


def test_request_budget_counts_retries(tmp_path):
    class Flaky(FakeGeneration):
        def __init__(self, times):
            super().__init__()
            self.times = times

        def __call__(self, url, timeout):
            if self.times:
                self.times -= 1
                return 500, b"synthetic server error"
            return super().__call__(url, timeout)

    summary = run(tmp_path, Flaky(2), budget=4)
    assert summary["requests"] == 3 and summary["retries"] == 2
    with pytest.raises(BudgetExceeded):
        run(tmp_path / "b", Flaky(9), budget=2)


# --- revisions and isolation -----------------------------------------------------------------


def test_repeat_is_idempotent_and_a_changed_value_becomes_a_revision(tmp_path):
    run(tmp_path)
    again = run(tmp_path)
    assert (again["rows_new"], again["rows_revised"], again["rows_unchanged"]) == (0, 0, 288)
    third = run(tmp_path, FakeGeneration(overrides={("BAT", "2026-03-08T02"): "-650"}))
    assert (third["rows_new"], third["rows_revised"], third["rows_unchanged"]) == (0, 1, 287)
    with generation.store(tmp_path).query() as con:
        history = con.execute(
            "SELECT revision, value_raw FROM observations WHERE energy_source='BAT' AND "
            "period='2026-03-08T02' ORDER BY revision"
        ).fetchall()
    assert history == [(1, "-600"), (2, "-650")]
    assert (
        next(o for o in load(tmp_path) if (o.metric, o.period) == ("BAT", "2026-03-08T02")).value
        == -650
    )


def test_generation_never_touches_the_demand_store(tmp_path):
    demand_store = Store(tmp_path)
    p = demand.plan_collection(days=2, lookback_days=0, today=TODAY)
    demand.collect(
        p, client(FakeEIA(synthetic_rows(p.fetch_start_day, p.fetch_days))), demand_store
    )
    before = {f["path"]: f["sha256"] for f in demand_store.committed_files("observations")}
    catalog_before = (demand_store.catalog).read_bytes()
    run(tmp_path)
    assert {f["path"]: f["sha256"] for f in demand_store.committed_files("observations")} == before
    assert demand_store.catalog.read_bytes() == catalog_before
    assert generation.store(tmp_path).root != demand_store.root
    with demand_store.query() as con:
        assert con.execute("SELECT DISTINCT metric FROM latest ORDER BY 1").fetchall() == [
            ("D",),
            ("DF",),
        ]
    with generation.store(tmp_path).query() as con:
        assert con.execute("SELECT DISTINCT metric FROM latest").fetchall() == [("NG",)]
    # A "NG" demand metric would be natural gas here; neither store sees the other's rows.
    assert not any(o.metric in ("D", "DF") for o in load(tmp_path))


# --- calculation ----------------------------------------------------------------------------


def test_generation_mix_partial_coverage_signed_sums_and_withheld_shares(tmp_path):
    run(
        tmp_path,
        FakeGeneration(overrides={("COL", "2026-03-09T10"): None}, drop={("SUN", "2026-03-08T03")}),
    )
    r = calc.generation_mix(load(tmp_path), SEL)
    v = r.values
    assert r.ok and v["categories"] == sorted(CATEGORIES)
    assert (v["complete_hours"], v["incomplete_hours"]) == (46, 2)
    assert v["absent_category_hours"] == 1 and v["null_category_hours"] == 1
    assert (
        v["per_category"]["BAT"]["negative_hours"] == 12
        and v["per_category"]["BAT"]["energy_sum"] == 12 * -600 + 10 * 900
    )
    assert (
        v["per_category"]["SUN"]["absent_rows"] == 1
        and v["per_category"]["COL"]["null_values"] == 1
    )
    assert v["categories_with_negative_hours"] == ["BAT"]
    assert v["shares"] is None and "negative" in v["share_note"]
    hour = next(h for h in v["hours"] if h["period"] == "2026-03-08T03")
    assert hour["categories_present"] == 5 and not hour["complete"]
    assert v["largest_category_by_energy"] == "NG"
    assert v["window_sum_complete_hours"] == sum(
        h["category_sum"] for h in v["hours"] if h["complete"]
    )
    assert {e["reason"] for e in r.exclusions} == {"absent row", "null value"}


def test_shares_are_offered_only_when_complete_and_non_negative(tmp_path):
    run(tmp_path, FakeGeneration(categories=("NG", "NUC", "COL")))
    v = calc.generation_mix(load(tmp_path), SEL).values
    assert v["complete_hours"] == 48 and v["shares"] is not None
    assert (
        abs(sum(v["shares"].values()) - 1) < 1e-12
        and "not a share of total system generation" in v["share_note"]
    )
    assert v["shares"]["NG"] == pytest.approx(20000 / 32000)
    assert calc.generation_mix([], SEL).status == "unavailable"


# --- refresh and health ------------------------------------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    patch_clock(monkeypatch, c)
    return c


def test_generation_is_disabled_by_default_and_a_plan_without_the_section_still_loads():
    assert not config().generation.enabled and "eia-generation" not in config().enabled()
    import yaml

    from mambo_explorer import refresh_config as rc

    data = yaml.safe_load(rc.default_text())
    del data["sources"]["eia-generation"]
    c = rc.validate(data)
    assert not c.generation.enabled and c.generation.request_budget == 12
    assert config(**{"sources__eia-generation__enabled": True}).enabled() == [
        "eia",
        "ercot",
        "eia-generation",
    ]


def test_refresh_with_generation_enabled_keeps_budgets_and_datasets_separate(tmp_path, clock):
    cfg = config(**{"sources__eia-generation__enabled": True})
    cs = clients(WindowEIA(), FakeErcot(ercot_docs(date(2026, 3, 9), 3)))
    gen_fake = FakeGeneration()
    cs["eia-generation"] = lambda budget: client(gen_fake, budget)
    record = refresh.refresh(
        cfg,
        ["eia", "ercot", "eia-generation"],
        data_dir=tmp_path,
        stores=stores(tmp_path) | {"eia-generation": generation.store(tmp_path)},
        clients=cs,
        now=clock,
        local_today=clock().date(),
        dry_run=True,
        secrets=[FAKE_KEY],
    )
    assert record["requests_budgeted"] == 36 and record["eia_api_requests_budgeted"] == 24
    assert gen_fake.urls == []
    record = refresh.refresh(
        cfg,
        ["eia", "ercot", "eia-generation"],
        data_dir=tmp_path,
        stores=stores(tmp_path) | {"eia-generation": generation.store(tmp_path)},
        clients=cs,
        now=clock,
        local_today=clock().date(),
        dry_run=False,
        secrets=[FAKE_KEY],
    )
    by = {r["source"]: r for r in record["results"]}
    assert record["overall"] == "complete" and by["eia-generation"]["requests"] == 1
    assert by["eia-generation"]["summary"]["rows_new"] == 3 * 24 * len(CATEGORIES)
    assert record["eia_api_requests_budgeted"] == 24 and record["requests_used"] == 6


def test_a_successful_demand_refresh_does_not_imply_generation_was_refreshed(tmp_path, clock):
    cfg = config(**{"sources__eia-generation__enabled": True})
    cs = clients(WindowEIA(), FakeErcot(ercot_docs(date(2026, 3, 9), 3)))
    cs["eia-generation"] = lambda budget: client(FakeGeneration(script=[(403, b"denied")]), budget)
    all_stores = stores(tmp_path) | {"eia-generation": generation.store(tmp_path)}
    record = refresh.refresh(
        cfg,
        ["eia", "eia-generation"],
        data_dir=tmp_path,
        stores=all_stores,
        clients=cs,
        now=clock,
        local_today=clock().date(),
        dry_run=False,
        secrets=[FAKE_KEY],
    )
    by = {r["source"]: r for r in record["results"]}
    assert by["eia"]["status"] == "succeeded" and by["eia-generation"]["status"] == "failed"
    assert record["overall"] == "partial" and refresh.exit_code("partial") == 3
    hs = {h.source: h for h in health.source_health(all_stores, cfg, clock())}
    assert hs["eia"].freshness == health.FRESH
    assert hs["eia-generation"].freshness == health.NO_DATA
    assert (
        hs["eia-generation"].last_attempt["status"] == "failed"
        and hs["eia-generation"].last_success is None
    )
    plan_ = refresh.plan_eia(cfg, all_stores["eia-generation"], clock(), "eia-generation")
    assert {f.kind for f in plan_.findings} >= {refresh.NEVER_COLLECTED, refresh.SOURCE_UNAVAILABLE}
    assert plan_.generation_plan is not None and plan_.eia_plan is None


def test_generation_health_covers_categories_and_goes_stale_by_label(tmp_path, clock):
    run(tmp_path, FakeGeneration(drop={("SUN", "2026-03-08T03")}))
    all_stores = stores(tmp_path) | {"eia-generation": generation.store(tmp_path)}
    h = {x.source: x for x in health.source_health(all_stores, config(), clock())}["eia-generation"]
    assert h.freshness == health.FRESH and h.latest_label == "period 2026-03-09T23 (UTC label)"
    assert h.coverage["BAT"]["negative_values"] == 12 and h.coverage["SUN"]["hours_absent"] == 1
    assert set(h.coverage) == set(CATEGORIES)
    assert any("not zero" in n for n in h.notes)
    later = {
        x.source: x for x in health.source_health(all_stores, config(), clock() + timedelta(days=3))
    }
    assert later["eia-generation"].freshness == health.STALE


# --- exercises -------------------------------------------------------------------------------


def test_exercises_follow_the_snapshot_and_are_invalidated_by_a_revision(tmp_path):
    run(tmp_path)
    obs = load(tmp_path)
    first = {n: ge.generate({"exercise_id": n, "generator": n}, obs, SEL) for n in ge.GENERATORS}
    assert all(e.options[e.answer_index] for e in first.values())
    assert (
        first["largest_category"].options[first["largest_category"].answer_index].startswith("NG")
    )
    assert {e.snapshot_id for e in first.values()} == {calc.snapshot_id(obs, SEL)}
    assert first["negative_meaning"].question.startswith("In this window, BAT")
    run(tmp_path, FakeGeneration(overrides={("NG", "2026-03-08T05"): "19999"}))
    revised = load(tmp_path)
    assert calc.snapshot_id(revised, SEL) != calc.snapshot_id(obs, SEL)
    narrower = calc.Selection("ERCO", "2026-03-08T00", "2026-03-08T23")
    assert calc.snapshot_id(obs, narrower) != calc.snapshot_id(obs, SEL)
    assert isinstance(
        ge.generate({"exercise_id": "x", "generator": "largest_category"}, None, None), Unavailable
    )
    assert isinstance(
        ge.generate({"exercise_id": "x", "generator": "largest_category"}, [], SEL), Unavailable
    )


def test_exercise_questions_never_hardcode_totals_or_categories(tmp_path):
    run(tmp_path, FakeGeneration(categories=("WND", "SUN")))  # no negatives, two categories
    obs = load(tmp_path)
    e = ge.generate({"exercise_id": "n", "generator": "negative_meaning"}, obs, SEL)
    assert e.question.startswith("No category is negative")
    e = ge.generate({"exercise_id": "a", "generator": "absent_category_hours"}, obs, SEL)
    assert e.options[e.answer_index].startswith("0 absent category-hours.")
    e = ge.generate({"exercise_id": "l", "generator": "largest_category"}, obs, SEL)
    assert len(e.options) == 4 and e.options[e.answer_index].startswith("WND")


# --- CLI -------------------------------------------------------------------------------------


def test_cli_dry_run_and_offline_sources_need_no_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    assert (
        cli.main(
            ["--no-dotenv", "collect", "--source", "eia-generation", "--dry-run", "--days", "2"]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "fuel-type-data" in out and "Dry run: no requests sent" in out and "never shown" in out
    assert cli.main(["--no-dotenv", "sources", "--source", "eia-generation"]) == 0
    assert "storage_sign" in capsys.readouterr().out
    assert cli.main(["--no-dotenv", "refresh", "--dry-run", "--source", "eia-generation"]) == 0
    out = capsys.readouterr().out
    assert (
        '"eia_api_requests_budgeted": 0' in out and "disabled in the refresh configuration" in out
    )
    assert not (tmp_path / "data").exists() or not any(
        p.is_file() for p in (tmp_path / "data").rglob("*")
    )
