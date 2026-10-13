"""System Health page via AppTest: states, separations, and that it never collects (offline)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from ercot_fixtures import FakeErcot
from refresh_helpers import T0, Clock, clients, config, ercot_docs, patch_clock, stores
from streamlit.testing.v1 import AppTest
from test_refresh import LAST_OPER

from mambo_explorer import collect, refresh, routes, system_health
from mambo_explorer.ercot import collect as ercot_collect

PAGE = "from mambo_explorer.pages import render_page\nrender_page('system-health')\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(data))
    monkeypatch.setattr(routes, "PAGES", {})
    clock = Clock()
    patch_clock(monkeypatch, clock)
    return data, clock, monkeypatch


def _fill(data, clock, ercot=None):
    """Populate scratch storage through the real refresh with synthetic transports."""
    return refresh.refresh(
        config(),
        ["eia", "ercot"],
        data_dir=data,
        stores=stores(data),
        clients=clients(None, ercot or FakeErcot(ercot_docs(LAST_OPER, 3))),
        now=clock,
        local_today=clock().date(),
        dry_run=False,
        secrets=[],
    )


def _render(monkeypatch, now):
    def forbidden(*args, **kwargs):
        raise AssertionError("System Health must never collect")

    # Any collection attempt from the page fails the test.
    for target, name in (
        (collect, "collect"),
        (ercot_collect, "collect"),
        (refresh, "execute"),
        (refresh, "refresh"),
    ):
        monkeypatch.setattr(target, name, forbidden)
    monkeypatch.setattr(system_health, "NOW", lambda: now)
    at = AppTest.from_string(PAGE).run(timeout=30)
    assert not at.exception
    return at


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return "\n".join(parts)


def _items(at) -> list[dict]:
    return [
        dict(zip(t.value["Item"], t.value["Value"], strict=True))
        for t in at.table
        if list(t.value.columns) == ["Item", "Value"] and "Freshness" in list(t.value["Item"])
    ]


def test_empty_state_shows_no_data_and_snapshot_note(env):
    data, clock, mp = env
    at = _render(mp, T0)
    eia, ercot, gen, price = _items(at)
    assert (
        eia["Freshness"]
        == ercot["Freshness"]
        == gen["Freshness"]
        == price["Freshness"]
        == "no data"
    )
    assert eia["Last attempted collection"] == "none recorded"
    text = _texts(at)
    assert "never collects data" in text and "No refresh logs yet" in text
    assert system_health.SNAPSHOT_NOTE in text and "not automatically maintained" in text
    assert not data.exists() or not any(p.is_file() for p in data.rglob("*"))


def test_successful_state_separates_attempt_success_label_publication_retrieval(env):
    data, clock, mp = env
    _fill(data, clock)
    at = _render(mp, T0 + timedelta(hours=1))
    eia, ercot, gen, price = _items(at)
    assert eia["Freshness"] == ercot["Freshness"] == "fresh"
    assert eia["Last attempted collection"].startswith("committed at 2026-03-10T12:00")
    assert eia["Latest observation label"] == "period 2026-03-09T23 (UTC label)"
    assert eia["Publication timestamp"].startswith("not provided by EIA")
    assert eia["Retrieval timestamp"].startswith("2026-03-10T12:00")
    assert ercot["Publication timestamp"].startswith("2026-03-10T05:50:00-05:00")
    assert eia["Configured freshness threshold"] == "48 hours"
    logs = next(t.value for t in at.table if "Requests used / budgeted" in t.value.columns)
    assert list(logs["Result"]) == ["complete"]


def test_stale_state_after_time_passes(env):
    data, clock, mp = env
    _fill(data, clock)
    at = _render(mp, T0 + timedelta(days=4))
    assert [i["Freshness"] for i in _items(at)] == [
        "stale",
        "stale",
        "no data",
        "no data",
    ]  # gen: nothing
    assert "Stale: older than the configured threshold" in _texts(at)


def test_unknown_state_when_observations_cannot_be_read(env):
    data, clock, mp = env
    _fill(data, clock)
    target = stores(data)["ercot"]
    (target.root / target.committed_files("observations")[0]["path"]).unlink()
    at = _render(mp, T0)
    eia, ercot, gen, price = _items(at)
    assert ercot["Freshness"] == "unknown" and eia["Freshness"] == "fresh"
    assert "Unknown: freshness cannot be determined" in _texts(at)
    assert any("observations could not be read" in e.value for e in at.error)


def test_partial_failure_state(env):
    data, clock, mp = env
    _fill(data, clock)
    clock.advance(hours=2)
    _fill(data, clock, ercot=FakeErcot({}, script=[(403, "text/html", b"denied")]))
    at = _render(mp, clock())
    eia, ercot, gen, price = _items(at)
    assert ercot["Last attempted collection"].startswith("failed")
    assert ercot["Last successful collection"].startswith("committed")
    assert any("failed run" in e.value and "403" in e.value for e in at.error)
    logs = next(t.value for t in at.table if "Requests used / budgeted" in t.value.columns)
    assert list(logs["Result"]) == ["partial", "complete"]


def test_view_selector_and_content_tables(env):
    data, clock, mp = env
    at = _render(mp, T0)
    at.radio(key="health_view").set_value("ercot").run(timeout=30)
    assert len(_items(at)) == 1
    lessons = next(t.value for t in at.table if "Lesson" in t.value.columns)
    assert set(lessons["Automatic change monitoring"]) == {"none"}
    assert set(lessons["Human review"]) == {"unreviewed"}
    at.button(key="health_recheck").click().run(timeout=30)
    assert not at.exception


def test_a_refresh_that_fails_before_collecting_is_still_shown(env):
    data, clock, mp = env
    # No EIA key: the EIA client is never built, so the catalog has no EIA run at all.
    refresh.refresh(
        config(),
        ["eia", "ercot"],
        data_dir=data,
        stores=stores(data),
        clients=clients(None, FakeErcot(ercot_docs(LAST_OPER, 3)), key=None),
        now=clock,
        local_today=clock().date(),
        dry_run=False,
        secrets=[],
    )
    at = _render(mp, T0)
    eia, ercot, gen, price = _items(at)
    assert eia["Last attempted collection"] == "none recorded"
    assert eia["Last refresh including this source"].startswith(
        "failed (refresh started 2026-03-10"
    )
    assert ercot["Last refresh including this source"].startswith("succeeded")
    assert any("last refresh" in e.value and "CredentialError" in e.value for e in at.error)
