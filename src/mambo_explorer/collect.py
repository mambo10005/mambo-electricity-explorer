"""Plan, fetch, normalize, and store one bounded EIA-930 collection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from mambo_explorer.eia import dataset as ds
from mambo_explorer.eia.client import EIAClient, EIAError, Page
from mambo_explorer.storage import Store, now_utc

MAX_DAYS_PER_RUN = 31  # including revision lookback
DEFAULT_DAYS = 7
DEFAULT_LOOKBACK_DAYS = 2
RETRY_ALLOWANCE = 6


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class Plan:
    entity: str
    metrics: tuple[str, ...]
    start_day: date  # first requested day (UTC)
    end_day: date  # exclusive
    lookback_days: int
    page_size: int
    max_requests: int

    @property
    def fetch_start_day(self) -> date:
        return self.start_day - timedelta(days=self.lookback_days)

    @property
    def start_period(self) -> str:
        return ds.first_period(self.fetch_start_day)

    @property
    def end_period(self) -> str:
        return ds.last_period(self.end_day)

    @property
    def fetch_days(self) -> int:
        return (self.end_day - self.fetch_start_day).days

    @property
    def expected_rows(self) -> int:
        return self.fetch_days * 24 * len(self.metrics)

    @property
    def pages_needed(self) -> int:
        return max(1, math.ceil(self.expected_rows / self.page_size))

    def describe(self) -> dict:
        return {
            "source": f"EIA API v2, route {ds.ROUTE} ({ds.DATASET})",
            "entity": f"{self.entity} ({ds.ENTITY_NAMES.get(self.entity, 'unverified')})",
            "metrics": {m: ds.METRIC_NAMES[m] for m in self.metrics},
            "frequency": ds.FREQUENCY,
            "requested_days_utc": f"{self.start_day} .. {self.end_day - timedelta(days=1)}",
            "revision_lookback_days": self.lookback_days,
            "period_range": f"{self.start_period} .. {self.end_period}",
            "expected_rows_max": self.expected_rows,
            "page_size": self.page_size,
            "pages_needed": self.pages_needed,
            "request_budget": self.max_requests,
            "credential": "read from EIA_API_KEY at run time (never shown)",
        }


def plan_collection(
    *,
    days: int = DEFAULT_DAYS,
    start: date | None = None,
    end: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    page_size: int = ds.MAX_ROWS_PER_REQUEST,
    max_requests: int | None = None,
    today: date | None = None,
) -> Plan:
    """Build a bounded plan over completed UTC days. Rejects unbounded or future scopes."""
    today = today or datetime.now(UTC).date()
    end = end or today
    start = start or end - timedelta(days=days)
    if end > today:
        raise PlanError(f"end {end} is in the future; only completed UTC days are collected")
    if start >= end:
        raise PlanError("start must be before end")
    if lookback_days < 0:
        raise PlanError("lookback_days must be >= 0")
    total = (end - start).days + lookback_days
    if total > MAX_DAYS_PER_RUN:
        raise PlanError(
            f"{total} days including lookback exceeds the per-run maximum of {MAX_DAYS_PER_RUN}"
        )
    if not 1 <= page_size <= ds.MAX_ROWS_PER_REQUEST:
        raise PlanError(f"page_size must be 1..{ds.MAX_ROWS_PER_REQUEST}")
    plan = Plan(ds.ENTITY, tuple(sorted(ds.METRICS)), start, end, lookback_days, page_size, 0)
    budget = plan.pages_needed + RETRY_ALLOWANCE
    if max_requests is not None and max_requests < plan.pages_needed:
        raise PlanError(
            f"max_requests {max_requests} is below the {plan.pages_needed} pages this plan needs"
        )
    return Plan(**{**plan.__dict__, "max_requests": max_requests or budget})


def normalize(
    pages: list[Page],
    archives: dict[int, tuple[str, str]],
    *,
    run_id: str,
    plan: Plan,
    retrieved_at: datetime,
) -> list[dict]:
    """Turn validated rows into observation records. Never imputes, clips, or drops values."""
    records = []
    for page in pages:
        archive_path, archive_sha = archives[page.offset]
        for row in page.rows:
            raw = row["value"]
            value, flags = ds.parse_value(raw)
            start_utc, end_utc = ds.interval_utc(row["period"])
            records.append(
                {
                    "source": ds.SOURCE,
                    "dataset": ds.DATASET,
                    "route": ds.ROUTE,
                    "frequency": ds.FREQUENCY,
                    "entity": row["respondent"],
                    "entity_name": row.get("respondent-name"),
                    "metric": row["type"],
                    "metric_name": row.get("type-name"),
                    "period": row["period"],
                    "interval_start_utc": start_utc,
                    "interval_end_utc": end_utc,
                    "value_raw": None if raw is None else str(raw),
                    "value": value,
                    "unit": row[ds.UNITS_FIELD],
                    "quality_flags": ",".join(flags),
                    "revision": 0,
                    "retrieved_at_utc": retrieved_at,
                    "publication_time_utc": None,  # not provided by the source
                    "request_start": plan.start_period,
                    "request_end": plan.end_period,
                    "run_id": run_id,
                    "archive_path": archive_path,
                    "archive_sha256": archive_sha,
                }
            )
    return records


def assign_revisions(store: Store, records: list[dict], plan: Plan) -> tuple[list[dict], dict]:
    """Keep only new or changed observations, numbering revisions per identity."""
    latest = store.latest_by_identity(
        plan.entity, list(plan.metrics), plan.start_period, plan.end_period
    )
    keep, counts = [], {"rows_new": 0, "rows_revised": 0, "rows_unchanged": 0}
    for record in records:
        previous = latest.get((record["metric"], record["period"]))
        if previous is None:
            record["revision"] = 1
            counts["rows_new"] += 1
        elif (previous[0], previous[1]) == (record["value_raw"], record["unit"]):
            counts["rows_unchanged"] += 1
            continue
        else:
            record["revision"] = previous[2] + 1
            counts["rows_revised"] += 1
        keep.append(record)
    return keep, counts


def collect(plan: Plan, client: EIAClient, store: Store) -> dict:
    """Run one collection under the writer lock. Returns a summary (no credentials)."""
    with store.writer_lock():
        run_id = store.start_run(
            entity=plan.entity,
            metrics=",".join(plan.metrics),
            request_start=plan.start_period,
            request_end=plan.end_period,
            lookback_days=plan.lookback_days,
        )
        try:
            pages = client.fetch_region_data(
                plan.entity,
                list(plan.metrics),
                plan.start_period,
                plan.end_period,
                page_size=plan.page_size,
                max_rows=plan.expected_rows,
            )
            retrieved_at = now_utc()
            files = [store.write_raw(run_id, p.offset, p.body, p.sanitized) for p in pages]
            archives = {p.offset: (f.path, f.sha256) for p, f in zip(pages, files, strict=True)}
            records = normalize(
                pages, archives, run_id=run_id, plan=plan, retrieved_at=retrieved_at
            )
            keep, counts = assign_revisions(store, records, plan)
            files += store.write_observations(run_id, keep)
            stats = client.stats
            store.commit_run(
                run_id,
                files,
                requests=stats.requests,
                retries=stats.retries,
                pages=stats.pages,
                rows_received=len(records),
                **counts,
            )
        except EIAError as exc:
            store.fail_run(
                run_id, str(exc), requests=client.stats.requests, retries=client.stats.retries
            )
            raise
    return {
        "run_id": run_id,
        "requests": client.stats.requests,
        "retries": client.stats.retries,
        "pages": client.stats.pages,
        "rows_received": len(records),
        "sanitized_pages": sum(p.sanitized for p in pages),
        **counts,
    }
