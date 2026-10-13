"""Bounded refresh orchestration (offline, credential-free, fixed clock; ADR 0013)."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from eia_fixtures import FAKE_KEY
from ercot_fixtures import FakeErcot
from refresh_helpers import (
    T0,
    Clock,
    WindowEIA,
    clients,
    config,
    ercot_docs,
    patch_clock,
    stores,
)

from mambo_explorer import cli, refresh
from mambo_explorer.ercot import dataset as ercot_ds

DAY = T0.date()  # 2026-03-10 (UTC); completed days end 2026-03-09
LAST_OPER = date(2026, 3, 9)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    patch_clock(monkeypatch, c)
    return c


def run(
    data_dir,
    clock,
    cfg=None,
    *,
    sources=("eia", "ercot"),
    eia=None,
    ercot=None,
    dry=False,
    key=FAKE_KEY,
    local_today=None,
    target=None,
):
    return refresh.refresh(
        cfg or config(),
        list(sources),
        data_dir=data_dir,
        stores=target or stores(data_dir),
        clients=clients(eia, ercot or FakeErcot(ercot_docs(LAST_OPER, 5)), key),
        now=clock,
        local_today=local_today or clock().date(),
        dry_run=dry,
        secrets=[key],
    )


def _findings(plan) -> dict[str, str]:
    return {f.kind: f.detail for f in plan.findings}


# --- dry run, first run, budgets -----------------------------------------------------------


def test_dry_run_sends_nothing_and_writes_nothing(tmp_path, clock):
    eia, ercot = WindowEIA(), FakeErcot(ercot_docs(LAST_OPER, 3))
    record = run(tmp_path, clock, eia=eia, ercot=ercot, dry=True)
    assert record["overall"] == "dry-run" and eia.urls == [] and ercot.urls == []
    assert [r["status"] for r in record["results"]] == ["planned", "planned"]
    assert record["requests_budgeted"] == 24
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


def test_first_refresh_collects_both_sources_sequentially_within_budget(tmp_path, clock):
    eia, ercot = WindowEIA(), FakeErcot(ercot_docs(LAST_OPER, 5))
    record = run(tmp_path, clock, eia=eia, ercot=ercot)
    assert record["overall"] == "complete" and refresh.exit_code("complete") == 0
    by = {r["source"]: r for r in record["results"]}
    assert by["eia"]["status"] == by["ercot"]["status"] == "succeeded"
    assert by["eia"]["requests"] == 1 and by["ercot"]["requests"] == 1 + 3  # list + 3 docs
    assert record["requests_used"] == 5 and record["requests_budgeted"] == 24
    kinds = {f["kind"] for p in record["plans"] for f in p["findings"]}
    assert refresh.NEVER_COLLECTED in kinds
    plan = record["plans"][0]["collector_plan"]
    assert plan["requested_days_utc"] == "2026-03-07 .. 2026-03-09"  # completed UTC days only
    log = tmp_path / "refresh" / "logs" / record["log"]
    assert json.loads(log.read_text("utf-8"))["overall"] == "complete"
    assert not (tmp_path / "refresh" / refresh.LOCK_NAME).exists()


class Flaky:
    """Returns HTTP 500 `times` times, then behaves like `inner`."""

    def __init__(self, inner, times):
        self.inner, self.times = inner, times

    def __call__(self, url, timeout):
        if self.times:
            self.times -= 1
            return 500, b"synthetic server error"
        return self.inner(url, timeout)


def test_request_budget_counts_retries_and_is_never_exceeded(tmp_path, clock):
    record = run(tmp_path, clock, sources=["eia"], eia=Flaky(WindowEIA(), 1))
    assert record["results"][0]["requests"] == 2  # one retry counted against the budget
    tight = config(sources__eia__request_budget=2)
    record = run(tmp_path / "b", clock, tight, sources=["eia"], eia=Flaky(WindowEIA(), 99))
    result = record["results"][0]
    assert result["status"] == "failed" and result["requests"] == 2
    assert "budget of 2 exhausted" in result["error"]


# --- partial failure, overlap ----------------------------------------------------------------


def test_one_source_failing_does_not_erase_the_other(tmp_path, clock):
    denied = FakeErcot(ercot_docs(LAST_OPER, 3), script=[(403, "text/html", b"denied")])
    record = run(tmp_path, clock, ercot=denied)
    assert record["overall"] == "partial" and refresh.exit_code("partial") == 3
    by = {r["source"]: r for r in record["results"]}
    assert by["eia"]["status"] == "succeeded" and by["ercot"]["status"] == "failed"
    assert "AccessError" in by["ercot"]["error"]
    s = stores(tmp_path)
    assert [r["status"] for r in s["eia"].runs()] == ["committed"]
    assert [r["status"] for r in s["ercot"].runs()] == ["failed"]
    clock.advance(hours=1)
    again = run(tmp_path, clock, sources=["ercot"])
    assert again["overall"] == "complete"
    assert [r["status"] for r in s["eia"].runs()] == ["committed"]  # untouched


def test_every_source_failing_is_reported_as_failed(tmp_path, clock):
    denied = FakeErcot({}, script=[(403, "text/html", b"denied")])
    record = run(tmp_path, clock, ercot=denied, key=None)  # no EIA key: credential error
    assert record["overall"] == "failed" and refresh.exit_code("failed") == 2
    assert "CredentialError" in record["results"][0]["error"]


def test_overlapping_refresh_is_refused_and_sends_nothing(tmp_path, clock):
    eia = WindowEIA()
    with refresh.refresh_lock(tmp_path, clock()):
        with pytest.raises(refresh.RefreshLockError, match="another refresh is running"):
            run(tmp_path, clock, eia=eia)
    assert eia.urls == []
    (tmp_path / "refresh" / refresh.LOCK_NAME).write_text("pid=1 since=old", "utf-8")
    with pytest.raises(refresh.RefreshLockError, match="stale"):
        run(tmp_path, clock, eia=eia)
    assert (tmp_path / "refresh" / refresh.LOCK_NAME).exists()  # never removed for you


def test_a_held_writer_lock_fails_only_that_source(tmp_path, clock):
    target = stores(tmp_path)
    with target["eia"].writer_lock():
        record = run(tmp_path, clock, target=target)
    by = {r["source"]: r for r in record["results"]}
    assert by["eia"]["status"] == "failed" and "WriterLockError" in by["eia"]["error"]
    assert by["ercot"]["status"] == "succeeded" and record["overall"] == "partial"


# --- catch-up planning ------------------------------------------------------------------------


def test_eia_catch_up_resumes_after_the_last_committed_day_with_lookback(tmp_path, clock):
    run(tmp_path, clock, sources=["eia"])
    clock.advance(days=5)  # now 2026-03-15; days 03-10 .. 03-14 are new
    plan = refresh.plan_eia(config(), stores(tmp_path)["eia"], clock())
    assert plan.eia_plan.start_day == date(2026, 3, 10) and plan.eia_plan.end_day == date(
        2026, 3, 15
    )
    assert plan.eia_plan.lookback_days == 3
    found = _findings(plan)
    assert refresh.MISSED_COLLECTION in found and refresh.REVISION_LOOKBACK in found
    assert refresh.NEVER_COLLECTED not in found


def test_eia_catch_up_is_capped_and_says_what_it_skips(tmp_path, clock):
    run(tmp_path, clock, sources=["eia"])
    clock.advance(days=30)
    plan = refresh.plan_eia(config(), stores(tmp_path)["eia"], clock())
    assert plan.eia_plan.start_day == clock().date() - timedelta(days=14)
    assert plan.eia_plan.fetch_days == 14 + 3
    assert (
        "2026-03-10 .. 2026-03-22 are not requested"
    )  # lookback covers 23-25 in _findings(plan)[refresh.BEYOND_CATCHUP]


def test_eia_up_to_date_requests_only_the_revision_lookback(tmp_path, clock):
    run(tmp_path, clock, sources=["eia"])
    plan = refresh.plan_eia(config(), stores(tmp_path)["eia"], clock())
    assert refresh.UP_TO_DATE in _findings(plan)
    assert plan.eia_plan.start_day == DAY - timedelta(days=1)
    assert plan.eia_plan.fetch_start_day == DAY - timedelta(days=4)


def test_missed_collection_comes_from_run_times_not_from_absent_rows(tmp_path, clock):
    # Absent rows (a whole metric hour missing) do not create a missed-collection finding.
    eia = WindowEIA(overrides={("DF", "2026-03-08T05"): None})
    run(tmp_path, clock, sources=["eia"], eia=eia)
    clock.advance(hours=30)  # within two 24 h intervals
    plan = refresh.plan_eia(config(), stores(tmp_path)["eia"], clock())
    assert refresh.MISSED_COLLECTION not in _findings(plan)
    clock.advance(hours=20)  # 50 h since the last success
    plan = refresh.plan_eia(config(), stores(tmp_path)["eia"], clock())
    assert refresh.MISSED_COLLECTION in _findings(plan)


@pytest.mark.parametrize(
    "local_today, documents, kinds",
    [
        (date(2026, 3, 10), 1, {refresh.REVISION_LOOKBACK}),  # nothing new; re-check newest
        (date(2026, 3, 15), 6, {refresh.REVISION_LOOKBACK}),  # 5 new + 1 lookback
        (date(2026, 3, 25), 7, {refresh.BEYOND_CATCHUP}),  # 15 new: capped at 7
        (date(2026, 5, 1), 7, {refresh.OUTSIDE_HISTORY, refresh.BEYOND_CATCHUP}),
    ],
)
def test_ercot_catch_up_by_calendar_labels(tmp_path, clock, local_today, documents, kinds):
    run(tmp_path, clock, sources=["ercot"], ercot=FakeErcot(ercot_docs(LAST_OPER, 3)))
    plan = refresh.plan_ercot(config(), stores(tmp_path)["ercot"], clock(), local_today)
    assert plan.ercot_selection.latest == documents
    assert kinds <= set(_findings(plan))


def test_ercot_with_no_lookback_and_nothing_new_is_skipped(tmp_path, clock):
    run(tmp_path, clock, sources=["ercot"], ercot=FakeErcot(ercot_docs(LAST_OPER, 3)))
    cfg = config(sources__ercot__revision_lookback_documents=0)
    plan = refresh.plan_ercot(cfg, stores(tmp_path)["ercot"], clock(), date(2026, 3, 10))
    assert plan.action == "skip" and refresh.UP_TO_DATE in _findings(plan)


def test_failed_and_interrupted_last_attempts_are_reported(tmp_path, clock):
    run(tmp_path, clock, sources=["ercot"], ercot=FakeErcot({}, script=[(403, "text/html", b"x")]))
    plan = refresh.plan_ercot(config(), stores(tmp_path)["ercot"], clock(), DAY)
    assert "failed" in _findings(plan)[refresh.SOURCE_UNAVAILABLE]
    assert refresh.NEVER_COLLECTED in _findings(plan)  # a failure is not a collection


# --- revisions, interrupted storage, redaction, logs ------------------------------------------


def test_revision_lookback_records_a_changed_value_as_a_new_revision(tmp_path, clock):
    run(tmp_path, clock, sources=["eia"])
    clock.advance(days=1)
    changed = WindowEIA(overrides={("D", "2026-03-09T10"): "1"})
    record = run(tmp_path, clock, sources=["eia"], eia=changed)
    summary = record["results"][0]["summary"]
    assert summary["rows_revised"] == 1 and summary["rows_new"] == 48
    with stores(tmp_path)["eia"].query() as con:
        revisions = con.execute(
            "SELECT revision, value_raw FROM observations WHERE metric='D' AND "
            "period='2026-03-09T10' ORDER BY revision"
        ).fetchall()
    assert [r[0] for r in revisions] == [1, 2] and revisions[1][1] == "1"  # lineage kept


def test_interrupted_storage_leaves_a_started_run_and_other_source_succeeds(
    tmp_path, clock, monkeypatch
):
    target = stores(tmp_path)

    def broken(run_id, rows):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(target["eia"], "write_observations", broken)
    record = run(tmp_path, clock, target=target)
    by = {r["source"]: r for r in record["results"]}
    assert by["eia"]["status"] == "failed" and "synthetic disk failure" in by["eia"]["error"]
    assert by["ercot"]["status"] == "succeeded"
    report = stores(tmp_path)["eia"].validate()
    assert len(report["interrupted"]) == 1 and report["orphans"]  # raw page written, not registered
    assert report["ok"]  # nothing committed was damaged
    plan = refresh.plan_eia(config(), stores(tmp_path)["eia"], clock())
    assert "interrupted" in _findings(plan)[refresh.SOURCE_UNAVAILABLE]


def test_diagnostics_are_redacted_in_results_and_logs(tmp_path, clock):
    def leaky(budget):
        raise RuntimeError(f"synthetic failure near https://x/?api_key={FAKE_KEY}&a=1 {FAKE_KEY}")

    cs = clients()
    cs["ercot"] = leaky
    record = refresh.refresh(
        config(),
        ["eia", "ercot"],
        data_dir=tmp_path,
        stores=stores(tmp_path),
        clients=cs,
        now=clock,
        local_today=DAY,
        dry_run=False,
        secrets=[FAKE_KEY],
    )
    error = record["results"][1]["error"]
    assert FAKE_KEY not in error and "[REDACTED]" in error
    text = (tmp_path / "refresh" / "logs" / record["log"]).read_text("utf-8")
    assert FAKE_KEY not in text and "fake" not in text.lower().replace("synthetic", "")


def test_logs_are_pruned_by_age_and_count(tmp_path, clock):
    folder = tmp_path / "refresh" / "logs"
    folder.mkdir(parents=True)
    for stamp in ("20260101T000000Z", "20260305T000000Z", "20260306T000000Z"):
        (folder / f"refresh-{stamp}-aaaaaa.json").write_text("{}", "utf-8")
    (folder / "unrelated.json").write_text("{}", "utf-8")
    cfg = config(logs__max_files=1)
    removed = refresh.prune_logs(folder, cfg, clock())
    assert sorted(removed) == [
        "refresh-20260101T000000Z-aaaaaa.json",
        "refresh-20260305T000000Z-aaaaaa.json",
    ]
    assert (folder / "unrelated.json").exists()  # only this app's refresh logs are pruned


# --- CLI ---------------------------------------------------------------------------------------


def test_cli_dry_run_shows_plan_and_budgets_and_needs_no_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    assert cli.main(["--no-dotenv", "refresh", "--dry-run", "--source", "ercot"]) == 0
    out = capsys.readouterr().out
    assert '"overall": "dry-run"' in out and "Dry run: no requests sent" in out
    assert '"source": "ercot"' in out and '"source": "eia"' not in out.split('"plans"')[1]
    assert not (tmp_path / "data").exists() or not any(
        p.is_file() for p in (tmp_path / "data").rglob("*")
    )


def test_cli_refuses_when_another_refresh_holds_the_lock(tmp_path, monkeypatch, capsys):
    data = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(data))
    (data / "refresh").mkdir(parents=True)
    (data / "refresh" / refresh.LOCK_NAME).write_text("pid=1", "utf-8")
    assert cli.main(["--no-dotenv", "refresh", "--source", "ercot"]) == 2
    assert "RefreshLockError" in capsys.readouterr().err


def test_ercot_public_history_limit_is_the_reviewed_value():
    assert ercot_ds.PUBLIC_RETENTION_DAYS == 31
