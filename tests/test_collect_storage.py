"""Ingest, idempotency, revisions, interrupted writes, recovery, locking, and queries.

All data here is SYNTHETIC (tests/eia_fixtures.py).
"""

import hashlib
from datetime import UTC, date, datetime

import pyarrow.parquet as pq
import pytest
from eia_fixtures import FAKE_KEY, FakeEIA, synthetic_rows

from mambo_explorer.collect import PlanError, collect, plan_collection
from mambo_explorer.eia import dataset as ds
from mambo_explorer.eia.client import EIAClient
from mambo_explorer.storage import Store, WriterLockError

TODAY = date(2026, 10, 11)


def plan(days=2, lookback=0, page_size=5000, **kw):
    return plan_collection(
        days=days, lookback_days=lookback, page_size=page_size, today=TODAY, **kw
    )


def run(store, rows, p=None, **client_kw):
    p = p or plan()
    c = EIAClient(
        FAKE_KEY,
        transport=FakeEIA(rows),
        sleep=lambda s: None,
        max_requests=p.max_requests,
        **client_kw,
    )
    return collect(p, c, store)


def rows_for(p, overrides=None):
    return synthetic_rows(p.fetch_start_day, p.fetch_days, overrides=overrides)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")


# --- planning ---------------------------------------------------------------------------


def test_default_plan_is_seven_completed_utc_days_with_budget():
    p = plan_collection(today=TODAY)
    assert (p.start_day, p.end_day) == (date(2026, 10, 4), date(2026, 10, 11))
    assert p.start_period == "2026-10-02T00" and p.end_period == "2026-10-10T23"
    assert p.expected_rows == 9 * 24 * 2 and p.pages_needed == 1 and p.max_requests >= 1


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"days": 31, "lookback_days": 1}, "per-run maximum"),
        ({"end": date(2026, 10, 12)}, "future"),
        ({"start": date(2026, 10, 5), "end": date(2026, 10, 5)}, "before end"),
        ({"page_size": 0}, "page_size"),
        ({"page_size": 10, "max_requests": 2, "days": 7}, "below"),
    ],
)
def test_unbounded_or_invalid_plans_are_rejected(kwargs, message):
    with pytest.raises(PlanError, match=message):
        plan_collection(today=TODAY, **kwargs)


# --- normalization -------------------------------------------------------------------


def test_values_units_intervals_and_flags(store):
    p = plan(days=1)
    rows = rows_for(
        p,
        {
            ("D", "2026-10-10T03"): None,
            ("D", "2026-10-10T04"): "-5",
            ("DF", "2026-10-10T05"): "n/a",
            ("D", "2026-10-10T06"): 41234.5,
        },
    )
    run(store, rows, p)
    with store.query() as con:
        got = {
            (m, per): (raw, val, unit, flags, start, end)
            for m, per, raw, val, unit, flags, start, end in con.execute(
                "SELECT metric, period, value_raw, value, unit, quality_flags, "
                "interval_start_utc, interval_end_utc FROM latest"
            ).fetchall()
        }
    assert got[("D", "2026-10-10T03")][:4] == (None, None, "megawatthours", "missing")
    assert got[("D", "2026-10-10T04")][:4] == ("-5", -5.0, "megawatthours", "negative")
    assert got[("DF", "2026-10-10T05")][:4] == ("n/a", None, "megawatthours", "non_numeric")
    assert got[("D", "2026-10-10T06")][:2] == ("41234.5", 41234.5)
    # Interval convention is unverified for the API field, so no boundaries are derived.
    assert got[("D", "2026-10-10T06")][4:] == (None, None)
    assert len(got) == 48  # missing and invalid values are kept, not dropped


@pytest.mark.parametrize(
    "convention, expected",
    [
        (None, (None, None)),
        (
            "hour_ending",
            (datetime(2026, 10, 10, 5, tzinfo=UTC), datetime(2026, 10, 10, 6, tzinfo=UTC)),
        ),
        (
            "hour_beginning",
            (datetime(2026, 10, 10, 6, tzinfo=UTC), datetime(2026, 10, 10, 7, tzinfo=UTC)),
        ),
    ],
)
def test_interval_boundaries_follow_only_the_configured_convention(
    monkeypatch, convention, expected
):
    monkeypatch.setattr(ds, "INTERVAL_CONVENTION", convention)
    assert ds.interval_utc("2026-10-10T06") == expected


def test_default_interval_convention_is_unverified():
    assert ds.INTERVAL_CONVENTION is None


def test_records_carry_lineage_and_null_publication_time(store):
    run(store, rows_for(plan()))
    table = pq.read_table(store.root / store.committed_files("observations")[0]["path"])
    row = table.slice(0, 1).to_pylist()[0]
    assert row["publication_time_utc"] is None
    assert row["retrieved_at_utc"] is not None
    assert row["archive_path"].startswith("raw/run=") and len(row["archive_sha256"]) == 64
    assert (row["request_start"], row["request_end"]) == ("2026-10-09T00", "2026-10-10T23")
    assert row["source"] == "EIA" and row["dataset"] == "EIA-930" and row["revision"] == 1


def test_archive_is_sanitized_and_checksummed(store):
    summary = run(store, rows_for(plan()))
    assert summary["sanitized_pages"] == 1
    raw = store.committed_files("raw")[0]
    data = (store.root / raw["path"]).read_bytes()
    assert raw["sanitized"] == 1
    assert hashlib.sha256(data).hexdigest() == raw["sha256"]
    assert FAKE_KEY.encode() not in data and b"[REDACTED]" in data


# --- idempotency and revisions -----------------------------------------------------------


def test_repeated_ingestion_is_idempotent(store):
    p = plan()
    first = run(store, rows_for(p), p)
    second = run(store, rows_for(p), p)
    assert first["rows_new"] == 96 and first["rows_unchanged"] == 0
    assert (
        second["rows_new"] == 0 and second["rows_revised"] == 0 and second["rows_unchanged"] == 96
    )
    with store.query() as con:
        assert con.execute("SELECT count(*) FROM observations").fetchone()[0] == 96
        assert con.execute("SELECT count(*) FROM latest").fetchone()[0] == 96
    assert len(store.committed_files("observations")) == 2  # second run wrote no observation file


def test_changed_value_creates_revision_with_lineage(store):
    p = plan()
    run(store, rows_for(p), p)
    changed = rows_for(p, {("D", "2026-10-10T12"): "99999"})
    summary = run(store, changed, p)
    assert summary["rows_revised"] == 1 and summary["rows_unchanged"] == 95
    with store.query() as con:
        history = con.execute(
            "SELECT revision, value_raw, run_id FROM observations "
            "WHERE metric='D' AND period='2026-10-10T12' ORDER BY revision"
        ).fetchall()
        latest = con.execute(
            "SELECT value_raw FROM latest WHERE metric='D' AND period='2026-10-10T12'"
        ).fetchone()
    # Synthetic D value for 2026-10-10T12 (hour 36 from 2026-10-09T00): 40000 + 12 * 100.
    assert [h[:2] for h in history] == [(1, "41200"), (2, "99999")]
    assert history[0][2] != history[1][2]
    assert latest == ("99999",)


def test_revision_lookback_refetches_earlier_days(store):
    p1 = plan(days=2, lookback=0)
    run(store, rows_for(p1), p1)
    p2 = plan_collection(start=date(2026, 10, 10), end=TODAY, lookback_days=1, today=TODAY)
    assert p2.start_period == "2026-10-09T00"
    summary = run(store, rows_for(p2, {("DF", "2026-10-09T08"): "1"}), p2)
    assert summary["rows_revised"] == 1


# --- interrupted writes, recovery, and locking ------------------------------------------


def test_failure_between_file_write_and_catalog_commit_is_invisible_and_recoverable(
    store, monkeypatch
):
    p = plan()
    run(store, rows_for(p), p)

    def crash(*a, **k):
        raise RuntimeError("simulated crash before catalog commit")

    with monkeypatch.context() as m:
        m.setattr(Store, "commit_run", crash)
        with pytest.raises(RuntimeError):
            run(store, rows_for(p, {("D", "2026-10-10T01"): "1"}), p)

    with store.query() as con:  # readers never see the uncommitted revision
        assert con.execute("SELECT count(*) FROM observations").fetchone()[0] == 96
        assert (
            con.execute(
                "SELECT value_raw FROM latest WHERE metric='D' AND period='2026-10-10T01'"
            ).fetchone()[0]
            != "1"
        )
    assert not store.lock_path.exists()  # lock released even on crash

    report = store.validate()
    assert report["ok"] and len(report["interrupted"]) == 1
    assert {o.split("/")[0] for o in report["orphans"]} == {"raw", "observations"}

    # Recovery: a rerun commits cleanly; then reconcile marks and quarantines, deleting nothing.
    summary = run(store, rows_for(p, {("D", "2026-10-10T01"): "1"}), p)
    assert summary["rows_revised"] == 1
    orphans = store.validate()["orphans"]
    after = store.validate(mark_interrupted=True, quarantine_orphans=True)
    assert (
        after["ok"] and store.validate()["orphans"] == [] and store.validate()["interrupted"] == []
    )
    assert all((next((store.root / "quarantine").iterdir()) / o).is_file() for o in orphans)
    with store.query() as con:
        assert con.execute("SELECT count(*) FROM observations").fetchone()[0] == 97


def test_source_failure_marks_run_failed_and_writes_nothing(store):
    p = plan()
    c = EIAClient(FAKE_KEY, transport=FakeEIA([], script=[(400, b"bad")]), sleep=lambda s: None)
    with pytest.raises(Exception, match="HTTP 400"):
        collect(p, c, store)
    assert store.runs()[0]["status"] == "failed"
    assert store.committed_files("observations") == [] and store.validate()["orphans"] == []


def test_concurrent_writer_is_rejected(store):
    p = plan()
    with store.writer_lock():
        with pytest.raises(WriterLockError, match="another collection holds the writer lock"):
            run(store, rows_for(p), p)


def test_checksum_mismatch_is_detected(store):
    run(store, rows_for(plan()))
    path = store.root / store.committed_files("observations")[0]["path"]
    path.write_bytes(path.read_bytes() + b"tamper")
    report = store.validate()
    assert not report["ok"] and report["checksum_mismatch"]


def test_query_on_empty_store_returns_no_rows(store):
    with store.query() as con:
        assert con.execute("SELECT count(*) FROM latest").fetchone()[0] == 0
    assert store.diagnostics()["latest_observations"] == 0


def test_dataset_constants_match_review():
    assert ds.ROUTE == "electricity/rto/region-data"
    assert ds.ENTITY == "ERCO" and ds.METRICS == ("D", "DF")
