"""Shared offline helpers for refresh and health tests. All data here is SYNTHETIC."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qsl, urlsplit

import yaml
from eia_fixtures import FAKE_KEY, response_body, synthetic_rows
from ercot_fixtures import FakeErcot, day_doc

from mambo_explorer import refresh_config
from mambo_explorer.eia.client import EIAClient
from mambo_explorer.ercot import collect as ercot_collect
from mambo_explorer.ercot.client import ErcotClient
from mambo_explorer.storage import Store

T0 = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)  # fixed test "now"; never today's date


class Clock:
    """Controllable clock for the stores' run timestamps and the refresh `now`."""

    def __init__(self, start: datetime = T0):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now = self.now + timedelta(**delta)


class WindowEIA:
    """Serves synthetic D/DF rows for exactly the requested start/end window.

    overrides: (type, period) -> value. fail: an exception or (status, body) returned first.
    """

    def __init__(self, overrides=None, fail=None):
        self.overrides = overrides or {}
        self.fail = fail
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float):
        self.urls.append(url)
        if self.fail is not None:
            if isinstance(self.fail, Exception):
                raise self.fail
            return self.fail
        params = dict(parse_qsl(urlsplit(url).query))
        first = date.fromisoformat(params["start"][:10])
        last = date.fromisoformat(params["end"][:10])
        rows = synthetic_rows(first, (last - first).days + 1, overrides=self.overrides)
        offset, length = int(params.get("offset", 0)), int(params.get("length", 5000))
        return 200, response_body(rows[offset : offset + length], total=len(rows))


def ercot_docs(last_day: date, count: int, *, hour=5) -> dict:
    """`count` synthetic documents ending at OperDay `last_day`, oldest first."""
    docs = {}
    for i in range(count):
        day = last_day - timedelta(days=count - 1 - i)
        published = f"{day + timedelta(days=1)}T0{hour}:50:00-05:00"
        docs.update(dict([day_doc(day, str(1000 + day.toordinal() % 1000), published)]))
    return docs


def stores(data_dir) -> dict[str, Store]:
    return {"eia": Store(data_dir), "ercot": ercot_collect.store(data_dir)}


def clients(eia_transport=None, ercot_transport=None, key: str | None = FAKE_KEY):
    return {
        "eia": lambda budget: EIAClient(
            key, transport=eia_transport or WindowEIA(), max_requests=budget, sleep=lambda s: None
        ),
        "ercot": lambda budget: ErcotClient(
            transport=ercot_transport or FakeErcot({}), max_requests=budget, sleep=lambda s: None
        ),
    }


def config(**changes):
    data = yaml.safe_load(refresh_config.default_text())
    for dotted, value in changes.items():
        node = data
        *path, last = dotted.split("__")
        for key in path:
            node = node[key]
        node[last] = value
    return refresh_config.validate(data)


def patch_clock(monkeypatch, clock: Clock) -> None:
    """Stores and collectors stamp runs and retrievals with this clock."""
    from mambo_explorer import collect, storage
    from mambo_explorer.ercot import collect as ec

    for module in (storage, collect, ec):
        monkeypatch.setattr(module, "now_utc", clock)
