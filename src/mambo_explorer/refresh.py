"""Bounded local refresh: plan and run the EXISTING collectors one source at a time (ADR 0013).

There is no second ingestion path. A refresh builds an EIA `collect.Plan` or an ERCOT
`Selection` from the refresh configuration and the store's own committed-run history, then
calls `collect.collect` / `ercot.collect.collect`, which keep their writer locks, atomic
writes, revision numbering, and recovery behavior.

Rules:
- One refresh at a time (a refresh lock beside the stores). Sources run sequentially.
- Each source has its own request budget; a source that fails is recorded and the next
  one still runs. A failure never touches another source's committed runs.
- Catch-up is planned from committed runs (what was successfully collected), never from
  the absence of rows: an absent row is not proof of a missed job, and nothing is filled.
- Diagnostics are redacted before they are printed or written.
- Nothing here runs from the Streamlit app.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from mambo_explorer import collect as eia_collect
from mambo_explorer import generation
from mambo_explorer.eia.redact import redact
from mambo_explorer.ercot import collect as ercot_collect
from mambo_explorer.ercot import dataset as ercot_ds
from mambo_explorer.ercot import prices as ercot_prices
from mambo_explorer.ercot import rt_prices as ercot_rt
from mambo_explorer.refresh_config import RefreshConfig
from mambo_explorer.storage import Store, atomic_write

REFRESH_DIR = "refresh"
LOCK_NAME = ".refresh.lock"
LOG_PREFIX = "refresh-"

# Gap classifications (shown by `mambo refresh --dry-run` and System Health).
NEVER_COLLECTED = "never-collected"
MISSED_COLLECTION = "missed-collection"  # no successful run within 2 collection intervals
MISSING_OBSERVATIONS = "missing-observations"  # absent rows inside collected ranges
SOURCE_UNAVAILABLE = "source-unavailable"  # the last attempt failed at the source
OUTSIDE_HISTORY = "outside-available-history"  # older than the source's public retention
BEYOND_CATCHUP = "beyond-catch-up-limit"  # newer than history limits but over this run's cap
REVISION_LOOKBACK = "revision-lookback"  # already-collected data requested again on purpose
UP_TO_DATE = "no-new-period-expected"

EXIT_COMPLETE, EXIT_FAILED, EXIT_PARTIAL = 0, 2, 3


class RefreshLockError(RuntimeError):
    pass


@dataclass(frozen=True)
class Finding:
    kind: str
    detail: str


@dataclass
class SourcePlan:
    source: str
    action: str  # "collect" or "skip"
    reason: str
    request_budget: int
    findings: list[Finding] = field(default_factory=list)
    eia_plan: eia_collect.Plan | None = None
    ercot_selection: ercot_collect.Selection | None = None
    generation_plan: generation.GenerationPlan | None = None
    price_selection: ercot_prices.Selection | None = None
    rt_selection: ercot_rt.Selection | None = None

    def describe(self) -> dict:
        out = {
            "source": self.source,
            "action": self.action,
            "reason": self.reason,
            "request_budget": self.request_budget,
            "findings": [asdict(f) for f in self.findings],
        }
        if self.eia_plan:
            out["collector_plan"] = self.eia_plan.describe()
        if self.ercot_selection:
            out["collector_plan"] = self.ercot_selection.describe()
        if self.generation_plan:
            out["collector_plan"] = self.generation_plan.describe()
        if self.price_selection:
            out["collector_plan"] = self.price_selection.describe()
        if self.rt_selection:
            out["collector_plan"] = self.rt_selection.describe()
        return out


@dataclass
class SourceResult:
    source: str
    status: str  # succeeded | failed | skipped | planned (dry run)
    request_budget: int
    requests: int | None = None
    summary: dict | None = None
    error: str | None = None


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    stamp = datetime.fromisoformat(text)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def run_history(store: Store) -> dict:
    """Last attempted and last successful run, from the catalog only (read-only)."""
    runs = store.runs(limit=10_000)
    committed = [r for r in runs if r["status"] == "committed"]
    return {
        "last_attempt": runs[0] if runs else None,
        "last_success": max(committed, key=lambda r: r["finished_at"]) if committed else None,
        "committed": committed,
    }


def _common_findings(history: dict, interval_hours: int, now: datetime) -> list[Finding]:
    findings = []
    last, success = history["last_attempt"], history["last_success"]
    if last and last["status"] == "failed":
        findings.append(
            Finding(
                SOURCE_UNAVAILABLE,
                f"the last attempt ({last['started_at']}) failed: "
                f"{last.get('error') or 'no detail'}",
            )
        )
    if last and last["status"] in ("started", "abandoned"):
        findings.append(
            Finding(
                SOURCE_UNAVAILABLE,
                f"the last attempt ({last['started_at']}) is '{last['status']}' (interrupted); "
                "run `mambo validate` for that source",
            )
        )
    if success:
        finished = _parse_time(success["finished_at"])
        if finished and now - finished > timedelta(hours=2 * interval_hours):
            findings.append(
                Finding(
                    MISSED_COLLECTION,
                    f"no successful collection since {success['finished_at']}, more than two "
                    f"collection intervals ({interval_hours} h each)",
                )
            )
    return findings


def plan_eia(config: RefreshConfig, store: Store, now: datetime, source: str = "eia") -> SourcePlan:
    """Demand/forecast ("eia") or generation ("eia-generation"): the same UTC-day rules, each
    from its own store's committed runs, so one dataset's success says nothing about the
    other's."""
    s = config.source(source)
    label = "EIA generation" if source == "eia-generation" else "EIA"
    if not s.enabled:
        return SourcePlan(source, "skip", "disabled in the refresh configuration", 0)
    today = now.astimezone(UTC).date()  # EIA periods are UTC labels; completed UTC days only
    history = run_history(store)
    findings = _common_findings(history, s.collection_interval_hours, now)
    if not history["committed"]:
        start, lookback = today - timedelta(days=s.window_days), 0
        findings.append(
            Finding(
                NEVER_COLLECTED,
                f"no successful {label} collection; requesting {s.window_days} days",
            )
        )
    else:
        covered = max(date.fromisoformat(r["request_end"][:10]) for r in history["committed"])
        first_new = covered + timedelta(days=1)
        new_days = (today - first_new).days
        lookback = s.revision_lookback_days
        if new_days <= 0:
            start = today - timedelta(days=1)
            findings.append(
                Finding(UP_TO_DATE, f"committed runs already cover UTC days through {covered}")
            )
        elif new_days <= s.max_catchup_days:
            start = first_new
        else:
            start = today - timedelta(days=s.max_catchup_days)
            last_skipped = start - timedelta(days=lookback + 1)  # the lookback also fetches
            if last_skipped >= first_new:
                findings.append(
                    Finding(
                        BEYOND_CATCHUP,
                        f"UTC days {first_new} .. {last_skipped} are not requested by "
                        f"this refresh (cap {s.max_catchup_days} days). They may still be "
                        "available from EIA; request them with `mambo collect --start/--end` in "
                        f"pieces of at most {eia_collect.MAX_DAYS_PER_RUN} days.",
                    )
                )
        if lookback:
            findings.append(
                Finding(
                    REVISION_LOOKBACK,
                    f"{lookback} earlier UTC day(s) are requested again to detect revisions",
                )
            )
    findings.append(
        Finding(
            MISSING_OBSERVATIONS,
            "absent hours are reported by System Health, never filled; an absent hour is "
            "requested again only if it falls inside this refresh's window",
        )
    )
    kwargs = dict(
        start=start, end=today, lookback_days=lookback, max_requests=s.request_budget, today=today
    )
    try:
        if source == "eia-generation":
            plan = generation.plan_generation(**kwargs)
            return SourcePlan(
                source,
                "collect",
                "bounded EIA generation collection",
                s.request_budget,
                findings,
                generation_plan=plan,
            )
        plan = eia_collect.plan_collection(**kwargs)
    except eia_collect.PlanError as exc:
        return SourcePlan(source, "skip", f"plan rejected: {exc}", s.request_budget, findings)
    return SourcePlan(
        "eia", "collect", "bounded EIA collection", s.request_budget, findings, eia_plan=plan
    )


def latest_oper_date(store: Store) -> date | None:
    if not store.committed_files("observations"):
        return None
    with store.query() as con:
        return con.execute("SELECT max(oper_date) FROM latest").fetchone()[0]


def latest_delivery_date(store: Store) -> date | None:
    if not store.committed_files("observations"):
        return None
    with store.query() as con:
        return con.execute("SELECT max(delivery_date) FROM latest").fetchone()[0]


def plan_ercot(
    config: RefreshConfig,
    store: Store,
    now: datetime,
    local_today: date,
    source: str = "ercot",
) -> SourcePlan:
    """ERCOT labels are compared by calendar date only; nothing is converted to UTC.

    "ercot" (NP6-345-CD load: one document per OperDay, posted the next morning) or
    "ercot-dam-spp" (NP4-190-CD DAM prices: one document per DAM run, posted the day BEFORE
    the Operating Day, so the newest DeliveryDate one can expect today is tomorrow).
    """
    s = config.source(source)
    prices = source == "ercot-dam-spp"
    retention = ercot_prices.PUBLIC_RETENTION_DAYS if prices else ercot_ds.PUBLIC_RETENTION_DAYS
    label = "DeliveryDate" if prices else "OperDay"
    if not s.enabled:
        return SourcePlan(source, "skip", "disabled in the refresh configuration", 0)
    history = run_history(store)
    findings = _common_findings(history, s.collection_interval_hours, now)
    if prices:
        last_day = latest_delivery_date(store) if history["committed"] else None
    else:
        last_day = latest_oper_date(store) if history["committed"] else None
    if last_day is None:
        documents = s.window_documents
        findings.append(
            Finding(
                NEVER_COLLECTED,
                f"no stored ERCOT {label}; requesting the latest {documents} public documents",
            )
        )
    else:
        # The document for an OperDay is posted the next morning, so the newest OperDay one
        # can expect today is yesterday (by calendar label; approximate, no conversion).
        newest_expected = local_today + timedelta(days=1) if prices else local_today
        new_days = max(0, (newest_expected - last_day).days - (0 if prices else 1))
        lookback = s.revision_lookback_documents
        if new_days > retention:
            lost = new_days - retention
            findings.append(
                Finding(
                    OUTSIDE_HISTORY,
                    f"about {lost} {label}(s) after {last_day} are older than ERCOT's public list "
                    f"(about {retention} days) and are not available "
                    "through the public report listing this app uses",
                )
            )
            new_days = retention
        if new_days + lookback > s.max_catchup_documents:
            documents = s.max_catchup_documents
            skipped = new_days + lookback - documents
            findings.append(
                Finding(
                    BEYOND_CATCHUP,
                    f"about {skipped} older document(s) are not requested (cap "
                    f"{s.max_catchup_documents}). While they remain in the public list, fetch "
                    f"them with `mambo collect --source {source} --publish-date YYYY-MM-DD`.",
                )
            )
        else:
            documents = new_days + lookback
        if lookback:
            findings.append(
                Finding(
                    REVISION_LOOKBACK,
                    f"{lookback} already-stored document(s) are downloaded again to detect reposts",
                )
            )
        if documents == 0:
            findings.append(
                Finding(UP_TO_DATE, f"latest stored {label} {last_day}; nothing newer expected yet")
            )
            return SourcePlan(
                source, "skip", "no new document expected", s.request_budget, findings
            )
    findings.append(
        Finding(
            MISSING_OBSERVATIONS,
            f"absent {label}s or hours are reported by System Health, never filled",
        )
    )
    if prices:
        findings.append(Finding("finality-not-determined", ercot_prices.FINALITY_TEXT))
    if s.request_budget < 1 + documents:
        return SourcePlan(
            source, "skip", "request budget below 1 list + downloads", s.request_budget, findings
        )
    if prices:
        return SourcePlan(
            source,
            "collect",
            "bounded ERCOT DAM price collection (HB_NORTH)",
            s.request_budget,
            findings,
            price_selection=ercot_prices.Selection(latest=documents),
        )
    selection = ercot_collect.Selection(latest=documents)
    return SourcePlan(
        "ercot",
        "collect",
        "bounded ERCOT collection",
        s.request_budget,
        findings,
        ercot_selection=selection,
    )


def plan_ercot_rt(config: RefreshConfig, store: Store, now: datetime) -> SourcePlan:
    """Real-time intervals: planned from the public list at collection time, not from a clock.

    ERCOT's interval labels carry no time zone, so the plan cannot say which intervals "should"
    exist by now. The collector lists the published documents and takes the newest ones not yet
    stored (capped); it reports documents published but not requested (catch-up limit), the
    oldest listed document (available history), and "no newer document published yet".
    """
    s = config.rt_prices
    source = "ercot-rt-spp"
    if not s.enabled:
        return SourcePlan(source, "skip", "disabled in the refresh configuration", 0)
    history = run_history(store)
    findings = _common_findings(history, s.collection_interval_hours, now)
    if not history["committed"]:
        documents = s.window_documents
        findings.append(
            Finding(
                NEVER_COLLECTED,
                f"no stored real-time interval; requesting the newest {documents} published "
                "documents",
            )
        )
    else:
        documents = s.max_catchup_documents
        findings.append(
            Finding(
                BEYOND_CATCHUP,
                f"up to {documents} newest unstored intervals are requested; the collector "
                "reports any older published ones it leaves (catch-up limit) and whether "
                "nothing newer is published yet",
            )
        )
    findings.append(
        Finding(
            OUTSIDE_HISTORY,
            f"ERCOT's public list keeps about {ercot_rt.PUBLIC_RETENTION_DAYS} days; older "
            "intervals are not available through the access method this app implements",
        )
    )
    findings.append(Finding(MISSING_OBSERVATIONS, "absent intervals are reported, never filled"))
    findings.append(Finding("finality-not-determined", ercot_rt.FINALITY_TEXT))
    if s.request_budget < 1 + documents:
        return SourcePlan(
            source, "skip", "request budget below 1 list + downloads", s.request_budget, findings
        )
    return SourcePlan(
        source,
        "collect",
        "bounded ERCOT real-time price collection (HB_NORTH)",
        s.request_budget,
        findings,
        rt_selection=ercot_rt.Selection(latest=documents),
    )


def plan_refresh(
    config: RefreshConfig,
    sources: list[str],
    stores: dict[str, Store],
    now: datetime,
    local_today: date,
) -> list[SourcePlan]:
    plans = []
    for source in sources:
        if source in ("eia", "eia-generation"):
            plans.append(plan_eia(config, stores[source], now, source))
        elif source == "ercot-rt-spp":
            plans.append(plan_ercot_rt(config, stores[source], now))
        else:
            plans.append(plan_ercot(config, stores[source], now, local_today, source))
    return apply_host_budgets(config, plans)


def apply_host_budgets(config: RefreshConfig, plans: list[SourcePlan]) -> list[SourcePlan]:
    """Skip any later dataset whose budget would push its host past the shared cap."""
    from mambo_explorer.refresh_config import HOSTS

    used: dict[str, int] = {}
    for plan in plans:
        if plan.action != "collect":
            continue
        host = HOSTS[plan.source]
        cap = config.host_budget(host)
        if cap is not None and used.get(host, 0) + plan.request_budget > cap:
            plan.action = "skip"
            plan.reason = (
                f"shared {host} budget: {used.get(host, 0)} of {cap} requests already "
                f"budgeted by earlier datasets in this refresh; this one needs "
                f"{plan.request_budget}"
            )
            plan.findings.append(Finding("host-budget", plan.reason))
            continue
        used[host] = used.get(host, 0) + plan.request_budget
    return plans


def host_budget_summary(config: RefreshConfig, plans: list[SourcePlan]) -> dict:
    from mambo_explorer.refresh_config import HOSTS

    out: dict[str, dict] = {}
    for plan in plans:
        if plan.action == "collect":
            host = HOSTS[plan.source]
            entry = out.setdefault(host, {"budgeted": 0, "cap": config.host_budget(host)})
            entry["budgeted"] += plan.request_budget
    return out


@contextmanager
def refresh_lock(data_dir: Path, now: datetime):
    """Single-run coordination. A stale lock is reported, never removed automatically."""
    folder = Path(data_dir) / REFRESH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / LOCK_NAME
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder = path.read_text("utf-8", "replace").strip()
        raise RefreshLockError(
            f"another refresh is running ({holder}). If none is, the lock is stale: check, "
            f"then delete {path}"
        ) from None
    with os.fdopen(fd, "w") as handle:
        handle.write(f"pid={os.getpid()} since={now.isoformat()}")
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def _eia_budget(items: list[tuple[str, int]]) -> int:
    """Combined requests the EIA API may receive (demand plus generation datasets)."""
    return sum(budget for source, budget in items if source in ("eia", "eia-generation"))


def overall_status(results: list[SourceResult]) -> str:
    ran = [r for r in results if r.status in ("succeeded", "failed")]
    if not ran:
        return "nothing-to-do"
    ok = sum(r.status == "succeeded" for r in ran)
    if ok == len(ran):
        return "complete"
    return "partial" if ok else "failed"


def exit_code(status: str) -> int:
    return {"partial": EXIT_PARTIAL, "failed": EXIT_FAILED}.get(status, EXIT_COMPLETE)


def execute(
    plans: list[SourcePlan],
    *,
    stores: dict[str, Store],
    clients: dict[str, Callable[[int], object]],
    secrets: list[str | None],
) -> list[SourceResult]:
    """Run planned sources one after another. The caller holds the refresh lock."""
    results = []
    for plan in plans:
        if plan.action != "collect":
            results.append(
                SourceResult(plan.source, "skipped", plan.request_budget, error=plan.reason)
            )
            continue
        client = None
        try:
            client = clients[plan.source](plan.request_budget)
            if plan.source == "eia":
                summary = eia_collect.collect(plan.eia_plan, client, stores["eia"])
            elif plan.source == "eia-generation":
                summary = generation.collect(plan.generation_plan, client, stores[plan.source])
            elif plan.source == "ercot-dam-spp":
                summary = ercot_prices.collect(plan.price_selection, client, stores[plan.source])
            elif plan.source == "ercot-rt-spp":
                summary = ercot_rt.collect(plan.rt_selection, client, stores[plan.source])
            else:
                summary = ercot_collect.collect(plan.ercot_selection, client, stores["ercot"])
            results.append(
                SourceResult(
                    plan.source, "succeeded", plan.request_budget, summary["requests"], summary
                )
            )
        except Exception as exc:  # noqa: BLE001 - one source's failure must not stop the next
            used = getattr(getattr(client, "stats", None), "requests", None)
            message = redact(f"{type(exc).__name__}: {exc}", secrets)
            results.append(
                SourceResult(plan.source, "failed", plan.request_budget, used, error=message)
            )
    return results


def write_log(
    data_dir: Path, config: RefreshConfig, record: dict, now: datetime, secrets: list[str | None]
) -> Path:
    folder = Path(data_dir) / REFRESH_DIR / "logs"
    name = f"{LOG_PREFIX}{now.astimezone(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}.json"
    text = redact(json.dumps(record, indent=2, default=str), secrets)
    atomic_write(folder / name, text.encode("utf-8"))
    prune_logs(folder, config, now)
    return folder / name


def prune_logs(folder: Path, config: RefreshConfig, now: datetime) -> list[str]:
    """Delete only this application's refresh logs, by age and count."""
    logs = sorted(folder.glob(f"{LOG_PREFIX}*.json"), key=lambda p: p.name, reverse=True)
    removed = []
    cutoff = now - timedelta(days=config.log_retention_days)
    for index, path in enumerate(logs):
        stamp = datetime.strptime(
            path.name[len(LOG_PREFIX) : len(LOG_PREFIX) + 16], "%Y%m%dT%H%M%SZ"
        )
        if index >= config.log_max_files or stamp.replace(tzinfo=UTC) < cutoff:
            path.unlink(missing_ok=True)
            removed.append(path.name)
    return removed


def read_logs(data_dir: Path, limit: int = 5) -> list[dict]:
    folder = Path(data_dir) / REFRESH_DIR / "logs"
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob(f"{LOG_PREFIX}*.json"), key=lambda p: p.name, reverse=True)[
        :limit
    ]:
        try:
            out.append(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError):
            out.append({"file": path.name, "overall": "unreadable log"})
    return out


def refresh(
    config: RefreshConfig,
    sources: list[str],
    *,
    data_dir: Path,
    stores: dict[str, Store],
    clients: dict[str, Callable[[int], object]],
    now: Callable[[], datetime],
    local_today: date,
    dry_run: bool,
    secrets: list[str | None],
) -> dict:
    """Plan, then (unless dry run) collect under the refresh lock and write a redacted log."""
    started = now()
    plans = plan_refresh(config, sources, stores, started, local_today)
    record = {
        "started_at_utc": started.astimezone(UTC).isoformat(),
        "config": config.origin,
        "dry_run": dry_run,
        "sources": sources,
        "plans": [p.describe() for p in plans],
    }
    if dry_run:
        record["results"] = [
            asdict(
                SourceResult(
                    p.source,
                    "planned" if p.action == "collect" else "skipped",
                    p.request_budget,
                    error=None if p.action == "collect" else p.reason,
                )
            )
            for p in plans
        ]
        record["overall"] = "dry-run"
        record["requests_budgeted"] = sum(p.request_budget for p in plans if p.action == "collect")
        record["eia_api_requests_budgeted"] = _eia_budget(
            [(p.source, p.request_budget) for p in plans if p.action == "collect"]
        )
        record["host_requests_budgeted"] = host_budget_summary(config, plans)
        return json.loads(redact(json.dumps(record, default=str), secrets))
    with refresh_lock(data_dir, started):
        results = execute(plans, stores=stores, clients=clients, secrets=secrets)
        record["results"] = [asdict(r) for r in results]
        record["overall"] = overall_status(results)
        record["requests_used"] = sum(r.requests or 0 for r in results)
        record["requests_budgeted"] = sum(
            r.request_budget for r in results if r.status in ("succeeded", "failed")
        )
        record["eia_api_requests_budgeted"] = _eia_budget(
            [(r.source, r.request_budget) for r in results if r.status in ("succeeded", "failed")]
        )
        record["host_requests_budgeted"] = host_budget_summary(config, plans)
        record["finished_at_utc"] = now().astimezone(UTC).isoformat()
        record["log"] = str(write_log(data_dir, config, record, started, secrets).name)
    return json.loads(redact(json.dumps(record, default=str), secrets))
