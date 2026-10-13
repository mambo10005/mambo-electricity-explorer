"""Plan, fetch, normalize, and store one bounded EIA-930 generation-by-energy-source collection.

Reuses the EIA client (redaction, paging, budgets), the Store (archives, checksums,
Parquet, SQLite, revisions, writer lock, recovery), and the demand collector's planning
rules. The data lives in its own store namespace (ADR 0014): nothing here can touch a
demand or forecast observation. Every category the source returns is kept, including
codes outside the reviewed list (flagged, never dropped). Values keep their sign and
their unit; missing values stay missing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pyarrow as pa

from mambo_explorer import collect as demand
from mambo_explorer.eia import dataset as ds
from mambo_explorer.eia.client import EIAClient, EIAError, Page
from mambo_explorer.storage import OBSERVATION_SCHEMA, Store, now_utc

SCHEMA = pa.schema(
    [
        *[f for f in OBSERVATION_SCHEMA if f.name not in ("metric", "metric_name")],
        ("metric", pa.string()),  # always "NG" (net generation)
        ("energy_source", pa.string()),  # the fueltype code as published
        ("energy_source_name", pa.string()),  # the source's name for it, when given
    ]
)
IDENTITY = (
    "source",
    "dataset",
    "route",
    "frequency",
    "entity",
    "metric",
    "energy_source",
    "period",
)


def store(data_dir: Path) -> Store:
    return Store(data_dir, namespace=ds.GENERATION_STORE, schema=SCHEMA, identity=IDENTITY)


@dataclass(frozen=True)
class GenerationPlan:
    entity: str
    start_day: date
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
        """Page-count estimate: one row per hour per reviewed category."""
        return self.fetch_days * 24 * len(ds.ENERGY_SOURCE_CODES)

    @property
    def max_rows(self) -> int:
        """Scope guard: the most rows the source may report before the run is refused."""
        return self.fetch_days * 24 * ds.MAX_CATEGORIES

    @property
    def pages_needed(self) -> int:
        return max(1, math.ceil(self.expected_rows / self.page_size))

    def describe(self) -> dict:
        return {
            "source": f"EIA API v2, route {ds.GENERATION_ROUTE} ({ds.DATASET})",
            "entity": f"{self.entity} ({ds.ENTITY_NAMES.get(self.entity, 'unverified')})",
            "series": f"net generation by energy source (facet {ds.GENERATION_FACET}; "
            "every category the source returns is kept)",
            "reviewed_codes": list(ds.ENERGY_SOURCE_CODES),
            "frequency": ds.FREQUENCY,
            "requested_days_utc": f"{self.start_day} .. {self.end_day - timedelta(days=1)}",
            "revision_lookback_days": self.lookback_days,
            "period_range": f"{self.start_period} .. {self.end_period}",
            "expected_rows_estimate": self.expected_rows,
            "rows_refused_above": self.max_rows,
            "page_size": self.page_size,
            "pages_needed_estimate": self.pages_needed,
            "request_budget": self.max_requests,
            "store": ds.GENERATION_STORE,
            "credential": "read from EIA_API_KEY at run time (never shown)",
        }


def plan_generation(
    *,
    days: int = demand.DEFAULT_DAYS,
    start: date | None = None,
    end: date | None = None,
    lookback_days: int = demand.DEFAULT_LOOKBACK_DAYS,
    page_size: int = ds.MAX_ROWS_PER_REQUEST,
    max_requests: int | None = None,
    today: date | None = None,
) -> GenerationPlan:
    """Same bounds as the demand plan (completed UTC days, per-run maximum, page size)."""
    base = demand.plan_collection(
        days=days,
        start=start,
        end=end,
        lookback_days=lookback_days,
        page_size=page_size,
        today=today,
    )
    plan = GenerationPlan(ds.ENTITY, base.start_day, base.end_day, lookback_days, page_size, 0)
    if max_requests is not None and max_requests < plan.pages_needed:
        raise demand.PlanError(
            f"max_requests {max_requests} is below the {plan.pages_needed} pages this plan needs"
        )
    budget = max_requests or plan.pages_needed + demand.RETRY_ALLOWANCE
    return GenerationPlan(**{**plan.__dict__, "max_requests": budget})


def normalize(
    pages: list[Page],
    archives: dict[int, tuple[str, str]],
    *,
    run_id: str,
    plan: GenerationPlan,
    retrieved_at: datetime,
) -> list[dict]:
    """Observation records. Never imputes, clips, drops a category, or changes a sign."""
    records = []
    for page in pages:
        archive_path, archive_sha = archives[page.offset]
        for row in page.rows:
            raw = row["value"]
            value, flags = ds.parse_value(raw)
            code = row[ds.GENERATION_FACET]
            if code not in ds.ENERGY_SOURCE_CODES:
                flags.append("unreviewed_category")
            start_utc, end_utc = ds.interval_utc(row["period"])
            records.append(
                {
                    "source": ds.SOURCE,
                    "dataset": ds.DATASET,
                    "route": ds.GENERATION_ROUTE,
                    "frequency": ds.FREQUENCY,
                    "entity": row["respondent"],
                    "entity_name": row.get("respondent-name"),
                    "metric": ds.GENERATION_METRIC,
                    "energy_source": code,
                    "energy_source_name": row.get(ds.GENERATION_NAME_FIELD),
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


def assign_revisions(
    target: Store, records: list[dict], plan: GenerationPlan
) -> tuple[list[dict], dict]:
    """Keep new or changed observations only; revisions are numbered per (category, period)."""
    latest = target.latest_index(
        {"entity": [plan.entity], "period": sorted({r["period"] for r in records})}
    )
    keep, counts = [], {"rows_new": 0, "rows_revised": 0, "rows_unchanged": 0}
    for record in records:
        key = tuple(record[c] for c in IDENTITY)
        previous = latest.get(key)
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


def collect(plan: GenerationPlan, client: EIAClient, target: Store) -> dict:
    """One collection under the generation store's writer lock. Returns a summary."""
    with target.writer_lock():
        run_id = target.start_run(
            entity=plan.entity,
            metrics=f"{ds.GENERATION_METRIC} by {ds.GENERATION_FACET}",
            request_start=plan.start_period,
            request_end=plan.end_period,
            lookback_days=plan.lookback_days,
        )
        try:
            pages = client.fetch_series(
                ds.GENERATION_ROUTE,
                ds.GENERATION_FACET,
                plan.entity,
                None,  # every category the source has
                plan.start_period,
                plan.end_period,
                page_size=plan.page_size,
                max_rows=plan.max_rows,
                required_fields=ds.GENERATION_REQUIRED_FIELDS,
            )
            retrieved_at = now_utc()
            files = [target.write_raw(run_id, p.offset, p.body, p.sanitized) for p in pages]
            archives = {p.offset: (f.path, f.sha256) for p, f in zip(pages, files, strict=True)}
            records = normalize(
                pages, archives, run_id=run_id, plan=plan, retrieved_at=retrieved_at
            )
            keep, counts = assign_revisions(target, records, plan)
            files += target.write_observations(run_id, keep)
            stats = client.stats
            target.commit_run(
                run_id,
                files,
                requests=stats.requests,
                retries=stats.retries,
                pages=stats.pages,
                rows_received=len(records),
                **counts,
            )
        except EIAError as exc:
            target.fail_run(
                run_id, str(exc), requests=client.stats.requests, retries=client.stats.retries
            )
            raise
    categories = sorted({r["energy_source"] for r in records})
    return {
        "run_id": run_id,
        "requests": client.stats.requests,
        "retries": client.stats.retries,
        "pages": client.stats.pages,
        "rows_received": len(records),
        "categories": categories,
        "unreviewed_categories": [c for c in categories if c not in ds.ENERGY_SOURCE_CODES],
        "sanitized_pages": sum(p.sanitized for p in pages),
        **counts,
    }
