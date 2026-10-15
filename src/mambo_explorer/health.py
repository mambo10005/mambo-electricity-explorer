"""Read-only health facts for System Health (HEALTH-01, ADR 0013).

Nothing here sends a request or writes a file: it reads each store's catalog and committed
Parquet files, the refresh logs, and the content metadata.

Kept apart on purpose:
- last attempted collection vs last successful collection (catalog runs);
- latest observation LABEL (as the source wrote it) vs publication time (only when the source
  provides one) vs retrieval time (when this computer downloaded it);
- freshness, which is judged from the observation label (EIA, UTC labels) or the source's
  publication time (ERCOT), never from when a request succeeded.
Freshness is "unknown" when it cannot be determined.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import duckdb

from mambo_explorer import refresh
from mambo_explorer.eia import dataset as eia_ds
from mambo_explorer.refresh_config import RefreshConfig
from mambo_explorer.storage import Store

FRESH, STALE, UNKNOWN, NO_DATA = "fresh", "stale", "unknown", "no data"


@dataclass
class SourceHealth:
    source: str
    title: str
    collected: bool
    last_attempt: dict | None
    last_success: dict | None
    latest_label: str | None
    publication_time: str  # a timestamp, or an explanation of why there is none
    retrieval_time: str | None
    freshness: str
    freshness_basis: str
    threshold_hours: int
    coverage: dict = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    storage: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # From refresh logs: a refresh can fail before a collector starts (e.g. no credential),
    # which leaves no catalog run. None when no refresh has included this source.
    last_refresh: dict | None = None


def _from_us(value) -> datetime | None:
    """DuckDB epoch microseconds to an aware UTC datetime (avoids a pytz dependency)."""
    return None if value is None else datetime.fromtimestamp(value / 1_000_000, UTC)


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        value = _from_us(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _unreadable(base: dict, exc: Exception) -> SourceHealth:
    base["problems"] = [*base["problems"], f"observations could not be read: {type(exc).__name__}"]
    return SourceHealth(
        collected=True,
        latest_label=None,
        retrieval_time=None,
        freshness=UNKNOWN,
        freshness_basis="the stored observations could not be read; run `mambo validate`",
        **base,
    )


def _attempt(run: dict | None) -> dict | None:
    if not run:
        return None
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "started_at": run["started_at"],
        "finished_at": run.get("finished_at"),
        "requests": run.get("requests"),
        "rows_new": run.get("rows_new"),
        "rows_revised": run.get("rows_revised"),
        "rows_unchanged": run.get("rows_unchanged"),
        "error": run.get("error"),
    }


def _problems(store: Store, history: dict) -> tuple[list[str], dict]:
    problems = []
    since = history["last_success"]["started_at"] if history["last_success"] else ""
    for run in store.runs(limit=10_000):
        if run["started_at"] > since and run["status"] == "failed":
            problems.append(f"failed run {run['run_id']}: {run.get('error') or 'no detail'}")
        if run["status"] == "started":
            problems.append(f"interrupted run {run['run_id']} (still 'started')")
    report = store.validate() if store.exists() else None  # read-only: no flags
    storage = (
        {"status": "not created yet"}
        if report is None
        else {
            "status": "ok" if report["ok"] and not report["orphans"] else "problems found",
            "missing_files": len(report["missing"]),
            "checksum_mismatches": len(report["checksum_mismatch"]),
            "orphan_files": len(report["orphans"]),
            "interrupted_runs": len(report["interrupted"]),
            "writer_lock_held": report["lock_held"],
        }
    )
    if report and not report["ok"]:
        problems.append("storage validation failed: missing files or checksum mismatches")
    return problems, storage


def _unchanged_note(history: dict) -> list[str]:
    s = history["last_success"]
    if s and not s.get("rows_new") and not s.get("rows_revised"):
        return [
            "The last successful collection found no new or revised rows. That is not a "
            "failure: the source may simply not have published anything new."
        ]
    return []


def _freshness(age: timedelta | None, threshold_hours: int) -> str:
    if age is None:
        return UNKNOWN
    return FRESH if age <= timedelta(hours=threshold_hours) else STALE


def eia_health(
    store: Store, config: RefreshConfig, now: datetime, source: str = "eia"
) -> SourceHealth:
    """Demand/forecast or generation (source "eia-generation"): each from its own store."""
    s = config.source(source)
    by_category = source == "eia-generation"
    series_col = "energy_source" if by_category else "metric"
    history = refresh.run_history(store)
    problems, storage = _problems(store, history)
    base = dict(
        source=source,
        title=s.title,
        last_attempt=_attempt(history["last_attempt"]),
        last_success=_attempt(history["last_success"]),
        publication_time="not provided by EIA (no per-value publication time)",
        threshold_hours=s.freshness_threshold_hours,
        problems=problems,
        storage=storage,
    )
    if not store.committed_files("observations"):
        return SourceHealth(
            collected=False,
            latest_label=None,
            retrieval_time=None,
            freshness=NO_DATA,
            freshness_basis="nothing has been collected",
            **base,
        )
    try:
        with store.query() as con:
            latest_period, retrieved = con.execute(
                "SELECT max(period), epoch_us(max(retrieved_at_utc)) FROM latest"
            ).fetchone()
            per_metric = con.execute(
                f"SELECT {series_col}, min(period), max(period), count(*), "
                "count(*) FILTER (WHERE value IS NULL), count(*) FILTER (WHERE value < 0) "
                f"FROM latest GROUP BY {series_col} ORDER BY {series_col}"
            ).fetchall()
    except (duckdb.Error, OSError) as exc:
        return _unreadable(base, exc)
    coverage = {}
    for metric, first, last, rows, nulls, negatives in per_metric:
        span = (
            int((eia_ds.parse_period(last) - eia_ds.parse_period(first)).total_seconds() // 3600)
            + 1
        )
        coverage[metric] = {
            "first_label": first,
            "last_label": last,
            "hours_in_span": span,
            "rows_present": rows,
            "hours_absent": span - rows,
            "null_values": nulls,
        }
        if by_category:
            coverage[metric]["negative_values"] = negatives
    age = now - eia_ds.parse_period(latest_period) if latest_period else None
    notes = _unchanged_note(history) + [
        "Absent hours are counted, never filled. An absent hour is not proof of a missed job."
    ]
    if by_category:
        notes.append(
            "Coverage is per energy-source category. A category absent from an hour is not "
            "zero, and the categories present do not add up to total system generation."
        )
    return SourceHealth(
        collected=True,
        latest_label=f"period {latest_period} (UTC label)",
        retrieval_time=_iso(retrieved),
        freshness=_freshness(age, s.freshness_threshold_hours),
        freshness_basis=(
            "age of the latest observation label (UTC); EIA has not confirmed whether the "
            "label marks the start or end of the hour, so ages are uncertain by one hour"
        ),
        coverage=coverage,
        notes=notes,
        **base,
    )


def ercot_health(store: Store, config: RefreshConfig, now: datetime) -> SourceHealth:
    s = config.ercot
    history = refresh.run_history(store)
    problems, storage = _problems(store, history)
    base = dict(
        source="ercot",
        title=s.title,
        last_attempt=_attempt(history["last_attempt"]),
        last_success=_attempt(history["last_success"]),
        threshold_hours=s.freshness_threshold_hours,
        problems=problems,
        storage=storage,
    )
    if not store.committed_files("observations"):
        return SourceHealth(
            collected=False,
            latest_label=None,
            publication_time="nothing collected",
            retrieval_time=None,
            freshness=NO_DATA,
            freshness_basis="nothing has been collected",
            **base,
        )
    try:
        with store.query() as con:
            oper_day, published_raw, published, retrieved = con.execute(
                "SELECT oper_day, publish_time_raw, epoch_us(publication_time_utc), "
                "epoch_us(retrieved_at_utc) FROM latest "
                "ORDER BY oper_date DESC, publication_time_utc DESC LIMIT 1"
            ).fetchone()
            last_hour = con.execute(
                "SELECT max(hour_ending) FROM latest WHERE oper_day = ?", [oper_day]
            ).fetchone()[0]
            first_date, last_date, days, rows, nulls = con.execute(
                "SELECT min(oper_date), max(oper_date), count(DISTINCT oper_date), "
                "count(DISTINCT (oper_day, hour_ending, dst_flag)), "
                "count(*) FILTER (WHERE value IS NULL) FROM latest WHERE entity = 'TOTAL'"
            ).fetchone()
    except (duckdb.Error, OSError) as exc:
        return _unreadable({**base, "publication_time": "unknown"}, exc)
    published = _from_us(published)
    span_days = (last_date - first_date).days + 1 if isinstance(first_date, date) else 0
    age = now - published if isinstance(published, datetime) else None
    return SourceHealth(
        collected=True,
        latest_label=f"OperDay {oper_day}, HourEnding {last_hour} (ERCOT labels; not converted)",
        publication_time=f"{published_raw} (ERCOT listing PublishDate)",
        retrieval_time=_iso(retrieved),
        freshness=_freshness(age, s.freshness_threshold_hours),
        freshness_basis="age of the latest document's publication time, as ERCOT states it",
        coverage={
            "TOTAL": {
                "first_oper_date": str(first_date),
                "last_oper_date": str(last_date),
                "oper_days_in_span": span_days,
                "oper_days_present": days,
                "oper_days_absent": span_days - days,
                "hour_rows_present": rows,
                "null_values": nulls,
            }
        },
        notes=_unchanged_note(history)
        + [
            "Hours per OperDay vary on DST days, so hours are not compared with 24 × days.",
            "ERCOT's public list keeps about 31 days; older OperDays are not available through "
            "the access method this app implements.",
        ],
        **base,
    )


def last_refresh(logs: list[dict], source: str) -> dict | None:
    """Newest refresh-log result for `source` (logs newest first; dry runs are ignored)."""
    for log in logs:
        if log.get("dry_run"):
            continue
        for result in log.get("results", []):
            if result.get("source") == source:
                return {
                    "started_at": log.get("started_at_utc"),
                    "status": result.get("status"),
                    "error": result.get("error"),
                }
    return None


def source_health(
    stores: dict[str, Store], config: RefreshConfig, now: datetime, logs: list[dict] | None = None
) -> list[SourceHealth]:
    out = [eia_health(stores["eia"], config, now), ercot_health(stores["ercot"], config, now)]
    if "eia-generation" in stores:
        out.append(eia_health(stores["eia-generation"], config, now, "eia-generation"))
    if "ercot-dam-spp" in stores:
        out.append(price_health(stores["ercot-dam-spp"], config, now))
    for h in out:
        h.last_refresh = last_refresh(logs or [], h.source)
        if h.last_refresh and h.last_refresh["status"] == "failed":
            h.problems.append(
                f"last refresh ({h.last_refresh['started_at']}) failed: {h.last_refresh['error']}"
            )
    return out


def content_health() -> dict:
    """Content versions and review state. No content is monitored for source changes."""
    from mambo_explorer import responsibilities
    from mambo_explorer.lessons import load_lessons

    lessons = []
    for lesson in load_lessons():
        meta = lesson.meta
        accessed = [str(s["accessed"]) for s in meta["sources"]]
        lessons.append(
            {
                # "1. x" would render as a Markdown list in st.table
                "Lesson": f"Lesson {meta['order']}: {lesson.title}",
                "Content version": str(meta["content_version"]),
                "Source review date": max(accessed) if accessed else "no external source",
                "Human review": meta["review_status"],
                "Automatic change monitoring": "none",
            }
        )
    cat = responsibilities.load()
    statuses = sorted({r["human_review_status"] for r in cat.records})
    records = {
        "Record set version": cat.set_version,
        "Source review date": str(cat.retrieved_at),
        "Records": len(cat.records),
        "Human review": ", ".join(statuses),
        "Automatic change monitoring": "none",
    }
    return {"lessons": lessons, "records": records}


def price_health(store: Store, config: RefreshConfig, now: datetime) -> SourceHealth:
    """ERCOT NP4-190-CD DAM price at HB_NORTH: labels as published; finality not determined."""
    from mambo_explorer.ercot import prices as px

    s = config.prices
    history = refresh.run_history(store)
    problems, storage = _problems(store, history)
    base = dict(
        source="ercot-dam-spp",
        title=s.title,
        last_attempt=_attempt(history["last_attempt"]),
        last_success=_attempt(history["last_success"]),
        threshold_hours=s.freshness_threshold_hours,
        problems=problems,
        storage=storage,
    )
    if not store.committed_files("observations"):
        return SourceHealth(
            collected=False,
            latest_label=None,
            publication_time="nothing collected",
            retrieval_time=None,
            freshness=NO_DATA,
            freshness_basis="nothing has been collected",
            **base,
        )
    try:
        with store.query() as con:
            day, hour, published_raw, published, retrieved = con.execute(
                "SELECT delivery_date_raw, hour_ending, publish_time_raw, "
                "epoch_us(publication_time_utc), epoch_us(retrieved_at_utc) FROM latest "
                "ORDER BY delivery_date DESC, row_order DESC LIMIT 1"
            ).fetchone()
            first, last, days, rows, nulls, negatives, revised = con.execute(
                "SELECT min(delivery_date), max(delivery_date), count(DISTINCT delivery_date), "
                "count(*), count(*) FILTER (WHERE value IS NULL), "
                "count(*) FILTER (WHERE value < 0), count(*) FILTER (WHERE revision > 1) "
                "FROM latest"
            ).fetchone()
    except (duckdb.Error, OSError) as exc:
        return _unreadable({**base, "publication_time": "unknown"}, exc)
    published = _from_us(published)
    span = (last - first).days + 1 if isinstance(first, date) else 0
    age = now - published if isinstance(published, datetime) else None
    return SourceHealth(
        collected=True,
        latest_label=f"DeliveryDate {day}, HourEnding {hour} (ERCOT labels; not converted)",
        publication_time=f"{published_raw} (ERCOT listing PublishDate)",
        retrieval_time=_iso(retrieved),
        freshness=_freshness(age, s.freshness_threshold_hours),
        freshness_basis="age of the latest document's publication time, as ERCOT states it",
        coverage={
            px.LOCATION: {
                "first_delivery_date": str(first),
                "last_delivery_date": str(last),
                "delivery_dates_in_span": span,
                "delivery_dates_present": days,
                "delivery_dates_absent": span - days,
                "hour_rows_present": rows,
                "null_values": nulls,
                "negative_prices": negatives,
                "revised_hours": revised,
            }
        },
        notes=_unchanged_note(history)
        + [
            "Finality: " + px.FINALITY_TEXT,
            "Only HB_NORTH is stored; each downloaded document holds every settlement point.",
            f"ERCOT's public list keeps about {px.PUBLIC_RETENTION_DAYS} days; older "
            "DeliveryDates are not available through the access method this app implements.",
        ],
        **base,
    )
