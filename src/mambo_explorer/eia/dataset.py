"""Reviewed facts about the one dataset this stage collects. Single source of truth.

Every constant here is backed by docs/source-register.md ("EIA-930 region-data review").
Change them only together with that review.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

SOURCE = "EIA"
DATASET = "EIA-930"
ROUTE = "electricity/rto/region-data"
FREQUENCY = "hourly"  # UTC periods; "local-hourly" is a separate frequency not used here
MAX_ROWS_PER_REQUEST = 5000  # JSON responses (EIA API FAQ)

ENTITY = "ERCO"
ENTITY_NAMES = {"ERCO": "Electric Reliability Council of Texas, Inc."}
METRICS = ("D", "DF")
METRIC_NAMES = {"D": "Demand", "DF": "Day-ahead demand forecast"}
# Short enough not to be truncated in the chart legend; the page caption explains
# that the forecast is published by the balancing authority, not made by this app.
DISPLAY_NAMES = {"D": "Actual demand", "DF": "Day-ahead forecast"}
EXPECTED_UNIT = "megawatthours"

# Field names confirmed by the first live collection (2026-10-11, apiVersion 2.1.14).
REQUIRED_FIELDS = ("period", "respondent", "type", "value", "value-units")
UNITS_FIELD = "value-units"
PERIOD_PATTERN = r"\d{4}-\d{2}-\d{2}T\d{2}"
PERIOD_FORMAT = "%Y-%m-%dT%H"
SORT_PARAMS = (
    ("sort[0][column]", "period"),
    ("sort[0][direction]", "asc"),
    ("sort[1][column]", "respondent"),
    ("sort[1][direction]", "asc"),
    ("sort[2][column]", "type"),
    ("sort[2][direction]", "asc"),
)

# How a period label maps to a UTC interval. EIA documents the hour-ending convention
# for EIA-930 (Grid Monitor "about" page, Form EIA-930 instructions), but not for the
# API's `period` field itself, so it is NOT treated as verified: interval columns stay
# null until EIA states it for the API. The 2026-10-11 live response is consistent with
# hour-ending (a missing forecast block spans exactly one Central-time day under that
# reading) but the API response itself does not state the convention.
INTERVAL_CONVENTION: str | None = None
INTERVAL_TEXT = (
    "Hourly values (EIA: time-weighted hourly averages, so MW and MWh for the hour are "
    "numerically equal). The period label is UTC. EIA-930 documentation describes an "
    "hour-ending convention ('01:00' = the hour ending 01:00), but this is not stated for "
    "the API field, so this app shows the period exactly as labeled and does not derive "
    "interval start/end times."
)


def first_period(day: date) -> str:
    """Earliest period label belonging to a UTC day under the convention in use."""
    return f"{day.isoformat()}T00"


def last_period(end_day_exclusive: date) -> str:
    return f"{(end_day_exclusive - timedelta(days=1)).isoformat()}T23"


def parse_period(period: str) -> datetime:
    return datetime.strptime(period, PERIOD_FORMAT).replace(tzinfo=UTC)


def interval_utc(period: str) -> tuple[datetime | None, datetime | None]:
    stamp = parse_period(period)
    if INTERVAL_CONVENTION == "hour_ending":
        return stamp - timedelta(hours=1), stamp
    if INTERVAL_CONVENTION == "hour_beginning":
        return stamp, stamp + timedelta(hours=1)
    return None, None


def parse_value(raw: object) -> tuple[float | None, list[str]]:
    """Parse a source value without imputing, clipping, or replacing anything."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, ["missing"]
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, ["non_numeric"]
    if not math.isfinite(value):
        return None, ["non_numeric"]
    return value, (["negative"] if value < 0 else [])


def review_summary() -> dict:
    return {
        "source": f"{SOURCE} Open Data API v2",
        "dataset": DATASET,
        "route": ROUTE,
        "frequency": FREQUENCY,
        "entity": {ENTITY: ENTITY_NAMES[ENTITY]},
        "metrics": METRIC_NAMES,
        "expected_unit": EXPECTED_UNIT,
        "interval": INTERVAL_TEXT,
        "review": "docs/source-register.md — EIA-930 region-data review",
    }


def verify_metadata(client) -> dict:
    """Check the reviewed route, entity, and metric codes against live EIA metadata."""
    meta = client.route_metadata()
    respondents = {v.get("id"): v.get("name") for v in client.facet_values("respondent")}
    types = {v.get("id"): v.get("name") for v in client.facet_values("type")}
    frequencies = {f.get("id") for f in meta.get("frequency", []) if isinstance(f, dict)}
    result = {
        "route_id": meta.get("id"),
        "frequency_available": FREQUENCY in frequencies,
        "entity_found": ENTITY in respondents,
        "entity_name": respondents.get(ENTITY),
        "metrics_found": {m: types.get(m) for m in METRICS},
        "requests_used": client.stats.requests,
    }
    result["ok"] = (
        result["frequency_available"]
        and result["entity_found"]
        and all(result["metrics_found"].values())
    )
    return result
