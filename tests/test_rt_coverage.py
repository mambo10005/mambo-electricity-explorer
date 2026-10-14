"""Stage 21: coverage-aware real-time price collection and bounded catch-up (offline, SYNTHETIC).

Synthetic listings and a controllable clock; no credential and no network.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from refresh_helpers import Clock, config, patch_clock
from rt_price_fixtures import FakeRt, csv_for, interval_doc, zip_bytes

from mambo_explorer import cli, health, refresh, refresh_config
from mambo_explorer.ercot import prices as dam
from mambo_explorer.ercot import rt_inventory as inv
from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.client import ErcotClient

D1 = date(2026, 10, 6)
T1 = datetime(2026, 10, 6, 5, 0, tzinfo=UTC)
EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "refresh-rt-catchup.yaml"


def backlog(days: int, start_id: int = 10000, first: date = D1) -> dict:
    """`days` operating days of 96 documents each, published 15 minutes apart. The last
    interval of a day (H24 I4) is published just after midnight, so its PublishDate label is
    the NEXT day, as in the live list."""
    docs, n = {}, start_id
    for d in range(days):
        day = first + timedelta(days=d)
        for k in range(96):
            stamp = datetime(day.year, day.month, day.day) + timedelta(minutes=15 * (k + 1))
            published = f"{stamp:%Y-%m-%dT%H:%M}:02-05:00"
            docs.update(dict([interval_doc(day, k // 4 + 1, k % 4 + 1, str(n), published)]))
            n += 1
    return docs


class Fake(FakeRt):
    """FakeRt with per-document scripted responses (e.g. a 404, or a 500 then success)."""

    def __init__(self, docs, fail=None):
        super().__init__(docs)
        self.fail = {k: list(v) for k, v in (fail or {}).items()}

    def __call__(self, url, timeout):
        doc_id = url.rsplit("=", 1)[1]
        if self.fail.get(doc_id):
            self.urls.append(url)
            return self.fail[doc_id].pop(0)
        return super().__call__(url, timeout)


@pytest.fixture
def clock(monkeypatch):
    c = Clock(T1)
    patch_clock(monkeypatch, c)
    return c


def run(data_dir, fake, selection, clock, budget=None):
    client = ErcotClient(
        transport=fake, sleep=lambda s: None, max_requests=budget or selection.request_budget
    )
    clock.advance(minutes=5)
    return rt.collect(selection, client, rt.store(data_dir), now=clock)


def coverage(start, end=None, latest=16, recheck=0):
    return rt.Selection(
        latest=latest, mode=rt.COVERAGE, publish_from=start, publish_to=end, recheck=recheck
    )


def observations(data_dir):
    with rt.store(data_dir).query() as con:
        return con.execute(
            "SELECT doc_id, delivery_date_raw, delivery_hour, delivery_interval, revision "
            "FROM observations ORDER BY publication_time_utc"
        ).fetchall()


def statuses(data_dir):
    target = rt.store(data_dir)
    rows = inv.classify(
        inv.Inventory(target).documents(),
        inv.collected_doc_ids(target),
        inv.superseded_doc_ids(target),
    )
    return {r["doc_id"]: r["status"] for r in rows}


def rt_health(data_dir, cfg, now):
    return health.rt_price_health(rt.store(data_dir), cfg, now)


def rt_config(**changes):
    return config(**{"sources__ercot-rt-spp__enabled": True, **changes})


# --- coverage mode ---------------------------------------------------------------------------


def test_coverage_mode_works_oldest_first_through_a_multi_day_backlog(tmp_path, clock):
    fake = Fake(backlog(2))  # 192 documents over PublishDates 10-06 .. 10-08
    selection = coverage(D1, D1)
    first = run(tmp_path, fake, selection, clock)
    assert first["status"] == "range in progress" and first["scope"]["listed_in_range"] == 95
    assert [o[2:4] for o in observations(tmp_path)][:5] == [
        ("1", "1"),
        ("1", "2"),
        ("1", "3"),
        ("1", "4"),
        ("2", "1"),
    ]  # the OLDEST documents first
    assert first["remaining_uncollected_in_range"] == 79 and first["documents_deferred"] == 79
    assert first["request_breakdown"] == {
        "list": 1,
        "download": 16,
        "other": 0,
        "retries_included": 0,
        "total": 17,
    }
    summaries = [first]
    while summaries[-1]["remaining_uncollected_in_range"]:
        summaries.append(run(tmp_path, fake, selection, clock))
        assert summaries[-1]["requests"] <= selection.request_budget <= 18
    assert len(summaries) == 6  # 16 + 16 + 16 + 16 + 16 + 15, one bounded run at a time
    done = run(tmp_path, fake, selection, clock)
    assert done["status"] == "no uncollected listed document in the range"
    assert done["requests"] == 1 and done["rows_new"] == 0
    rows = observations(tmp_path)
    assert len(rows) == 95 and {r[4] for r in rows} == {1}  # no duplicate observation
    assert len({r[0] for r in rows}) == 95
    # PublishDate is not DeliveryDate: H24 I4 of 10/06 was published on 10-07, so the
    # range holds 95 intervals and hour 24 has three of four (not comparable).
    cfg = refresh_config.validate(
        _plan(mode="coverage", coverage_from="2026-10-06", coverage_to="2026-10-06")
    )
    h = rt_health(tmp_path, cfg, clock())
    assert h.completeness.startswith("Complete for the documents ERCOT listed")
    assert "not a verified number of intervals" in h.completeness
    assert h.coverage["HB_NORTH"]["hours_with_fewer_than_4_intervals"] == 1
    assert h.collection["Published but not collected (all listed documents)"] == str(192 - 95)


def test_snapshot_mode_takes_the_newest_and_sees_documents_arriving_between_runs(tmp_path, clock):
    docs = backlog(1)
    first_eight = dict(list(docs.items())[:8])
    fake = Fake(first_eight)
    first = run(tmp_path, fake, rt.Selection(4), clock)
    assert [o[2:4] for o in observations(tmp_path)] == [
        ("2", "1"),
        ("2", "2"),
        ("2", "3"),
        ("2", "4"),
    ]
    assert first["status"] == "partial catch-up" and first["listing"]["new_documents"] == 8
    fake.docs = dict(list(docs.items())[:12])  # four new intervals published since
    second = run(tmp_path, fake, rt.Selection(4), clock)
    assert second["listing"]["new_documents"] == 4
    assert [o[2] for o in observations(tmp_path)][-4:] == ["3", "3", "3", "3"]
    assert second["scope"]["deferred_by_document_bound"] == 4  # hour 1 is still not collected
    third = run(tmp_path, fake, rt.Selection(4), clock)
    assert third["status"] == "collected" and len(observations(tmp_path)) == 12
    assert run(tmp_path, fake, rt.Selection(4), clock)["status"] == (
        "no newer document published yet"
    )


# --- budgets, failures, resume ----------------------------------------------------------------


def test_budget_exhaustion_commits_progress_and_the_next_run_resumes(tmp_path, clock):
    fake = Fake(backlog(1))
    stopped = run(tmp_path, fake, coverage(D1, latest=8), clock, budget=5)
    assert stopped["status"].startswith("stopped early") and stopped["rows_new"] == 4
    assert stopped["requests"] == 5 and stopped["stopped_early"]
    status = statuses(tmp_path)
    assert sum(s == inv.COLLECTED for s in status.values()) == 4
    assert sum(s == inv.DEFERRED for s in status.values()) == 92  # 96 in range
    resumed = run(tmp_path, fake, coverage(D1, latest=8), clock)
    assert resumed["rows_new"] == 8 and resumed["rows_unchanged"] == 0
    rows = observations(tmp_path)
    assert len(rows) == 12 and len({r[0] for r in rows}) == 12
    assert [r[2:4] for r in rows][4] == ("2", "1")  # continued where the stopped run ended


def test_partial_failure_is_isolated_and_failed_documents_wait_behind_unseen_ones(tmp_path, clock):
    docs = backlog(1)
    ids = list(docs)
    fake = Fake(docs, fail={ids[0]: [(404, "text/html", b"gone")]})
    first = run(tmp_path, fake, coverage(D1, latest=4), clock)
    assert first["documents_failed"] == 1 and first["rows_new"] == 3
    assert first["status"] == "completed with document failures"
    assert statuses(tmp_path)[ids[0]] == inv.FAILED
    second = run(tmp_path, fake, coverage(D1, latest=4), clock)
    assert ids[0] not in [d["doc_id"] for d in second["documents"]]  # unseen ones first
    # A transient 500 is retried inside the budget and counted as a request.
    fake.fail[ids[8]] = [(500, "text/plain", b"busy")]
    third = run(tmp_path, fake, coverage(D1, latest=4), clock)
    assert third["retries"] == 1 and third["request_breakdown"]["download"] == 5
    assert third["request_breakdown"]["total"] == 6 and third["documents_failed"] == 0
    # A run that stops early keeps a previously failed document "failed" (still behind unseen).
    two = dict(list(docs.items())[:2])
    small = Fake(two, fail={ids[0]: [(404, "text/html", b"gone")]})
    run(tmp_path / "stop", small, coverage(D1, latest=2), clock)
    stop = run(tmp_path / "stop", small, coverage(D1, latest=1), clock, budget=1)
    assert stop["stopped_early"] and stop["request_breakdown"]["list"] == 1
    assert statuses(tmp_path / "stop")[ids[0]] == inv.FAILED


def test_interrupted_write_leaves_no_observation_and_the_rerun_has_no_duplicates(
    tmp_path, clock, monkeypatch
):
    fake = Fake(backlog(1))
    target = rt.store(tmp_path)

    def broken(run_id, rows):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(target, "write_observations", broken)
    with pytest.raises(OSError):
        rt.collect(
            coverage(D1, latest=4),
            ErcotClient(transport=fake, sleep=lambda s: None, max_requests=6),
            target,
            now=clock,
        )
    assert target.validate(mark_interrupted=True, quarantine_orphans=True)["ok"]
    assert set(statuses(tmp_path).values()) == {inv.DISCOVERED}  # nothing claimed collected
    again = run(tmp_path, fake, coverage(D1, latest=4), clock)
    assert again["rows_new"] == 4 and len(observations(tmp_path)) == 4


# --- revisions -------------------------------------------------------------------------------


def test_recheck_allocation_detects_an_in_place_repost_and_coverage_is_reported(tmp_path, clock):
    docs = backlog(1)
    fake = Fake(dict(list(docs.items())[:4]))
    run(tmp_path, fake, coverage(D1, latest=4), clock)
    oldest = next(iter(fake.docs))
    pub, name, _ = fake.docs[oldest]
    fake.docs[oldest] = (pub, name, zip_bytes(csv_for(D1, 1, 1, price="99.99")))
    unseen_only = run(tmp_path, fake, coverage(D1, latest=4), clock)
    assert unseen_only["rows_revised"] == 0  # only unseen documents: the repost is missed
    checked = run(tmp_path, fake, coverage(D1, latest=4, recheck=1), clock)
    assert checked["revision_recheck"] == {"allocated": 1, "rechecked": 1}
    assert checked["rows_revised"] == 1
    again = run(tmp_path, fake, coverage(D1, latest=4, recheck=1), clock)
    assert again["documents"][0]["doc_id"] != oldest  # least recently checked first
    off = rt_health(tmp_path, rt_config(), clock())
    assert off.collection["Revision recheck"].startswith("none allocated: revisions are not")
    on = rt_health(
        tmp_path, rt_config(**{"sources__ercot-rt-spp__revision_lookback_documents": 1}), clock()
    )
    assert on.collection["Revision recheck"].startswith("2 of 4 collected documents")


def test_a_repost_under_a_new_docid_supersedes_and_is_never_rechecked(tmp_path, clock):
    docs = dict(list(backlog(1).items())[:2])
    fake = Fake(docs)
    run(tmp_path, fake, coverage(D1, latest=2), clock)
    first_id = next(iter(docs))
    pub, name, _ = docs[first_id]
    fake.docs["99999"] = (
        pub.replace(":02-", ":59-"),
        name,
        zip_bytes(csv_for(D1, 1, 1, price="1.00")),
    )
    summary = run(tmp_path, fake, coverage(D1, latest=2, recheck=2), clock)
    assert summary["rows_revised"] == 1
    assert statuses(tmp_path)[first_id] == inv.SUPERSEDED
    later = run(tmp_path, fake, coverage(D1, latest=1, recheck=2), clock)
    assert first_id not in [d["doc_id"] for d in later["documents"]]
    assert later["rows_revised"] == 0


# --- listings and availability ----------------------------------------------------------------


def test_disappearing_documents_are_flagged_without_claiming_they_are_lost(tmp_path, clock):
    docs = dict(list(backlog(1).items())[:8])
    fake = Fake(docs)
    run(tmp_path, fake, coverage(D1, latest=2), clock)
    fake.docs = dict(list(docs.items())[4:])  # the four oldest leave the public list
    summary = run(tmp_path, fake, coverage(D1, latest=1), clock)
    assert summary["listing"]["no_longer_listed"] == 4
    assert len(observations(tmp_path)) == 3  # what was collected stays
    h = rt_health(tmp_path, rt_config(), clock())
    assert h.collection["No longer listed and not collected"].startswith("2 (not proof")


def test_unavailable_and_future_ranges_are_reported(tmp_path, clock):
    fake = Fake(dict(list(backlog(1, first=date(2026, 10, 8)).items())[:4]))
    old = run(tmp_path, fake, coverage(date(2026, 10, 1), date(2026, 10, 7)), clock)
    assert old["status"] == "no listed document in the range" and old["requests"] == 1
    assert (
        "2026-10-01 through 2026-10-07 are older than ERCOT's public list"
        in (old["scope"]["unavailable"])
    )
    straddle = run(tmp_path, fake, coverage(date(2026, 10, 1), date(2026, 10, 9)), clock)
    assert (
        "PublishDates 2026-10-01 through 2026-10-07 are older" in straddle["scope"]["unavailable"]
    )
    future = run(tmp_path, fake, coverage(date(2026, 10, 20)), clock)
    assert (
        "no document with PublishDate 2026-10-20 or later is listed yet"
        in (future["scope"]["unavailable"])
    )
    partial = rt.Selection(mode=rt.COVERAGE, publish_from=date(2026, 10, 8)).unavailable(
        [rt.Document("1", "", "2026-10-08T00:15:02-05:00", 0, "x")]
    )
    assert "the first listed document with PublishDate 2026-10-08" in partial
    assert "not known from the list" in partial


def test_inventory_lives_only_in_the_real_time_namespace(tmp_path, clock):
    run(tmp_path, Fake(dict(list(backlog(1).items())[:2])), rt.Selection(2), clock)
    assert (rt.store(tmp_path).root / inv.FILE_NAME).is_file()
    assert not dam.store(tmp_path).root.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [rt.STORE_NAMESPACE]
    # Readers never create the inventory.
    empty = rt.store(tmp_path / "empty")
    assert inv.Inventory(empty).documents() == [] and not empty.root.exists()


# --- health -----------------------------------------------------------------------------------


def test_fresh_but_incomplete_health(tmp_path, clock):
    docs = dict(list(backlog(1).items())[:8])
    run(tmp_path, Fake(docs), rt.Selection(4), clock)
    newest = datetime(2026, 10, 6, 7, 10, tzinfo=UTC)  # 2 h after 00:00-05:00 + 8 intervals
    h = rt_health(tmp_path, rt_config(), newest)
    assert h.freshness == health.FRESH
    assert h.completeness.startswith("Cannot be determined for a history")
    assert "4 published document(s)" in h.completeness
    cov = refresh_config.validate(_plan(mode="coverage", coverage_from="2026-10-06"))
    h2 = rt_health(tmp_path, cov, newest)
    assert h2.freshness == health.FRESH and h2.completeness.startswith("Not complete: 4 listed")
    nothing = rt_health(tmp_path / "none", rt_config(), newest)
    assert nothing.freshness == health.NO_DATA and "no ERCOT listing" in nothing.completeness


def _plan(**rt_changes) -> dict:
    data = yaml.safe_load(refresh_config.default_text())
    data["sources"]["ercot-rt-spp"].update({"enabled": True, **rt_changes})
    return data


# --- configuration, shared budget, refresh --------------------------------------------------


def test_mode_configuration_is_validated():
    assert (
        refresh_config.validate(_plan(mode="coverage", coverage_from="2026-10-06")).rt_prices.mode
        == "coverage"
    )
    for bad, message in (
        ({"mode": "coverage"}, "coverage_from is required"),
        ({"coverage_from": "2026-10-06"}, "need mode: coverage"),
        ({"mode": "all"}, "mode must be"),
        (
            {"mode": "coverage", "coverage_from": "2026-10-06", "coverage_to": "2026-10-01"},
            "before coverage_from",
        ),
        ({"revision_lookback_documents": 3}, "request_budget must cover"),
    ):
        with pytest.raises(refresh_config.RefreshConfigError, match=message):
            refresh_config.validate(_plan(**bad))


def test_shared_budget_order_warns_and_the_cap_is_unchanged(tmp_path, clock):
    cfg = config(
        **{"sources__ercot-dam-spp__enabled": True, "sources__ercot-rt-spp__enabled": True}
    )
    assert cfg.host_budget("ercot.com") == 18
    allocation = refresh.host_allocation(cfg, cfg.enabled())["ercot.com"]
    assert [o["source"] for o in allocation["order"]] == ["ercot", "ercot-dam-spp", "ercot-rt-spp"]
    assert (
        allocation["rt_always_skipped"] and "never runs with this plan" in allocation["warnings"][0]
    )
    plan = refresh.plan_ercot_rt(cfg, rt.store(tmp_path), clock(), cfg.enabled())
    assert plan.capacity["verdict"].startswith("cannot keep pace: with this plan real-time")
    # The order given with --source is the order used; nothing is silently reordered.
    reverse = refresh.host_allocation(cfg, ["ercot-rt-spp", "ercot", "ercot-dam-spp"])
    assert reverse["ercot.com"]["order"][0]["source"] == "ercot-rt-spp"
    daily = config(
        **{
            "sources__ercot-rt-spp__enabled": True,
            "sources__ercot-rt-spp__collection_interval_hours": 24,
            "sources__ercot__enabled": False,
        }
    )
    verdict = refresh.rt_capacity(daily, rt.store(tmp_path), ["ercot-rt-spp"])["verdict"]
    assert verdict.startswith("cannot keep pace: at most 8 of about 96 documents per day")
    hourly = refresh.rt_capacity(
        config(**{"sources__ercot-rt-spp__enabled": True, "sources__ercot__enabled": False}),
        rt.store(tmp_path),
        ["ercot-rt-spp"],
    )
    assert hourly["verdict"].startswith("keeps pace only if a refresh really runs every 1 h")
    assert hourly["complete_history_claimed"] is False


def test_example_catch_up_plan_selects_only_real_time_within_the_cap(tmp_path, clock):
    cfg = refresh_config.load(EXAMPLE)
    assert cfg.enabled() == ["ercot-rt-spp"] and cfg.rt_prices.mode == "coverage"
    assert cfg.rt_prices.request_budget == cfg.host_budget("ercot.com") == 18
    fake = Fake(backlog(1))
    record = refresh.refresh(
        cfg,
        cfg.enabled(),
        data_dir=tmp_path,
        stores={"ercot-rt-spp": rt.store(tmp_path)},
        clients={
            "ercot-rt-spp": lambda b: ErcotClient(
                transport=fake, sleep=lambda s: None, max_requests=b
            )
        },
        now=clock,
        local_today=D1,
        dry_run=True,
        secrets=[],
    )
    plan = record["plans"][0]
    assert (
        plan["collector_plan"]["mode"] == "coverage"
        and "2026-10-07" in plan["collector_plan"]["range"]
    )
    assert record["warnings"] == [] and fake.urls == []  # a dry run sends nothing


def test_refresh_reports_partial_when_a_document_fails(tmp_path, clock):
    docs = dict(list(backlog(1).items())[:4])
    fake = Fake(docs, fail={next(iter(docs)): [(404, "text/html", b"gone")]})
    cfg = config(**{"sources__ercot-rt-spp__enabled": True, "sources__ercot__enabled": False})
    record = refresh.refresh(
        cfg,
        ["ercot-rt-spp"],
        data_dir=tmp_path,
        stores={"ercot-rt-spp": rt.store(tmp_path)},
        clients={
            "ercot-rt-spp": lambda b: ErcotClient(
                transport=fake, sleep=lambda s: None, max_requests=b
            )
        },
        now=clock,
        local_today=D1,
        dry_run=False,
        secrets=[],
    )
    assert record["results"][0]["status"] == "partial" and record["overall"] == "partial"
    assert refresh.exit_code(record["overall"]) == refresh.EXIT_PARTIAL


# --- CLI ------------------------------------------------------------------------------------


def test_cli_dry_run_shows_mode_range_and_preview_without_requests(
    tmp_path, clock, monkeypatch, capsys
):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv(refresh_config.ENV, raising=False)
    run(tmp_path, Fake(dict(list(backlog(1).items())[:6])), coverage(D1, latest=2), clock)

    def no_network(*a, **k):
        raise AssertionError("a dry run must not send a request")

    monkeypatch.setattr("mambo_explorer.ercot.client.urllib_transport", no_network)
    code = cli.main(
        [
            "--no-dotenv",
            "collect",
            "--source",
            "ercot-rt-spp",
            "--coverage-from",
            "2026-10-06",
            "--latest",
            "3",
            "--recheck",
            "1",
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0 and '"mode": "coverage"' in out and "PublishDate 2026-10-06" in out
    assert '"request_budget": 6' in out and "the listing recorded at" in out
    assert out.count("SPPHLZNP6905_") == 4  # 3 new (oldest uncollected) + 1 recheck
    plan = tmp_path / "plan.yaml"
    data = yaml.safe_load(refresh_config.default_text())
    data["hosts"]["ercot.com"]["max_requests_per_refresh"] = 12
    plan.write_text(yaml.safe_dump(data), "utf-8")
    monkeypatch.setenv(refresh_config.ENV, str(plan))
    code = cli.main(
        [
            "--no-dotenv",
            "collect",
            "--source",
            "ercot-rt-spp",
            "--coverage-from",
            "2026-10-06",
            "--dry-run",
        ]
    )
    assert code != 0 and "above the shared ercot.com cap of 12" in capsys.readouterr().err
