"""Read-only health facts: states, separations, and content status (offline, fixed clock)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from ercot_fixtures import FakeErcot
from refresh_helpers import T0, Clock, WindowEIA, clients, config, ercot_docs, patch_clock, stores
from test_refresh import LAST_OPER

from mambo_explorer import health, refresh


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    patch_clock(monkeypatch, c)
    return c


def _refresh(data_dir, clock, sources=("eia", "ercot"), eia=None, ercot=None):
    return refresh.refresh(
        config(),
        list(sources),
        data_dir=data_dir,
        stores=stores(data_dir),
        clients=clients(eia, ercot or FakeErcot(ercot_docs(LAST_OPER, 3))),
        now=clock,
        local_today=clock().date(),
        dry_run=False,
        secrets=[],
    )


def _by(data_dir, now):
    return {h.source: h for h in health.source_health(stores(data_dir), config(), now)}


def test_empty_store_reports_no_data_and_creates_nothing(tmp_path):
    hs = _by(tmp_path, T0)
    for h in hs.values():
        assert h.freshness == health.NO_DATA and not h.collected
        assert h.last_attempt is None and h.last_success is None
        assert h.storage == {"status": "not created yet"}
    assert not any(tmp_path.rglob("*"))  # reading health wrote nothing


def test_successful_collection_separates_label_publication_and_retrieval(tmp_path, clock):
    _refresh(tmp_path, clock)
    hs = _by(tmp_path, clock())
    eia, ercot = hs["eia"], hs["ercot"]
    assert eia.latest_label == "period 2026-03-09T23 (UTC label)"
    assert eia.publication_time.startswith("not provided by EIA")
    assert eia.retrieval_time.startswith("2026-03-10T12:00")
    assert eia.freshness == health.FRESH and "uncertain by one hour" in eia.freshness_basis
    assert ercot.latest_label.startswith("OperDay 03/09/2026, HourEnding 24:00")
    assert ercot.publication_time == "2026-03-10T05:50:00-05:00 (ERCOT listing PublishDate)"
    assert ercot.freshness == health.FRESH and "publication time" in ercot.freshness_basis
    assert eia.last_attempt["status"] == eia.last_success["status"] == "committed"
    assert eia.storage["status"] == "ok" and not eia.problems
    cov = eia.coverage["D"]
    assert cov["hours_in_span"] == 72 and cov["rows_present"] == 72 and cov["hours_absent"] == 0


def test_stale_is_judged_from_observations_not_from_a_recent_request(tmp_path, clock):
    _refresh(tmp_path, clock)
    clock.advance(days=5)
    # A new successful request that brings nothing new (same window, nothing changed).
    _refresh(tmp_path, clock, sources=["ercot"])
    hs = _by(tmp_path, clock())
    assert hs["ercot"].last_success["finished_at"].startswith("2026-03-15")
    assert hs["ercot"].freshness == health.STALE  # the newest document is still from 03-10
    assert hs["eia"].freshness == health.STALE
    assert any("not a failure" in n for n in hs["ercot"].notes)  # unchanged ≠ failure


def test_absent_hours_are_counted_not_filled(tmp_path, clock):
    class Gappy(WindowEIA):
        def __call__(self, url, timeout):
            import json

            status, body = super().__call__(url, timeout)
            payload = json.loads(body)
            rows = [
                r
                for r in payload["response"]["data"]
                if not (r["type"] == "DF" and r["period"].endswith("T05"))
            ]
            payload["response"]["data"] = rows
            payload["response"]["total"] = str(len(rows))
            return status, json.dumps(payload).encode()

    _refresh(tmp_path, clock, sources=["eia"], eia=Gappy())
    cov = _by(tmp_path, clock())["eia"].coverage["DF"]
    assert cov["hours_absent"] == 3 and cov["null_values"] == 0


def test_partial_failure_and_storage_problems_are_shown(tmp_path, clock):
    _refresh(tmp_path, clock)
    clock.advance(hours=1)
    _refresh(
        tmp_path, clock, sources=["ercot"], ercot=FakeErcot({}, script=[(403, "text/html", b"x")])
    )
    target = stores(tmp_path)["eia"]
    first = target.committed_files("observations")[0]
    (target.root / first["path"]).unlink()  # simulate a damaged store
    hs = _by(tmp_path, clock())
    assert hs["ercot"].last_attempt["status"] == "failed"
    assert hs["ercot"].last_success["status"] == "committed"
    assert any(p.startswith("failed run") for p in hs["ercot"].problems)
    assert hs["eia"].storage["missing_files"] == 1
    assert hs["eia"].freshness == health.UNKNOWN  # unreadable observations: not guessed
    assert any("storage validation failed" in p for p in hs["eia"].problems)


def test_unknown_when_freshness_cannot_be_determined():
    assert health._freshness(None, 48) == health.UNKNOWN
    assert health._freshness(timedelta(hours=48), 48) == health.FRESH
    assert health._freshness(timedelta(hours=49), 48) == health.STALE


def test_content_health_reports_versions_review_and_no_monitoring():
    c = health.content_health()
    assert len(c["lessons"]) == 13
    assert {row["Automatic change monitoring"] for row in c["lessons"]} == {"none"}
    assert {row["Human review"] for row in c["lessons"]} == {"unreviewed"}
    assert c["records"]["Automatic change monitoring"] == "none"
    assert c["records"]["Source review date"] == "2026-10-11"
    assert c["records"]["Human review"] == "unreviewed"
