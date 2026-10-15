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
# Display abbreviation only; the stored unit is always the source string.
UNIT_LABELS = {"megawatthours": "MWh"}


def unit_label(unit: str | None) -> str:
    return UNIT_LABELS.get(unit or "", unit or "")


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


def sort_params(facet: str = "type") -> tuple[tuple[str, str], ...]:
    """Deterministic order (period, respondent, series facet) for any EIA-930 route."""
    return tuple((k, facet if v == "type" else v) for k, v in SORT_PARAMS)


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


# --- Hourly net generation by energy source (Stage 16; ADR 0014) ----------------------------
# Facts below were read from the live API metadata on 2026-10-12 (parent route listing,
# route metadata, facet values; 4 requests) and from the Form EIA-930 instructions (OMB
# 1905-0129, expiration 07/31/2029) and the "About the EIA-930 data" page. See
# docs/datasets/eia930-fuel-type-data.md and docs/source-register.md.
GENERATION_ROUTE = "electricity/rto/fuel-type-data"  # "Hourly Generation by Energy Source"
GENERATION_FACET = "fueltype"  # facet description: "Energy Source"
GENERATION_METRIC = "NG"  # Form EIA-930 data type for net generation
GENERATION_VALUE_ALIAS = "Net Generation"  # API data column alias; units megawatthours
GENERATION_START_PERIOD = "2019-01-01T00"  # API metadata startPeriod (by-source data from 2018-07)
GENERATION_STORE = "eia930-fuel-type"  # separate namespace: never mixes with demand/forecast
GENERATION_REQUIRED_FIELDS = ("period", "respondent", GENERATION_FACET, "value", "value-units")
GENERATION_NAME_FIELD = "type-name"  # optional in rows; stored when present

# Energy-source codes from the Form EIA-930 instructions ("Data Code" for data type NG).
# Order: as listed in the instructions. Names are the instruction wording, shortened.
ENERGY_SOURCE_NAMES = {
    "COL": "Coal",
    "NG": "Natural gas",
    "NUC": "Nuclear",
    "OIL": "Petroleum (all products)",
    "WAT": "Hydro (excluding pumped storage, unless combined)",
    "PS": "Pumped storage",
    "SUN": "Solar (without integrated battery storage)",
    "SNB": "Solar with integrated battery storage",
    "WND": "Wind (without integrated battery storage)",
    "WNB": "Wind with integrated battery storage",
    "BAT": "Battery storage",
    "OES": "Other energy storage",
    "GEO": "Geothermal",
    "OTH": "Other (all other sources; also used to mask small categories)",
    "UNK": "Unknown",
    # Present in the API facet list (2026-10-12) but not in the instructions read.
    "UES": "Unknown energy storage (API facet; not in the form instructions)",
}
ENERGY_SOURCE_CODES = tuple(ENERGY_SOURCE_NAMES)
# Categories the instructions say may be reported negative in an hour of net storage.
# A combined hydro report (WAT including pumped storage) may also be negative.
STORAGE_CODES = ("PS", "BAT", "OES", "SNB", "WNB", "UES")
# Scope guard for one fetch: more categories than this is treated as an unexpected response.
MAX_CATEGORIES = 24

GENERATION_INTERVAL_TEXT = INTERVAL_TEXT  # same period labels and the same unverified convention
STORAGE_TEXT = (
    "Form EIA-930 instructions: for hours when storage devices store more electricity than "
    "they generate, the net storage is reported as negative net generation for that "
    "category; hydro combined with pumped storage may also be negative. EIA's 'About the "
    "EIA-930 data' page adds that it has asked balancing authorities to count pumped-storage "
    "negative net generation as demand instead, and accepts negative values where a BA has "
    "said it reports battery charging. Which convention ERCOT follows is not stated per "
    "balancing authority, so this app shows signed values exactly as published."
)
NET_GENERATION_TEXT = (
    "EIA describes net generation as the metered output of generating units managed by, or "
    "visible to, the balancing authority; distribution-connected generation such as rooftop "
    "solar is typically not included. The form instructions say station use above gross "
    "output yields negative net generation, so values are net of station use. This is not "
    "installed capacity, fuel consumption, or marginal generation."
)


def energy_source_name(code: str) -> str:
    return ENERGY_SOURCE_NAMES.get(code, f"{code} (not in the reviewed code list)")


def generation_review_summary() -> dict:
    return {
        "source": f"{SOURCE} Open Data API v2",
        "dataset": DATASET,
        "route": GENERATION_ROUTE,
        "facet": GENERATION_FACET,
        "frequency": FREQUENCY,
        "entity": {ENTITY: ENTITY_NAMES[ENTITY]},
        "energy_sources": ENERGY_SOURCE_NAMES,
        "expected_unit": EXPECTED_UNIT,
        "interval": GENERATION_INTERVAL_TEXT,
        "storage_sign": STORAGE_TEXT,
        "review": "docs/source-register.md — EIA-930 fuel-type-data review",
    }


def verify_generation_metadata(client) -> dict:
    """Check the reviewed generation route, facet, entity, and codes against live metadata."""
    meta = client.route_metadata(GENERATION_ROUTE)
    facets = {f.get("id") for f in meta.get("facets", []) if isinstance(f, dict)}
    respondents = {v.get("id") for v in client.facet_values("respondent", GENERATION_ROUTE)}
    codes = {v.get("id") for v in client.facet_values(GENERATION_FACET, GENERATION_ROUTE)}
    frequencies = {f.get("id") for f in meta.get("frequency", []) if isinstance(f, dict)}
    units = (meta.get("data") or {}).get("value", {}).get("units")
    result = {
        "route_id": meta.get("id"),
        "frequency_available": FREQUENCY in frequencies,
        "facet_found": GENERATION_FACET in facets,
        "entity_found": ENTITY in respondents,
        "units": units,
        "codes_not_reviewed": sorted(codes - set(ENERGY_SOURCE_CODES)),
        "reviewed_codes_absent": sorted(set(ENERGY_SOURCE_CODES) - codes),
        "requests_used": client.stats.requests,
    }
    result["ok"] = (
        result["frequency_available"]
        and result["facet_found"]
        and result["entity_found"]
        and units == EXPECTED_UNIT
    )
    return result
