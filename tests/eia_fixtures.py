"""SYNTHETIC EIA API v2-shaped responses for offline tests.

These are not saved EIA responses: no values here were ever retrieved from EIA, and
no API key was available when they were written (2026-10-11). The structure follows
the reviewed route documentation (docs/source-register.md). The values are made up
and labeled synthetic. Do not use them as observations.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlsplit

# A fake credential with characters that change under URL encoding, used to test
# redaction of raw, percent-encoded, and plus-encoded forms. Not a real key.
FAKE_KEY = "fake+k3y/with=chars&more"


def synthetic_rows(start: date, days: int, *, overrides: dict | None = None) -> list[dict]:
    """Hourly D and DF rows sorted by (period, respondent, type).

    overrides maps (type, period) to a replacement value.
    """
    overrides = overrides or {}
    rows = []
    t0 = datetime(start.year, start.month, start.day)
    for hour in range(days * 24):
        period = (t0 + timedelta(hours=hour)).strftime("%Y-%m-%dT%H")
        for code, name, base in (
            ("D", "Demand", 40000),
            ("DF", "Day-ahead demand forecast", 40500),
        ):
            value = overrides.get((code, period), str(base + (hour % 24) * 100))
            rows.append(
                {
                    "period": period,
                    "respondent": "ERCO",
                    "respondent-name": "Electric Reliability Council of Texas, Inc.",
                    "type": code,
                    "type-name": name,
                    "value": value,
                    "value-units": "megawatthours",
                }
            )
    return rows


def response_body(rows: list[dict], total: int | None = None, echo_key: str | None = None) -> bytes:
    payload = {
        "response": {
            "total": str(len(rows) if total is None else total),
            "dateFormat": 'YYYY-MM-DD"T"HH24',
            "frequency": "hourly",
            "data": rows,
            "description": "SYNTHETIC test fixture",
        },
        "request": {"command": "/v2/electricity/rto/region-data/data/", "params": {}},
        "apiVersion": "synthetic",
    }
    if echo_key is not None:
        payload["request"]["params"]["api_key"] = echo_key
    return json.dumps(payload).encode("utf-8")


class FakeEIA:
    """Transport that serves synthetic rows with real offset/length paging semantics."""

    def __init__(self, rows: list[dict], *, echo_key: bool = True, script: list | None = None):
        self.rows = rows
        self.echo_key = echo_key
        self.script = list(script or [])  # queued (status, body) or exceptions to emit first
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> tuple[int, bytes]:
        self.urls.append(url)
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        params = dict(parse_qsl(urlsplit(url).query))
        offset, length = int(params.get("offset", 0)), int(params.get("length", 5000))
        page = self.rows[offset : offset + length]
        return 200, response_body(page, total=len(self.rows), echo_key=params.get("api_key"))
