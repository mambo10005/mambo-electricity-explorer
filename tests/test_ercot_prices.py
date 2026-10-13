"""ERCOT NP4-190-CD DAM Settlement Point Prices at HB_NORTH: contract, collection, refresh, health.

Offline and credential-free. All fixtures are SYNTHETIC (tests/price_fixtures.py).
"""

from __future__ import annotations

from datetime import date

import pytest
from ercot_fixtures import FakeErcot, three_days_docs
from price_fixtures import FakePrices, csv_bytes, day_doc, docs_ending, rows_for, zip_bytes
from refresh_helpers import Clock, clients, config, patch_clock, stores

from mambo_explorer import health, price_exercises, price_view, refresh
from mambo_explorer.ercot import collect as load_collect
from mambo_explorer.ercot import prices as px
from mambo_explorer.ercot.client import AccessError, BudgetExceeded, ErcotClient, ResponseError
from mambo_explorer.exercises import Unavailable

D9, D10 = date(2026, 3, 9), date(2026, 3, 10)


def client(fake, budget=6):
    return ErcotClient(transport=fake, sleep=lambda s: None, max_requests=budget)


def collect(data_dir, docs, selection=None, budget=6):
    return px.collect(
        selection or px.Selection(latest=len(docs) or 1),
        client(FakePrices(docs), budget),
        px.store(data_dir),
    )


def latest(data_dir):
    with px.store(data_dir).query() as con:
        return con.execute(
            "SELECT delivery_date_raw, hour_ending, dst_flag, value_raw, value, quality_flags, "
            "revision, location, market_stage, unit FROM latest ORDER BY delivery_date, row_order"
        ).fetchall()


# --- contract ---------------------------------------------------------------------------------


def test_reviewed_identifiers_are_the_discovered_ones():
    assert (px.DATASET, px.REPORT_TYPE_ID, px.CSV_FRIENDLY_NAME) == (
        "NP4-190-CD",
        "12331",
        "DAMSPNP4190_csv",
    )
    assert px.HEADER == (
        "DeliveryDate",
        "HourEnding",
        "SettlementPoint",
        "SettlementPointPrice",
        "DSTFlag",
    )
    assert px.LOCATION == "HB_NORTH" and "3.5.2.1" in px.LOCATION_NAME
    assert px.UNIT == "$/MWh" and "4.5.3(5)" in px.UNIT_TEXT and "does not state" in px.UNIT_TEXT
    assert "nothing is converted to UTC" in px.TIME_TEXT and "4.5.3(6)" in px.FINALITY_TEXT
    assert px.STORE_NAMESPACE not in ("eia930", "ercot-np6-345-cd", "eia930-fuel-type")
    for field in ("market_stage", "location", "delivery_date_raw", "hour_ending", "dst_flag"):
        assert field in px.IDENTITY


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda b: b.replace(b"SettlementPointPrice", b"Price"), "unexpected header"),
        (lambda b: b.replace(b"03/09/2026", b"2026-03-09", 1), "DeliveryDate"),
        (lambda b: b.replace(b",02:00,", b",2:00,", 1), "HourEnding"),
        (lambda b: b.replace(b",N\n", b",X\n", 1), "DSTFlag"),
        (lambda b: b.replace(b"HB_NORTH", b"HB_ELSEWHERE"), "not in this document"),
        (lambda b: b.split(b"\n")[0] + b"\n", "no data rows"),
    ],
)
def test_schema_and_format_errors_are_rejected(mutate, message):
    with pytest.raises(px.PriceFormatError, match=message):
        px.parse_csv(mutate(csv_bytes(rows_for(D9))))


def test_location_filter_keeps_only_the_hub_and_records_downloaded_scope():
    parsed = px.parse_csv(csv_bytes(rows_for(D9)))
    assert len(parsed.rows) == 24 and parsed.downloaded_rows == 24 * 5
    assert parsed.downloaded_settlement_points == 5 and parsed.delivery_dates == ("03/09/2026",)
    assert [r.hour_ending for r in parsed.rows][:2] == ["01:00", "02:00"]


def test_duplicate_hub_rows_are_refused_but_dst_repeated_hours_are_distinct():
    lines = rows_for(D9)
    dupe = [line for line in lines if line[2] == "HB_NORTH"][1]
    with pytest.raises(px.PriceFormatError, match="duplicate"):
        px.parse_csv(csv_bytes([*lines, dupe]))
    fall_back = rows_for(D9, dst={"02:00": ["N", "Y"]})
    parsed = px.parse_csv(csv_bytes(fall_back))
    assert len(parsed.rows) == 25
    assert [(r.hour_ending, r.dst_flag) for r in parsed.rows if r.hour_ending == "02:00"] == [
        ("02:00", "N"),
        ("02:00", "Y"),
    ]


# --- collection -------------------------------------------------------------------------------


def test_negative_and_missing_prices_are_kept_as_published(tmp_path):
    docs = dict([day_doc(D9, "501", overrides={("05:00", "N"): ""})])
    summary = collect(tmp_path, docs)
    assert summary["stored_scope_rows"] == 24 and summary["downloaded_rows"] == 120
    assert summary["documents"][0]["downloaded_settlement_points"] == 5
    rows = {r[1]: r for r in latest(tmp_path)}
    assert (
        rows["03:00"][3] == "-2.50" and rows["03:00"][4] == -2.5 and "negative" in rows["03:00"][5]
    )
    assert rows["05:00"][3] is None and rows["05:00"][4] is None and "missing" in rows["05:00"][5]
    assert {r[7] for r in rows.values()} == {"HB_NORTH"} and {r[8] for r in rows.values()} == {
        "day-ahead"
    }
    assert {r[9] for r in rows.values()} == {"$/MWh"}


def test_archive_is_byte_identical_and_requests_counted(tmp_path):
    docs = docs_ending(D10, 2)
    summary = collect(tmp_path, docs)
    assert summary["requests"] == 3  # 1 list + 2 downloads
    target = px.store(tmp_path)
    stored = {
        r["path"].rsplit("/", 1)[1]: (target.root / r["path"]).read_bytes()
        for r in target.committed_files("raw")
    }
    assert {f"{i}.zip": z for i, (_, z) in docs.items()} == stored
    assert target.validate()["ok"]


def test_repeat_is_idempotent_and_a_repost_becomes_a_revision(tmp_path):
    collect(tmp_path, dict([day_doc(D9, "501")]))
    again = collect(tmp_path, dict([day_doc(D9, "501")]))
    assert (again["rows_new"], again["rows_revised"], again["rows_unchanged"]) == (0, 0, 24)
    repost = dict(
        [day_doc(D9, "601", "2026-03-08T15:00:00-05:00", overrides={("10:00", "N"): "99.99"})]
    )
    third = collect(tmp_path, repost)
    assert (third["rows_new"], third["rows_revised"]) == (0, 1)
    with px.store(tmp_path).query() as con:
        trail = con.execute(
            "SELECT revision, value_raw, doc_id FROM observations "
            "WHERE hour_ending='10:00' ORDER BY revision"
        ).fetchall()
    assert trail == [(1, "45.00", "501"), (2, "99.99", "601")]


def test_price_store_is_isolated_from_the_load_store(tmp_path):
    load = load_collect.store(tmp_path)
    load_collect.collect(
        load_collect.Selection(latest=3), client(FakeErcot(three_days_docs()), 10), load
    )
    before = load.catalog.read_bytes()
    collect(tmp_path, docs_ending(D10, 2))
    assert load.catalog.read_bytes() == before
    assert px.store(tmp_path).root != load.root


def test_budget_and_access_errors_fail_the_run_and_keep_nothing(tmp_path):
    with pytest.raises(BudgetExceeded):
        collect(tmp_path, docs_ending(D10, 2), budget=2)  # needs 1 list + 2 downloads
    with pytest.raises(AccessError):
        px.collect(
            px.Selection(latest=1),
            client(FakePrices({}, script=[(403, "text/html", b"x")])),
            px.store(tmp_path / "b"),
        )
    assert [r["status"] for r in px.store(tmp_path).runs()] == ["failed"]
    assert not px.store(tmp_path).committed_files("observations")


def test_oversized_or_non_zip_documents_are_refused(tmp_path):
    big = dict([day_doc(D9, "501")])
    published, z = big["501"]
    with pytest.raises(ResponseError, match="not a ZIP"):
        px.collect(
            px.Selection(latest=1),
            client(FakePrices({"501": (published, b"<html>")})),
            px.store(tmp_path),
        )
    two = zip_bytes(csv_bytes(rows_for(D9)))
    assert two.startswith(b"PK")


def test_interrupted_write_is_recoverable(tmp_path, monkeypatch):
    target = px.store(tmp_path)

    def broken(run_id, rows):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(target, "write_observations", broken)
    with pytest.raises(OSError):
        px.collect(px.Selection(latest=1), client(FakePrices(docs_ending(D9, 1))), target)
    report = px.store(tmp_path).validate()
    assert len(report["interrupted"]) == 1 and report["orphans"] and report["ok"]
    fixed = px.store(tmp_path).validate(mark_interrupted=True, quarantine_orphans=True)
    assert fixed["ok"]
    assert collect(tmp_path, docs_ending(D9, 1))["rows_new"] == 24


def test_selection_bounds():
    with pytest.raises(px.SelectionError):
        px.Selection(latest=4)
    with pytest.raises(px.SelectionError):
        px.Selection(latest=1, publish_dates=("2026-03-08",))
    assert "HB_NORTH" in px.Selection(latest=2).describe()["stored_scope"]


# --- refresh and health ------------------------------------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    patch_clock(monkeypatch, c)
    return c


def all_stores(data_dir):
    return stores(data_dir) | {"ercot-dam-spp": px.store(data_dir)}


def price_clients(fake, ercot_fake=None):
    cs = clients(None, ercot_fake)
    cs["ercot-dam-spp"] = lambda budget: client(fake, budget)
    return cs


def test_prices_are_opt_in_and_a_plan_without_the_section_loads():
    assert not config().prices.enabled and "ercot-dam-spp" not in config().enabled()
    assert config().host_budget("ercot.com") == 18
    import yaml

    from mambo_explorer import refresh_config as rc

    data = yaml.safe_load(rc.default_text())
    del data["sources"]["ercot-dam-spp"]
    del data["hosts"]
    c = rc.validate(data)
    assert not c.prices.enabled and c.host_budget("ercot.com") is None


def test_shared_host_budget_skips_a_dataset_that_would_overload_ercot(tmp_path, clock):
    cfg = config(
        **{
            "sources__ercot-dam-spp__enabled": True,
            "hosts__ercot.com__max_requests_per_refresh": 14,
        }
    )
    fake = FakePrices(docs_ending(D10, 2))
    record = refresh.refresh(
        cfg,
        ["ercot", "ercot-dam-spp"],
        data_dir=tmp_path,
        stores=all_stores(tmp_path),
        clients=price_clients(fake),
        now=clock,
        local_today=D9,
        dry_run=True,
        secrets=[],
    )
    plans = {p["source"]: p for p in record["plans"]}
    assert plans["ercot"]["action"] == "collect" and plans["ercot-dam-spp"]["action"] == "skip"
    assert "shared ercot.com budget" in plans["ercot-dam-spp"]["reason"]
    assert record["host_requests_budgeted"] == {"ercot.com": {"budgeted": 12, "cap": 14}}
    assert fake.urls == []


def test_a_budget_above_the_host_cap_is_rejected():
    from mambo_explorer import refresh_config as rc

    with pytest.raises(rc.RefreshConfigError, match="exceeds hosts.ercot.com"):
        config(
            **{
                "sources__ercot-dam-spp__enabled": True,
                "hosts__ercot.com__max_requests_per_refresh": 5,
            }
        )


def test_partial_refresh_keeps_load_and_records_price_failure(tmp_path, clock):
    cfg = config(**{"sources__ercot-dam-spp__enabled": True})
    denied = FakePrices({}, script=[(403, "text/html", b"denied")])
    record = refresh.refresh(
        cfg,
        ["ercot", "ercot-dam-spp"],
        data_dir=tmp_path,
        stores=all_stores(tmp_path),
        clients=price_clients(denied, FakeErcot(three_days_docs())),
        now=clock,
        local_today=D9,
        dry_run=False,
        secrets=[],
    )
    by = {r["source"]: r for r in record["results"]}
    assert by["ercot"]["status"] == "succeeded" and by["ercot-dam-spp"]["status"] == "failed"
    assert record["overall"] == "partial" and refresh.exit_code("partial") == 3
    hs = {h.source: h for h in health.source_health(all_stores(tmp_path), cfg, clock())}
    assert hs["ercot-dam-spp"].freshness == health.NO_DATA
    assert hs["ercot-dam-spp"].last_attempt["status"] == "failed"


def test_price_refresh_plans_from_delivery_dates_and_never_claims_finality(tmp_path, clock):
    cfg = config(**{"sources__ercot-dam-spp__enabled": True})
    first = refresh.refresh(
        cfg,
        ["ercot-dam-spp"],
        data_dir=tmp_path,
        stores=all_stores(tmp_path),
        clients=price_clients(FakePrices(docs_ending(D10, 2))),
        now=clock,
        local_today=D9,
        dry_run=False,
        secrets=[],
    )
    assert first["overall"] == "complete" and first["results"][0]["requests"] == 3
    kinds = {f["kind"] for f in first["plans"][0]["findings"]}
    assert {"never-collected", "finality-not-determined"} <= kinds
    plan = refresh.plan_ercot(cfg, px.store(tmp_path), clock(), D9, "ercot-dam-spp")
    assert plan.price_selection.latest == 1  # nothing newer than tomorrow (D10): lookback only
    plan = refresh.plan_ercot(cfg, px.store(tmp_path), clock(), date(2026, 3, 12), "ercot-dam-spp")
    assert plan.price_selection.latest == 3  # D11, D12, D13 expected + 1 lookback, capped at 3
    h = {x.source: x for x in health.source_health(all_stores(tmp_path), cfg, clock())}[
        "ercot-dam-spp"
    ]
    assert h.latest_label.startswith("DeliveryDate 03/10/2026, HourEnding 24:00")
    assert (
        h.coverage["HB_NORTH"]["negative_prices"] == 4
        and h.coverage["HB_NORTH"]["delivery_dates_present"] == 2
    )
    assert any("Finality: Not determined" in n for n in h.notes)
    assert h.publication_time.startswith("2026-03-09T12:46:27-05:00")


# --- exercises -----------------------------------------------------------------------------


def test_exercises_follow_the_snapshot_and_a_revision_invalidates_them(tmp_path):
    collect(tmp_path, dict([day_doc(D9, "501")]))
    target = px.store(tmp_path)
    hours = price_view.load_day(target, "03/09/2026")
    ex = {
        n: price_exercises.generate({"exercise_id": n, "generator": n}, "03/09/2026", hours)
        for n in price_exercises.GENERATORS
    }
    assert all(not isinstance(e, Unavailable) for e in ex.values())
    assert ex["highest_hour"].options[ex["highest_hour"].answer_index].startswith("23:00 N: 64.50")
    assert ex["negative_count"].options[ex["negative_count"].answer_index].startswith("2,")
    assert len({e.snapshot_id for e in ex.values()}) == 1
    collect(
        tmp_path,
        dict(
            [day_doc(D9, "601", "2026-03-08T15:00:00-05:00", overrides={("10:00", "N"): "99.99"})]
        ),
    )
    revised = price_view.load_day(target, "03/09/2026")
    assert price_view.snapshot_id("03/09/2026", revised) != ex["highest_hour"].snapshot_id
    new = price_exercises.generate(
        {"exercise_id": "h", "generator": "highest_hour"}, "03/09/2026", revised
    )
    assert new.options[new.answer_index].startswith("10:00 N: 99.99")
    assert isinstance(
        price_exercises.generate({"exercise_id": "h", "generator": "highest_hour"}, None, None),
        Unavailable,
    )
