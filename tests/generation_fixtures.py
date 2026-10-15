"""SYNTHETIC EIA API v2-shaped responses for the fuel-type-data route (offline tests).

No value here was retrieved from EIA. The row shape follows the live metadata read on
2026-10-12 (facets `respondent` and `fueltype`; data column `value`, units megawatthours).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlsplit

from mambo_explorer.eia import dataset as ds

# A plausible synthetic category mix: wind and solar vary by hour, battery charges at night
# (negative) and discharges in the evening (positive), nuclear flat, gas fills.
CATEGORIES = ("NG", "WND", "SUN", "NUC", "COL", "BAT")
BASE = {"NG": 20000, "WND": 9000, "SUN": 0, "NUC": 5000, "COL": 7000, "BAT": 0}


def _value(code: str, hour: int) -> int:
    h = hour % 24
    if code == "SUN":
        return max(0, 8000 - abs(h - 13) * 1200)
    if code == "BAT":
        return -600 if h < 6 else (900 if 17 <= h <= 21 else 0)
    if code == "WND":
        return 9000 + ((h * 7) % 11) * 400
    return BASE.get(code, 1000)  # any other code: a flat synthetic value


def generation_rows(
    start: date,
    days: int,
    *,
    categories: tuple[str, ...] = CATEGORIES,
    overrides: dict | None = None,
    drop: set | None = None,
) -> list[dict]:
    """Hourly rows sorted by (period, respondent, fueltype).

    overrides: (code, period) -> raw value (None = null). drop: (code, period) rows to omit.
    """
    overrides, drop = overrides or {}, drop or set()
    rows = []
    t0 = datetime(start.year, start.month, start.day)
    for hour in range(days * 24):
        period = (t0 + timedelta(hours=hour)).strftime("%Y-%m-%dT%H")
        for code in sorted(categories):
            if (code, period) in drop:
                continue
            value = overrides.get((code, period), str(_value(code, hour)))
            rows.append(
                {
                    "period": period,
                    "respondent": "ERCO",
                    "respondent-name": "Electric Reliability Council of Texas, Inc.",
                    "fueltype": code,
                    "type-name": ds.ENERGY_SOURCE_NAMES.get(code, code),
                    "value": value,
                    "value-units": "megawatthours",
                }
            )
    return rows


def response_body(rows: list[dict], total: int | None = None) -> bytes:
    payload = {
        "response": {
            "total": str(len(rows) if total is None else total),
            "dateFormat": 'YYYY-MM-DD"T"HH24',
            "frequency": "hourly",
            "data": rows,
            "description": "SYNTHETIC test fixture",
        },
        "request": {"command": "/v2/electricity/rto/fuel-type-data/data/", "params": {}},
        "apiVersion": "synthetic",
    }
    return json.dumps(payload).encode("utf-8")


class FakeGeneration:
    """Serves synthetic generation rows for the requested window with real paging."""

    def __init__(self, *, categories=CATEGORIES, overrides=None, drop=None, script=None):
        self.categories, self.overrides, self.drop = categories, overrides, drop
        self.script = list(script or [])
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float):
        self.urls.append(url)
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        params = dict(parse_qsl(urlsplit(url).query))
        assert "fuel-type-data" in url and "facets[fueltype][]" not in params
        first = date.fromisoformat(params["start"][:10])
        last = date.fromisoformat(params["end"][:10])
        rows = generation_rows(
            first,
            (last - first).days + 1,
            categories=self.categories,
            overrides=self.overrides,
            drop=self.drop,
        )
        offset, length = int(params.get("offset", 0)), int(params.get("length", 5000))
        return 200, response_body(rows[offset : offset + length], total=len(rows))
