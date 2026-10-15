"""ERCOT NP6-345-CD connector. All data is SYNTHETIC (tests/ercot_fixtures.py)."""

import io
import os
import zipfile
from datetime import UTC, date, datetime

import pytest
from ercot_fixtures import FakeErcot, csv_bytes, day_doc, document, listing, rows_for, zip_bytes

from mambo_explorer.ercot import dataset as ds
from mambo_explorer.ercot.client import (
    AccessError,
    BudgetExceeded,
    ErcotClient,
    ResponseError,
    UnavailableError,
)
from mambo_explorer.ercot.collect import Selection, SelectionError, collect, store
from mambo_explorer.storage import Store

D1, D2, D3 = date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 10)


def client(fake, **kw) -> ErcotClient:
    return ErcotClient(transport=fake, sleep=lambda s: None, **kw)


def three_days():
    return dict(
        [
            day_doc(D1, "101", "2026-10-09T05:50:00-05:00"),
            day_doc(D2, "102", "2026-10-10T05:50:00-05:00"),
            day_doc(D3, "103", "2026-10-11T05:50:00-05:00"),
        ]
    )


# --- parsing and schema --------------------------------------------------------------------


def test_parse_valid_day_keeps_original_labels():
    rows = ds.parse_csv(csv_bytes(rows_for(D3)))
    assert len(rows) == 24
    assert (rows[0].oper_day, rows[0].hour_ending, rows[0].dst_flag) == ("10/10/2026", "01:00", "N")
    assert rows[-1].hour_ending == "24:00" and rows[0].oper_date == D3
    assert set(rows[0].values) == {*ds.ZONES, "TOTAL"}


@pytest.mark.parametrize(
    "header, message",
    [
        (tuple(h for h in ds.HEADER if h != "WEST"), "missing \\['WEST'\\]"),
        ((*ds.HEADER, "NEW_ZONE"), "extra \\['NEW_ZONE'\\]"),
        (tuple(h.replace("COAST", "Coast") for h in ds.HEADER), "missing \\['COAST'\\]"),
        (("HourEnding", "OperDay", *ds.HEADER[2:]), "order differs"),
    ],
)
def test_schema_changes_are_rejected(header, message):
    with pytest.raises(ds.ReportFormatError, match=message):
        ds.parse_csv(csv_bytes([], header=header) + b"x\n")


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: r.pop(), "fields"),
        (lambda r: r.__setitem__(0, "2026-10-10"), "bad OperDay"),
        (lambda r: r.__setitem__(0, "02/30/2026"), "invalid date"),
        (lambda r: r.__setitem__(1, "25:00"), "bad HourEnding"),
        (lambda r: r.__setitem__(1, "01:30"), "bad HourEnding"),
        (lambda r: r.__setitem__(-1, "X"), "bad DSTFlag"),
    ],
)
def test_malformed_rows_are_rejected(mutate, message):
    lines = rows_for(D3)
    mutate(lines[3])
    with pytest.raises(ds.ReportFormatError, match=message):
        ds.parse_csv(csv_bytes(lines))


def test_other_malformed_files():
    with pytest.raises(ds.ReportFormatError, match="empty"):
        ds.parse_csv(b"")
    with pytest.raises(ds.ReportFormatError, match="no data rows"):
        ds.parse_csv(csv_bytes([]))
    with pytest.raises(ds.ReportFormatError, match="UTF-8"):
        ds.parse_csv(b"\xff\xfe\x00")
    two_days = rows_for(D2) + rows_for(D3)
    with pytest.raises(ds.ReportFormatError, match="more than one OperDay"):
        ds.parse_csv(csv_bytes(two_days))


def test_duplicate_labels_are_rejected():
    lines = rows_for(D3)
    lines.append(list(lines[5]))
    with pytest.raises(ds.ReportFormatError, match="duplicate row"):
        ds.parse_csv(csv_bytes(lines))


def test_dst_fall_back_repeated_hour_is_kept_as_two_rows():
    lines = rows_for(D3, dst={"02:00": ["N", "Y"]})
    rows = ds.parse_csv(csv_bytes(lines))
    assert len(rows) == 25
    twins = [r for r in rows if r.hour_ending == "02:00"]
    assert [r.dst_flag for r in twins] == ["N", "Y"] and twins[0].values != twins[1].values


def test_dst_spring_forward_missing_hour_is_not_invented():
    hours = [f"{h:02d}:00" for h in range(1, 25) if h != 3]
    rows = ds.parse_csv(csv_bytes(rows_for(D3, hours=hours)))
    assert len(rows) == 23 and "03:00" not in {r.hour_ending for r in rows}


def test_values_nulls_and_flags_without_imputation():
    overrides = {("05:00", "N"): {"EAST": "", "WEST": "n/a", "COAST": "-1.50"}}
    rows = ds.parse_csv(csv_bytes(rows_for(D3, overrides=overrides)))
    raw = rows[4].values
    assert ds.parse_value(raw["EAST"]) == (None, ["missing"])
    assert ds.parse_value(raw["WEST"]) == (None, ["non_numeric"])
    assert ds.parse_value(raw["COAST"]) == (-1.5, ["negative"])
    assert ds.zone_sum_minus_total(raw) is None  # not computed over missing zones


def test_total_is_provided_and_zone_sum_is_only_a_diagnostic():
    rows = ds.parse_csv(csv_bytes(rows_for(D3, total_offset=2.5)))
    assert ds.zone_sum_minus_total(rows[0].values) == pytest.approx(-2.5)


def test_publish_time_requires_offset():
    assert ds.parse_publish_time("2026-10-11T05:50:00-05:00") == datetime(
        2026, 10, 11, 10, 50, tzinfo=UTC
    )
    with pytest.raises(ds.ReportFormatError, match="no UTC offset"):
        ds.parse_publish_time("2026-10-11T05:50:00")


# --- client ------------------------------------------------------------------------------


def test_listing_keeps_only_public_csv_documents_oldest_first():
    docs = client(FakeErcot(three_days())).list_documents()
    assert [d.doc_id for d in docs] == ["101", "102", "103"]
    assert all(d.publish_time_raw.endswith("-05:00") for d in docs)


@pytest.mark.parametrize(
    "response, message",
    [
        ((200, "text/html", b"<html>maintenance</html>"), "not JSON"),
        ((200, "application/json", b'{"unexpected": 1}'), "expected JSON structure"),
        (
            (
                200,
                "application/json",
                listing([document("1", "2026-10-11T05:50:00-05:00", security="X")]),
            ),
            "unexpected document metadata",
        ),
        (
            (200, "application/json", listing([document("abc", "2026-10-11T05:50:00-05:00")])),
            "invalid DocID",
        ),
        (
            (200, "application/json", listing([document("1", "2026-10-11T05:50:00")])),
            "no UTC offset",
        ),
    ],
)
def test_bad_listing_is_rejected(response, message):
    with pytest.raises((ResponseError, ds.ReportFormatError), match=message):
        client(FakeErcot({}, script=[response])).list_documents()


def test_download_rejects_html_oversize_and_bad_archives():
    good = three_days()
    c = client(FakeErcot(good, script=[(200, "text/html", b"<html>login</html>")]))
    doc = client(FakeErcot(good)).list_documents()[0]
    with pytest.raises(ResponseError, match="not a ZIP"):
        c.download_csv(doc)
    big = type(doc)(doc.doc_id, doc.name, doc.publish_time_raw, 10_000_000)
    with pytest.raises(ResponseError, match="declares"):
        client(FakeErcot(good)).download_csv(big)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("a.csv", "x")
        z.writestr("../b.csv", "y")
    two_members = buffer.getvalue()
    with pytest.raises(ResponseError, match="members; limit|unsafe"):
        client(FakeErcot({"7": ("2026-10-11T05:50:00-05:00", two_members)})).download_csv(
            type(doc)("7", "x", "2026-10-11T05:50:00-05:00", 100)
        )


def test_access_denied_and_unavailable_are_clear_errors():
    with pytest.raises(AccessError, match="will not register or accept terms"):
        client(FakeErcot({}, script=[(401, "text/html", b"denied")])).list_documents()
    doc = client(FakeErcot(three_days())).list_documents()[0]
    with pytest.raises(UnavailableError, match="expired"):
        client(FakeErcot({})).download_csv(doc)


def test_retries_budget_and_politeness_pause():
    sleeps = []
    fake = FakeErcot(three_days(), script=[(503, "", b""), TimeoutError("slow")])
    c = ErcotClient(transport=fake, sleep=sleeps.append, max_retries=2)
    c.list_documents()
    assert c.stats.requests == 3 and c.stats.retries == 2
    assert 1.0 in sleeps  # pause between requests


def test_request_budget_is_enforced():
    c = ErcotClient(transport=FakeErcot(three_days()), sleep=lambda s: None, max_requests=1)
    docs = c.list_documents()
    with pytest.raises(BudgetExceeded):
        c.download_csv(docs[0])


def test_client_never_uses_eia_credential(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "fake-eia-key-must-not-leak")
    fake = FakeErcot(three_days())
    c = client(fake)
    c.download_csv(c.list_documents()[0])
    assert all("fake-eia-key" not in u and "api_key" not in u for u in fake.urls)
    assert "fake-eia-key" not in repr(c.stats)


# --- selection, storage, isolation, revisions, recovery ------------------------------------


def test_selection_bounds():
    with pytest.raises(SelectionError):
        Selection(latest=0)
    with pytest.raises(SelectionError):
        Selection(latest=8)
    with pytest.raises(SelectionError, match="either"):
        Selection(latest=2, publish_dates=("2026-10-10",))
    docs = client(FakeErcot(three_days())).list_documents()
    assert [d.doc_id for d in Selection(latest=2).apply(docs)] == ["102", "103"]
    assert [
        d.doc_id for d in Selection(latest=None, publish_dates=("2026-10-10",)).apply(docs)
    ] == ["102"]
    with pytest.raises(UnavailableError, match="no public NP6-345-CD CSV"):
        Selection(latest=None, publish_dates=("2026-09-01",)).apply(docs)


def _collect(data_dir, docs, selection=None):
    selection = selection or Selection(latest=3)
    return collect(selection, client(FakeErcot(docs)), store(data_dir))


def test_collect_stores_raw_zip_byte_identical_and_observations(tmp_path):
    docs = three_days()
    summary = _collect(tmp_path, docs)
    assert summary["rows_new"] == 3 * 24 * 9 and summary["requests"] == 4
    target = store(tmp_path)
    raws = target.committed_files("raw")
    assert sorted(r["path"].rsplit("/", 1)[1] for r in raws) == ["101.zip", "102.zip", "103.zip"]
    stored = (target.root / raws[0]["path"]).read_bytes()
    assert stored in {z for _, z in docs.values()} and raws[0]["sanitized"] == 0
    with target.query() as con:
        row = con.execute(
            "SELECT oper_day, hour_ending, dst_flag, entity, value_raw, unit, doc_id, "
            "publish_time_raw, CAST(publication_time_utc AS VARCHAR), zone_sum_minus_total "
            "FROM latest "
            "WHERE entity='TOTAL' AND oper_day='10/10/2026' AND hour_ending='01:00'"
        ).fetchone()
    assert row[:4] == ("10/10/2026", "01:00", "N", "TOTAL")
    assert row[5] == ds.UNIT and row[6] == "103" and row[7] == "2026-10-11T05:50:00-05:00"
    assert row[8].startswith("2026-10-11 10:50:00")  # offset applied: 05:50 -05:00 = 10:50 UTC
    assert row[9] == pytest.approx(0.0, abs=1e-6)


def test_repeat_collection_is_idempotent(tmp_path):
    docs = three_days()
    _collect(tmp_path, docs)
    again = _collect(tmp_path, docs)
    assert again["rows_new"] == 0 and again["rows_revised"] == 0
    assert again["rows_unchanged"] == 3 * 24 * 9


def test_reposted_document_with_changed_value_becomes_revision_with_lineage(tmp_path):
    first = dict([day_doc(D3, "103", "2026-10-11T05:50:00-05:00")])
    _collect(tmp_path, first, Selection(latest=1))
    repost = dict(
        [
            day_doc(
                D3,
                "203",
                "2026-10-11T14:00:00-05:00",
                overrides={("01:00", "N"): {"TOTAL": "99999.00"}},
            )
        ]
    )
    summary = _collect(tmp_path, repost, Selection(latest=1))
    assert summary["rows_revised"] == 1
    with store(tmp_path).query() as con:
        history = con.execute(
            "SELECT revision, value_raw, doc_id FROM observations WHERE entity='TOTAL' "
            "AND hour_ending='01:00' ORDER BY revision"
        ).fetchall()
    assert [h[0] for h in history] == [1, 2] and history[1][1:] == ("99999.00", "203")


def test_dst_twins_are_distinct_identities_in_storage(tmp_path):
    docs = dict([day_doc(D3, "301", "2026-10-11T05:50:00-05:00", dst={"02:00": ["N", "Y"]})])
    summary = _collect(tmp_path, docs, Selection(latest=1))
    assert summary["rows_new"] == 25 * 9
    with store(tmp_path).query() as con:
        flags = con.execute(
            "SELECT dst_flag FROM latest WHERE entity='TOTAL' AND "
            "hour_ending='02:00' ORDER BY row_order"
        ).fetchall()
    assert flags == [("N",), ("Y",)]


def test_source_isolation_from_eia(tmp_path):
    from eia_fixtures import FAKE_KEY, FakeEIA, synthetic_rows

    from mambo_explorer.collect import collect as eia_collect
    from mambo_explorer.collect import plan_collection
    from mambo_explorer.eia.client import EIAClient

    plan = plan_collection(days=1, lookback_days=0, today=date(2026, 10, 11))
    eia_collect(
        plan,
        EIAClient(
            FAKE_KEY,
            transport=FakeEIA(synthetic_rows(plan.fetch_start_day, 1)),
            sleep=lambda s: None,
        ),
        Store(tmp_path),
    )
    with Store(tmp_path).query() as con:
        eia_before = con.execute("SELECT count(*) FROM observations").fetchone()[0]
    _collect(tmp_path, three_days())
    eia, ercot = Store(tmp_path), store(tmp_path)
    assert eia.root != ercot.root and eia.catalog != ercot.catalog
    assert eia.lock_path != ercot.lock_path
    with eia.query() as con:
        assert con.execute("SELECT count(*) FROM observations").fetchone()[0] == eia_before
        assert con.execute("SELECT count(DISTINCT source) FROM observations").fetchone()[0] == 1
    with ercot.query() as con:
        assert con.execute("SELECT DISTINCT source FROM observations").fetchall() == [("ERCOT",)]
    assert eia.validate()["ok"] and ercot.validate()["ok"]
    assert eia.validate()["orphans"] == [] and ercot.validate()["orphans"] == []


def test_failure_before_commit_is_invisible_and_recoverable(tmp_path, monkeypatch):
    docs = three_days()
    with monkeypatch.context() as m:
        m.setattr(Store, "commit_run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash")))
        with pytest.raises(RuntimeError):
            _collect(tmp_path, docs)
    target = store(tmp_path)
    with target.query() as con:
        assert con.execute("SELECT count(*) FROM latest").fetchone()[0] == 0
    report = target.validate()
    assert report["interrupted"] and report["orphans"] and not target.lock_path.exists()
    assert _collect(tmp_path, docs)["rows_new"] == 3 * 24 * 9


def test_format_error_marks_run_failed(tmp_path):
    bad = {"500": ("2026-10-11T05:50:00-05:00", zip_bytes(b"not,the,header\n1,2,3\n"))}
    with pytest.raises(ds.ReportFormatError):
        _collect(tmp_path, bad, Selection(latest=1))
    assert store(tmp_path).runs()[0]["status"] == "failed"


def test_concurrent_writer_rejected(tmp_path):
    from mambo_explorer.storage import WriterLockError

    target = store(tmp_path)
    with target.writer_lock(), pytest.raises(WriterLockError):
        _collect(tmp_path, three_days())


def test_no_env_credentials_needed(tmp_path, monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    assert "EIA_API_KEY" not in os.environ
    assert _collect(tmp_path, three_days())["rows_new"] > 0
