"""ERCOT NP6-905-CD real-time Settlement Point Prices at HB_NORTH (offline, SYNTHETIC fixtures)."""

from __future__ import annotations

from datetime import date

import pytest
from ercot_fixtures import FakeErcot, three_days_docs
from price_fixtures import FakePrices, docs_ending
from refresh_helpers import Clock, clients, config, patch_clock, stores
from rt_price_fixtures import FakeRt, csv_for, day_docs, interval_doc, zip_bytes

from mambo_explorer import health, refresh, rt_price_exercises, rt_price_view
from mambo_explorer.ercot import prices as dam
from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.client import AccessError, BudgetExceeded, ErcotClient
from mambo_explorer.exercises import Unavailable

D9 = date(2026, 3, 9)


def client(fake, budget=12):
    return ErcotClient(transport=fake, sleep=lambda s: None, max_requests=budget)


def collect(data_dir, docs, latest=8, include_stored=False, budget=12):
    return rt.collect(
        rt.Selection(latest, include_stored), client(FakeRt(docs), budget), rt.store(data_dir)
    )


def stored(data_dir):
    with rt.store(data_dir).query() as con:
        return con.execute(
            "SELECT delivery_date_raw, delivery_hour, delivery_interval, dst_flag, value_raw, "
            "value, quality_flags, revision, interval_minutes, market_stage, location, unit "
            "FROM latest ORDER BY CAST(delivery_hour AS INT), CAST(delivery_interval AS INT), "
            "dst_flag"
        ).fetchall()


# --- contract ---------------------------------------------------------------------------------


def test_reviewed_identifiers_and_price_definition():
    assert (rt.DATASET, rt.REPORT_TYPE_ID) == ("NP6-905-CD", "12301")
    assert rt.HEADER == (
        "DeliveryDate",
        "DeliveryHour",
        "DeliveryInterval",
        "SettlementPointName",
        "SettlementPointType",
        "SettlementPointPrice",
        "DSTFlag",
    )
    assert (
        rt.INTERVAL_MINUTES == 15 and rt.MARKET_STAGE == "real-time" and rt.LOCATION == "HB_NORTH"
    )
    assert (
        "SCED LMPs" in rt.PRICE_DEFINITION
        and "Adder" in rt.PRICE_DEFINITION
        and "-$251" in rt.PRICE_DEFINITION
    )
    assert "6.3(7)" in rt.FINALITY_TEXT and "NP4-197-M" in rt.FINALITY_TEXT
    assert "no clock time or UTC boundary" in rt.TIME_TEXT
    assert rt.REPORT.is_csv("SPPHLZNP6905_20261013_0015_csv") and not rt.REPORT.is_csv(
        "SPPHLZNP6905_20261013_0015_xml"
    )
    assert rt.STORE_NAMESPACE != dam.STORE_NAMESPACE
    for f in (
        "market_stage",
        "location",
        "delivery_date_raw",
        "delivery_hour",
        "delivery_interval",
        "dst_flag",
    ):
        assert f in rt.IDENTITY


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda b: b.replace(b"DeliveryInterval", b"Interval"), "unexpected header"),
        (lambda b: b.replace(b",1,2,HB_NORTH", b",25,2,HB_NORTH"), "DeliveryHour"),
        (lambda b: b.replace(b",1,2,HB_NORTH", b",1,5,HB_NORTH"), "DeliveryInterval"),
        (lambda b: b.replace(b",N\n", b",Q\n", 1), "DSTFlag"),
        (lambda b: b.replace(b"HB_NORTH,HU", b"HB_NORTH,LZ"), "with type 'HU' is not"),
        (lambda b: b.replace(b"HB_NORTH", b"HB_ELSE"), "not in this document"),
        (lambda b: b.replace(b",1,2,HB_SOUTH", b",1,3,HB_SOUTH"), "covers 2 intervals"),
        (lambda b: b + b"03/09/2026,1,2,HB_NORTH,HU,1.00,N\n", "duplicate row"),
    ],
)
def test_schema_and_interval_errors_are_rejected(mutate, message):
    with pytest.raises(rt.RtFormatError, match=message):
        rt.parse_csv(mutate(csv_for(D9, 1, 2)))


def test_same_name_with_different_types_is_valid_as_in_the_live_file():
    extra = [
        ("03/09/2026", "1", "2", "LZ_AEN", "LZ", "38.40", "N"),
        ("03/09/2026", "1", "2", "LZ_AEN", "LZEW", "38.40", "N"),
        ("03/09/2026", "1", "2", "HB_NORTH", "LZ", "1.00", "N"),  # only type HU is the hub row
    ]
    p = rt.parse_csv(csv_for(D9, 1, 2, extra=extra))
    assert p.downloaded_rows == 7 and p.downloaded_settlement_points == 5
    assert p.settlement_point_type == "HU" and p.value_raw == "21.75"


def test_parse_keeps_the_complete_interval_identity_and_downloaded_scope():
    p = rt.parse_csv(csv_for(D9, 7, 3, dst="Y"))
    assert (p.delivery_date_raw, p.delivery_hour, p.delivery_interval, p.dst_flag) == (
        "03/09/2026",
        "7",
        "3",
        "Y",
    )
    assert (
        p.settlement_point_type == "HU"
        and p.downloaded_rows == 4
        and p.downloaded_settlement_points == 4
    )


# --- collection -------------------------------------------------------------------------------


def test_negative_missing_filtered_and_idempotent(tmp_path):
    docs = day_docs(D9, hours=(3, 4))
    docs.update(dict([interval_doc(D9, 5, 1, "7900", price="")]))
    first = collect(tmp_path, docs, latest=9)
    assert (
        first["status"] == "collected"
        and first["stored_scope_rows"] == 9
        and first["downloaded_rows"] == 36
    )
    assert first["requests"] == 10  # 1 list + 9 downloads
    rows = stored(tmp_path)
    assert len(rows) == 9 and {r[8] for r in rows} == {15} and {r[9] for r in rows} == {"real-time"}
    assert {r[10] for r in rows} == {"HB_NORTH"} and {r[11] for r in rows} == {"$/MWh"}
    four = [r for r in rows if r[1] == "4"]
    assert [r[4] for r in four] == ["-4.00", "-5.00", "-6.00", "-7.00"] and all(
        "negative" in r[6] for r in four
    )
    blank = next(r for r in rows if r[1] == "5")
    assert blank[4] is None and blank[5] is None and "missing" in blank[6]
    again = collect(tmp_path, docs, latest=9)
    assert again["status"] == "no newer document published yet" and again["requests"] == 1
    recheck = collect(tmp_path, docs, latest=9, include_stored=True)
    assert (recheck["rows_new"], recheck["rows_revised"], recheck["rows_unchanged"]) == (0, 0, 9)


def test_dst_twin_intervals_are_distinct_and_no_day_length_is_assumed(tmp_path):
    docs = dict(
        [interval_doc(D9, 2, 1, "8001"), interval_doc(D9, 2, 1, "8002", dst="Y", price="31.00")]
    )
    collect(tmp_path, docs)
    rows = stored(tmp_path)
    assert [(r[1], r[2], r[3]) for r in rows] == [("2", "1", "N"), ("2", "1", "Y")]
    intervals = rt_price_view.load_day(rt.store(tmp_path), "03/09/2026")
    assert [x.label for x in intervals] == ["H02 I1 N", "H02 I1 Y"]
    cov = rt_price_view.coverage(intervals)
    assert (
        cov["stored"] == 2
        and cov["hours_with_fewer_than_4"] == [2]
        and cov["dst_flags"] == ["N", "Y"]
    )


def test_catch_up_is_bounded_and_reports_what_it_leaves(tmp_path):
    docs = day_docs(D9, hours=(1, 2, 3))  # 12 published intervals
    first = collect(tmp_path, docs, latest=8)
    assert first["status"] == "partial catch-up"
    assert (
        first["scope"]["listed_documents"] == 12 and first["scope"]["published_not_requested"] == 4
    )
    assert first["scope"]["oldest_listed_publish_time"] is not None
    second = collect(tmp_path, docs, latest=8)
    assert second["stored_scope_rows"] == 4 and second["scope"]["already_stored_documents"] == 8


def test_repost_becomes_a_revision_with_lineage(tmp_path):
    collect(tmp_path, dict([interval_doc(D9, 6, 2, "8101")]))
    repost = dict(
        [interval_doc(D9, 6, 2, "8102", published="2026-03-09T09:00:00-05:00", price="88.88")]
    )
    summary = collect(tmp_path, repost)
    assert summary["rows_revised"] == 1
    with rt.store(tmp_path).query() as con:
        trail = con.execute(
            "SELECT revision, value_raw, doc_id FROM observations ORDER BY revision"
        ).fetchall()
    assert trail == [(1, "28.00", "8101"), (2, "88.88", "8102")]


def test_real_time_and_day_ahead_stores_are_isolated(tmp_path):
    dam.collect(
        dam.Selection(latest=1), client(FakePrices(docs_ending(D9, 1)), 6), dam.store(tmp_path)
    )
    before = dam.store(tmp_path).catalog.read_bytes()
    collect(tmp_path, day_docs(D9))
    assert (
        dam.store(tmp_path).catalog.read_bytes() == before
        and rt.store(tmp_path).root != dam.store(tmp_path).root
    )


def test_budget_access_and_recovery(tmp_path, monkeypatch):
    with pytest.raises(BudgetExceeded):
        collect(tmp_path, day_docs(D9), latest=8, budget=4)
    assert [r["status"] for r in rt.store(tmp_path).runs()] == ["failed"]
    with pytest.raises(AccessError):
        rt.collect(
            rt.Selection(2),
            client(FakeRt({}, script=[(403, "text/html", b"x")])),
            rt.store(tmp_path / "b"),
        )
    target = rt.store(tmp_path / "c")

    def broken(run_id, rows):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(target, "write_observations", broken)
    with pytest.raises(OSError):
        rt.collect(rt.Selection(2), client(FakeRt(day_docs(D9))), target)
    report = rt.store(tmp_path / "c").validate()
    assert len(report["interrupted"]) == 1 and report["orphans"] and report["ok"]
    assert rt.store(tmp_path / "c").validate(mark_interrupted=True, quarantine_orphans=True)["ok"]
    assert collect(tmp_path / "c", day_docs(D9), latest=2)["rows_new"] == 2


def test_non_zip_and_selection_bounds(tmp_path):
    docs = {"1": ("2026-03-09T00:17:01-05:00", "SPPHLZNP6905_20260309_0015_csv", b"<html>")}
    from mambo_explorer.ercot.client import ResponseError

    with pytest.raises(ResponseError, match="not a ZIP"):
        collect(tmp_path, docs)
    with pytest.raises(rt.SelectionError):
        rt.Selection(17)
    assert zip_bytes(csv_for(D9, 1, 1)).startswith(b"PK")


# --- refresh and health ------------------------------------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    patch_clock(monkeypatch, c)
    return c


def all_stores(d):
    return stores(d) | {"ercot-dam-spp": dam.store(d), "ercot-rt-spp": rt.store(d)}


def rt_clients(rt_fake, dam_fake=None, load_fake=None):
    cs = clients(None, load_fake)
    cs["ercot-rt-spp"] = lambda budget: client(rt_fake, budget)
    cs["ercot-dam-spp"] = lambda budget: client(dam_fake or FakePrices({}), budget)
    return cs


def test_opt_in_and_shared_cap_is_not_raised():
    c = config()
    assert (
        not c.rt_prices.enabled
        and "ercot-rt-spp" not in c.enabled()
        and c.host_budget("ercot.com") == 18
    )
    import yaml

    from mambo_explorer import refresh_config as rc

    data = yaml.safe_load(rc.default_text())
    del data["sources"]["ercot-rt-spp"]
    assert not rc.validate(data).rt_prices.enabled


def test_all_three_ercot_datasets_respect_the_shared_host_cap(tmp_path, clock):
    cfg = config(
        **{"sources__ercot-dam-spp__enabled": True, "sources__ercot-rt-spp__enabled": True}
    )
    record = refresh.refresh(
        cfg,
        ["ercot", "ercot-dam-spp", "ercot-rt-spp"],
        data_dir=tmp_path,
        stores=all_stores(tmp_path),
        clients=rt_clients(FakeRt(day_docs(D9))),
        now=clock,
        local_today=D9,
        dry_run=True,
        secrets=[],
    )
    plans = {p["source"]: p for p in record["plans"]}
    assert plans["ercot"]["action"] == "collect" and plans["ercot-dam-spp"]["action"] == "collect"
    assert (
        plans["ercot-rt-spp"]["action"] == "skip"
        and "shared ercot.com budget" in plans["ercot-rt-spp"]["reason"]
    )
    assert record["host_requests_budgeted"] == {"ercot.com": {"budgeted": 18, "cap": 18}}


def test_partial_refresh_and_rt_health_states(tmp_path, clock):
    # Load (12) + real-time (10) exceeds the default ercot.com cap (18); raise it explicitly.
    cfg = config(
        **{
            "sources__ercot-rt-spp__enabled": True,
            "hosts__ercot.com__max_requests_per_refresh": 22,
        }
    )
    denied = FakeRt({}, script=[(403, "text/html", b"denied")])
    record = refresh.refresh(
        cfg,
        ["ercot", "ercot-rt-spp"],
        data_dir=tmp_path,
        stores=all_stores(tmp_path),
        clients=rt_clients(denied, load_fake=FakeErcot(three_days_docs())),
        now=clock,
        local_today=D9,
        dry_run=False,
        secrets=[],
    )
    by = {r["source"]: r for r in record["results"]}
    assert by["ercot"]["status"] == "succeeded" and by["ercot-rt-spp"]["status"] == "failed"
    assert record["overall"] == "partial"
    hs = {h.source: h for h in health.source_health(all_stores(tmp_path), cfg, clock())}
    assert (
        hs["ercot-rt-spp"].freshness == health.NO_DATA
        and hs["ercot-rt-spp"].last_attempt["status"] == "failed"
    )
    ok = refresh.refresh(
        cfg,
        ["ercot-rt-spp"],
        data_dir=tmp_path,
        stores=all_stores(tmp_path),
        clients=rt_clients(FakeRt(day_docs(D9))),
        now=clock,
        local_today=D9,
        dry_run=False,
        secrets=[],
    )
    assert (
        ok["overall"] == "complete" and ok["results"][0]["summary"]["stored_scope_rows"] == 4
    )  # window 4
    kinds = {f["kind"] for f in ok["plans"][0]["findings"]}
    assert {"never-collected", "outside-available-history", "finality-not-determined"} <= kinds
    from datetime import UTC, datetime

    h = {
        x.source: x
        for x in health.source_health(
            all_stores(tmp_path), cfg, datetime(2026, 3, 9, 7, 0, tzinfo=UTC)
        )
    }["ercot-rt-spp"]
    assert h.freshness == health.FRESH and h.latest_label.startswith(
        "DeliveryDate 03/09/2026, DeliveryHour 2, DeliveryInterval 4"
    )
    assert h.coverage["HB_NORTH"]["intervals_stored"] == 4 and any(
        "not compared with 96" in n for n in h.notes
    )
    later = {
        x.source: x
        for x in health.source_health(
            all_stores(tmp_path), cfg, datetime(2026, 3, 9, 12, 0, tzinfo=UTC)
        )
    }
    assert later["ercot-rt-spp"].freshness == health.STALE  # threshold 2 h by publication time


# --- exercises -----------------------------------------------------------------------------


def test_exercises_follow_the_snapshot_and_stale_answers_are_invalidated(tmp_path):
    collect(tmp_path, day_docs(D9, hours=(3, 4)))
    target = rt.store(tmp_path)
    xs = rt_price_view.load_day(target, "03/09/2026")
    ex = {
        n: rt_price_exercises.generate({"exercise_id": n, "generator": n}, "03/09/2026", xs)
        for n in rt_price_exercises.GENERATORS
    }
    assert all(not isinstance(e, Unavailable) for e in ex.values())
    assert (
        ex["highest_interval"]
        .options[ex["highest_interval"].answer_index]
        .startswith("H03 I4 N: 24.75")
    )
    assert ex["negative_count"].options[ex["negative_count"].answer_index].startswith("4,")
    collect(tmp_path, dict([interval_doc(D9, 5, 1, "7999")]))  # a new interval arrives
    grown = rt_price_view.load_day(target, "03/09/2026")
    assert rt_price_view.snapshot_id("03/09/2026", grown) != ex["highest_interval"].snapshot_id
    assert isinstance(
        rt_price_exercises.generate(
            {"exercise_id": "x", "generator": "highest_interval"}, None, None
        ),
        Unavailable,
    )
