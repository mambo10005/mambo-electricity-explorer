"""Command line: `mambo <command> [--source eia|ercot]`.

Commands:
    sources    reviewed dataset contract; --remote checks the live source
               (EIA: route/entity/metrics with the key; ERCOT: lists available public documents)
    collect    bounded collection (--dry-run shows scope and request budget, sends nothing)
    validate   check stored files against the catalog; report orphans/interrupted runs
    status     recent collection runs
    storage    storage diagnostics
    refresh    bounded refresh of the enabled sources, one after another (--dry-run shows the
               plan and budgets; --source eia/ercot selects; --config uses another plan)
    health     read-only collection, freshness, and storage status
    learn-reset  optional backup-and-reset of local learning progress (dry run unless
               --execute; asks for typed confirmation; never shows contents)
    assumption show|status|approve|revoke  the versioned M1 alignment assumption and its
               local approval records (approve/revoke are dry runs unless --execute; every
               reviewer field must be supplied, nothing is filled in)

--source defaults to eia. ERCOT (NP6-345-CD) uses ERCOT's public download, needs no
credential, and never uses EIA_API_KEY. Nothing is deleted by default.
Exit codes: 0 ok, 1 check failed, 2 configuration or source error (refresh: every source
failed, or another refresh is running), 3 refresh partially succeeded.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from mambo_explorer import generation
from mambo_explorer.collect import (
    DEFAULT_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    MAX_DAYS_PER_RUN,
    PlanError,
    collect,
    plan_collection,
)
from mambo_explorer.config import ConfigError, find_repo_root, load_dotenv, load_settings
from mambo_explorer.eia import dataset as ds
from mambo_explorer.eia.client import EIAClient, EIAError
from mambo_explorer.ercot import collect as ercot
from mambo_explorer.ercot import dataset as ercot_ds
from mambo_explorer.ercot import prices as ercot_prices
from mambo_explorer.ercot import rt_prices as ercot_rt
from mambo_explorer.ercot.client import ErcotClient, ErcotError
from mambo_explorer.refresh import RefreshLockError
from mambo_explorer.refresh_config import RefreshConfigError
from mambo_explorer.safe_zip import ArchiveError
from mambo_explorer.storage import Store, WriterLockError

SOURCES = ("eia", "ercot", "eia-generation", "ercot-dam-spp", "ercot-rt-spp")


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _store(args, settings) -> Store:
    if args.source == "ercot":
        return ercot.store(settings.data_dir)
    if args.source == "eia-generation":
        return generation.store(settings.data_dir)
    if args.source == "ercot-dam-spp":
        return ercot_prices.store(settings.data_dir)
    if args.source == "ercot-rt-spp":
        return ercot_rt.store(settings.data_dir)
    return Store(settings.data_dir)


def cmd_sources(args, settings) -> int:
    if args.source == "ercot":
        _print(
            {
                "source": f"ERCOT {ercot_ds.DATASET} — {ercot_ds.REPORT_NAME}",
                "report_type_id": ercot_ds.REPORT_TYPE_ID,
                "product_page": ercot_ds.PRODUCT_PAGE,
                "columns": list(ercot_ds.HEADER),
                "units": ercot_ds.UNIT_TEXT,
                "time_labels": ercot_ds.TIME_TEXT,
                "public_retention_days": ercot_ds.PUBLIC_RETENTION_DAYS,
                "review": "docs/source-register.md — ERCOT NP6-345-CD review",
            }
        )
        if not args.remote:
            print("\n(offline summary; add --remote to list documents ERCOT currently publishes)")
            return 0
        client = ErcotClient(max_requests=1)
        documents = client.list_documents()
        _print(
            {
                "public_csv_documents": len(documents),
                "publish_times": [d.publish_time_raw for d in documents],
                "requests_used": client.stats.requests,
            }
        )
        return 0
    if args.source == "ercot-rt-spp":
        _print(
            {
                "source": f"ERCOT {ercot_rt.DATASET} — {ercot_rt.REPORT_NAME}",
                "report_type_id": ercot_rt.REPORT_TYPE_ID,
                "product_page": ercot_rt.PRODUCT_PAGE,
                "market_stage": ercot_rt.MARKET_STAGE,
                "location": f"{ercot_rt.LOCATION} — {ercot_rt.LOCATION_NAME}",
                "price": ercot_rt.PRICE_DEFINITION,
                "interval_minutes": ercot_rt.INTERVAL_MINUTES,
                "columns": list(ercot_rt.HEADER),
                "units": ercot_rt.UNIT_TEXT,
                "time_labels": ercot_rt.TIME_TEXT,
                "finality": ercot_rt.FINALITY_TEXT,
                "review": "docs/source-register.md — ERCOT NP6-905-CD review",
            }
        )
        return 0
    if args.source == "ercot-dam-spp":
        _print(
            {
                "source": f"ERCOT {ercot_prices.DATASET} — {ercot_prices.REPORT_NAME}",
                "report_type_id": ercot_prices.REPORT_TYPE_ID,
                "product_page": ercot_prices.PRODUCT_PAGE,
                "market_stage": ercot_prices.MARKET_STAGE,
                "location": f"{ercot_prices.LOCATION} — {ercot_prices.LOCATION_NAME}",
                "columns": list(ercot_prices.HEADER),
                "units": ercot_prices.UNIT_TEXT,
                "time_labels": ercot_prices.TIME_TEXT,
                "finality": ercot_prices.FINALITY_TEXT,
                "review": "docs/source-register.md — ERCOT NP4-190-CD review",
            }
        )
        return 0
    if args.source == "eia-generation":
        _print(ds.generation_review_summary())
        if not args.remote:
            print("\n(offline summary; add --remote to verify route, facet, and codes with EIA)")
            return 0
        client = EIAClient(settings.api_key, max_requests=5)
        _print(ds.verify_generation_metadata(client))
        return 0
    _print(ds.review_summary())
    if not args.remote:
        print("\n(offline summary; add --remote to verify route, entity, and metrics with EIA)")
        return 0
    client = EIAClient(settings.api_key, max_requests=5)
    _print(ds.verify_metadata(client))
    return 0


def _collect_rt(args, settings) -> int:
    """Real-time prices: snapshot (--latest) or bounded coverage/backfill (--coverage-from)."""
    from mambo_explorer import refresh_config

    if args.publish_date:
        raise ercot_rt.SelectionError(
            "--publish-date is not supported for ercot-rt-spp; use --coverage-from/--coverage-to"
        )
    coverage = args.coverage_from is not None
    if args.coverage_to is not None and not coverage:
        raise ercot_rt.SelectionError("--coverage-to needs --coverage-from")
    selection = ercot_rt.Selection(
        latest=args.latest
        or (
            ercot_rt.MAX_DOCUMENTS_PER_RUN - (args.recheck or 0)
            if coverage
            else ercot_rt.DEFAULT_LATEST
        ),
        include_stored=args.include_stored,
        mode=ercot_rt.COVERAGE if coverage else ercot_rt.SNAPSHOT,
        publish_from=args.coverage_from,
        publish_to=args.coverage_to,
        recheck=args.recheck or 0,
    )
    cap = refresh_config.load().host_budget("ercot.com")
    if cap is not None and selection.request_budget > cap:
        raise ercot_rt.SelectionError(
            f"this run would budget {selection.request_budget} requests, above the shared "
            f"ercot.com cap of {cap}; request fewer documents or rechecks"
        )
    target = ercot_rt.store(settings.data_dir)
    print("Collection plan:")
    _print({**selection.describe(), "preview": ercot_rt.preview(selection, target)})
    if args.dry_run:
        print("\nDry run: no requests sent, nothing written.")
        return 0
    summary = ercot_rt.collect(
        selection, ErcotClient(max_requests=selection.request_budget), target
    )
    print("\nCollection committed:")
    _print(summary)
    if summary["documents_failed"] or summary["stopped_early"]:
        print("\nPartial: some documents failed or were deferred; run again to resume.")
        return 3
    return 0


def cmd_collect(args, settings) -> int:
    if args.source == "ercot-rt-spp":
        return _collect_rt(args, settings)
    if args.source == "ercot-dam-spp":
        selection = ercot_prices.Selection(
            latest=None if args.publish_date else (args.latest or ercot_prices.DEFAULT_LATEST),
            publish_dates=tuple(args.publish_date or ()),
        )
        print("Collection plan:")
        _print(selection.describe())
        if args.dry_run:
            print("\nDry run: no requests sent, nothing written.")
            return 0
        summary = ercot_prices.collect(
            selection, ErcotClient(), ercot_prices.store(settings.data_dir)
        )
        print("\nCollection committed:")
        _print(summary)
        return 0
    if args.source == "ercot":
        selection = ercot.Selection(
            latest=None if args.publish_date else (args.latest or ercot.DEFAULT_LATEST),
            publish_dates=tuple(args.publish_date or ()),
        )
        print("Collection plan:")
        _print(selection.describe())
        if args.dry_run:
            print("\nDry run: no requests sent, nothing written.")
            return 0
        summary = ercot.collect(selection, ErcotClient(), ercot.store(settings.data_dir))
        print("\nCollection committed:")
        _print(summary)
        return 0
    planner = generation.plan_generation if args.source == "eia-generation" else plan_collection
    plan = planner(
        days=args.days,
        start=args.start,
        end=args.end,
        lookback_days=args.lookback_days,
        page_size=args.page_size,
        max_requests=args.max_requests,
    )
    print("Collection plan:")
    _print(plan.describe())
    if args.dry_run:
        print("\nDry run: no requests sent, nothing written.")
        return 0
    client = EIAClient(settings.api_key, max_requests=plan.max_requests)
    if args.source == "eia-generation":
        summary = generation.collect(plan, client, generation.store(settings.data_dir))
    else:
        summary = collect(plan, client, Store(settings.data_dir))
    print("\nCollection committed:")
    _print(summary)
    return 0


def cmd_validate(args, settings) -> int:
    report = _store(args, settings).validate(
        mark_interrupted=args.mark_interrupted, quarantine_orphans=args.quarantine_orphans
    )
    _print(report)
    return 0 if report["ok"] else 1


def cmd_status(args, settings) -> int:
    target = _store(args, settings)
    runs = target.runs(limit=args.limit)
    if not runs:
        print(f"No collection runs in {target.root}.")
    _print(runs)
    return 0


def cmd_storage(args, settings) -> int:
    _print(_store(args, settings).diagnostics())
    return 0


def cmd_learn_reset(args, settings) -> int:
    from mambo_explorer import progress_reset as pr

    try:
        p = pr.plan(settings.data_dir, Path(args.backup_dir) if args.backup_dir else None)
        if not args.execute:
            for line in pr.describe(p):
                print(line)
            if p.exists:
                print("Dry run: nothing was changed. Re-run with --execute to back up and reset.")
            return 0
        for line in pr.execute(p, input):
            print(line)
        return 0
    except pr.ResetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _refresh_parts(settings, config_path):
    from mambo_explorer import refresh_config

    config = refresh_config.load(Path(config_path) if config_path else None)
    stores = {
        "eia": Store(settings.data_dir),
        "ercot": ercot.store(settings.data_dir),
        "eia-generation": generation.store(settings.data_dir),
        "ercot-dam-spp": ercot_prices.store(settings.data_dir),
        "ercot-rt-spp": ercot_rt.store(settings.data_dir),
    }
    return config, stores


def cmd_refresh(args, settings) -> int:
    from datetime import UTC, datetime

    from mambo_explorer import refresh

    config, stores = _refresh_parts(settings, args.config)
    sources = list(dict.fromkeys(args.source)) if args.source else config.enabled()
    clients = {
        "eia": lambda budget: EIAClient(settings.api_key, max_requests=budget),
        "eia-generation": lambda budget: EIAClient(settings.api_key, max_requests=budget),
        "ercot": lambda budget: ErcotClient(max_requests=budget),
        "ercot-dam-spp": lambda budget: ErcotClient(max_requests=budget),
        "ercot-rt-spp": lambda budget: ErcotClient(max_requests=budget),
    }
    record = refresh.refresh(
        config,
        sources,
        data_dir=settings.data_dir,
        stores=stores,
        clients=clients,
        now=lambda: datetime.now(UTC),
        local_today=date.today(),
        dry_run=args.dry_run,
        secrets=[settings.api_key],
    )
    _print(record)
    if args.dry_run:
        print("\nDry run: no requests sent, nothing written.")
        return 0
    print(f"\nRefresh {record['overall']}.")
    return refresh.exit_code(record["overall"])


def cmd_health(args, settings) -> int:
    from dataclasses import asdict
    from datetime import UTC, datetime

    from mambo_explorer import health, refresh

    config, stores = _refresh_parts(settings, args.config)
    logs = refresh.read_logs(settings.data_dir)
    _print([asdict(h) for h in health.source_health(stores, config, datetime.now(UTC), logs)])
    return 0


def cmd_assumption(args, settings) -> int:
    from dataclasses import asdict

    from mambo_explorer.ercot import approvals as ap
    from mambo_explorer.ercot.m1_policy import current

    record = current(args.assumption_id)
    if args.action == "show":
        _print(
            {
                **{k: v for k, v in asdict(record).items() if k != "schema"},
                "schema_fingerprint": record.schema_fingerprint(),
                "scope_fingerprint": record.scope_fingerprint(),
            }
        )
        return 0
    try:
        if args.action == "status":
            state = ap.status(settings.data_dir, record)
            _print(
                {
                    "assumption": f"{record.id} {record.version}",
                    "approval_status": state.status,
                    "approval_reference": state.reference,
                    "detail": state.detail,
                    "superseded_records": ap.superseded_records(settings.data_dir, record),
                    "official_semantics": record.official_status,
                    "records_file": str(ap.path(settings.data_dir)),
                }
            )
            return 0
        if args.action == "approve":
            event = ap.new_approval(
                record,
                reviewer=args.reviewer,
                role=args.role,
                evidence=args.evidence,
                approved_on=args.approved_on,
            )
        else:
            if not args.record or not args.reason:
                raise ap.ApprovalError("revoke needs --record and --reason")
            event = ap.new_revocation(record, args.record, args.reason)
        _print(asdict(event))
        if not args.execute:
            print("Dry run: nothing was recorded. Re-run with --execute to append this record.")
            return 0
        print(f"Appended to {ap.append(settings.data_dir, event)}")
        return 0
    except ap.ApprovalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _date(text: str) -> date:
    return date.fromisoformat(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mambo", description=__doc__.split("\n")[0])
    parser.add_argument("--no-dotenv", action="store_true", help="do not load ./.env")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str, func):
        p = sub.add_parser(name, help=help_text)
        p.add_argument(
            "--source",
            choices=SOURCES,
            default="eia",
            help="eia (EIA-930 demand/forecast), ercot (ERCOT NP6-345-CD direct), or "
            "eia-generation (EIA-930 net generation by energy source), or ercot-dam-spp "
            "(ERCOT NP4-190-CD DAM settlement point price, HB_NORTH), or ercot-rt-spp "
            "(ERCOT NP6-905-CD real-time settlement point price, HB_NORTH)",
        )
        p.set_defaults(func=func)
        return p

    p = add("sources", "show the reviewed dataset contract", cmd_sources)
    p.add_argument("--remote", action="store_true", help="check the live source")

    p = add("collect", "bounded collection", cmd_collect)
    p.add_argument("--dry-run", action="store_true", help="show scope and budget only")
    eia = p.add_argument_group("EIA options")
    eia.add_argument("--days", type=int, default=DEFAULT_DAYS, help="completed UTC days to fetch")
    eia.add_argument("--start", type=_date, help="first UTC day (YYYY-MM-DD)")
    eia.add_argument("--end", type=_date, help="UTC day after the last day (exclusive)")
    eia.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="extra earlier days re-fetched to detect revisions",
    )
    eia.add_argument("--page-size", type=int, default=ds.MAX_ROWS_PER_REQUEST)
    eia.add_argument("--max-requests", type=int, help="request budget including retries")
    ercot_group = p.add_argument_group("ERCOT options")
    ercot_group.add_argument(
        "--latest",
        type=int,
        help=f"latest N public documents (1..{ercot.MAX_DOCUMENTS_PER_RUN}; "
        f"default {ercot.DEFAULT_LATEST})",
    )
    ercot_group.add_argument(
        "--publish-date",
        action="append",
        help="ERCOT PublishDate (YYYY-MM-DD) to fetch; repeatable",
    )
    ercot_group.add_argument(
        "--include-stored",
        action="store_true",
        help="ercot-rt-spp: re-download already-stored intervals (revision check)",
    )
    ercot_group.add_argument(
        "--coverage-from",
        type=_date,
        help="ercot-rt-spp coverage/backfill mode: first PublishDate label (YYYY-MM-DD, as "
        "ERCOT writes it); takes the OLDEST uncollected listed documents first",
    )
    ercot_group.add_argument(
        "--coverage-to",
        type=_date,
        help="ercot-rt-spp coverage mode: last PublishDate label (default: newest listed)",
    )
    ercot_group.add_argument(
        "--recheck",
        type=int,
        help=f"ercot-rt-spp: already-collected documents to download again for reposts "
        f"(0..{ercot_rt.MAX_RECHECK_PER_RUN}; default 0)",
    )
    p.epilog = (
        f"EIA: at most {MAX_DAYS_PER_RUN} days per run including lookback. "
        f"ERCOT: at most {ercot.MAX_DOCUMENTS_PER_RUN} documents per run."
    )

    p = add("validate", "verify stored files and catalog", cmd_validate)
    p.add_argument("--mark-interrupted", action="store_true", help="mark stale runs abandoned")
    p.add_argument(
        "--quarantine-orphans", action="store_true", help="move unregistered files to quarantine/"
    )

    p = add("status", "recent collection runs", cmd_status)
    p.add_argument("--limit", type=int, default=10)

    add("storage", "storage diagnostics", cmd_storage)

    p = sub.add_parser("refresh", help="bounded refresh of the enabled sources (sequential)")
    p.add_argument("--dry-run", action="store_true", help="show the plan and budgets only")
    p.add_argument(
        "--source",
        action="append",
        choices=SOURCES,
        help="source to refresh; repeatable (default: the sources enabled in the plan)",
    )
    p.add_argument("--config", help="refresh plan YAML (default: the packaged plan)")
    p.set_defaults(func=cmd_refresh)

    p = sub.add_parser("health", help="read-only collection, freshness, and storage status")
    p.add_argument("--config", help="refresh plan YAML (thresholds; default: packaged plan)")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser(
        "learn-reset",
        help="optional backup-and-reset of local learning progress (dry run by default)",
    )
    p.add_argument("--execute", action="store_true", help="back up, verify, then reset")
    p.add_argument(
        "--backup-dir", help="where to write the backup (default: outside the repository)"
    )
    p.set_defaults(func=cmd_learn_reset)

    p = sub.add_parser(
        "assumption",
        help="the versioned M1 alignment assumption and its local approval records",
    )
    p.add_argument("action", choices=("show", "status", "approve", "revoke"))
    p.add_argument("--assumption-id", default="M1")
    p.add_argument("--reviewer", help="approve: the reviewer's name, as they supplied it")
    p.add_argument("--role", help="approve: the reviewer's role")
    p.add_argument("--evidence", help="approve: where the approval is documented (a reference)")
    p.add_argument("--approved-on", help="approve: the actual approval date (YYYY-MM-DD)")
    p.add_argument("--record", help="revoke: the approval record id to revoke")
    p.add_argument("--reason", help="revoke: why")
    p.add_argument("--execute", action="store_true", help="append the record (default: dry run)")
    p.set_defaults(func=cmd_assumption)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.no_dotenv:
            loaded = load_dotenv(Path.cwd() / ".env", find_repo_root(Path.cwd()))
            if loaded:
                print(f"Loaded from .env: {', '.join(loaded)} (values not shown)", file=sys.stderr)
        settings = load_settings()
        return args.func(args, settings)
    except (
        ConfigError,
        PlanError,
        EIAError,
        WriterLockError,
        ErcotError,
        ercot_ds.ReportFormatError,
        ercot.SelectionError,
        ArchiveError,
        RefreshConfigError,
        RefreshLockError,
        ercot_prices.PriceFormatError,
        ercot_prices.SelectionError,
        ercot_rt.RtFormatError,
        ercot_rt.SelectionError,
    ) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
