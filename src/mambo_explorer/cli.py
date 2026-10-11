"""Command line: `mambo <command> [--source eia|ercot]`.

Commands:
    sources    reviewed dataset contract; --remote checks the live source
               (EIA: route/entity/metrics with the key; ERCOT: lists available public documents)
    collect    bounded collection (--dry-run shows scope and request budget, sends nothing)
    validate   check stored files against the catalog; report orphans/interrupted runs
    status     recent collection runs
    storage    storage diagnostics

--source defaults to eia. ERCOT (NP6-345-CD) uses ERCOT's public download, needs no
credential, and never uses EIA_API_KEY. Nothing is deleted by default.
Exit codes: 0 ok, 1 check failed, 2 configuration or source error.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

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
from mambo_explorer.ercot.client import ErcotClient, ErcotError
from mambo_explorer.safe_zip import ArchiveError
from mambo_explorer.storage import Store, WriterLockError

SOURCES = ("eia", "ercot")


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _store(args, settings) -> Store:
    return ercot.store(settings.data_dir) if args.source == "ercot" else Store(settings.data_dir)


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
    _print(ds.review_summary())
    if not args.remote:
        print("\n(offline summary; add --remote to verify route, entity, and metrics with EIA)")
        return 0
    client = EIAClient(settings.api_key, max_requests=5)
    _print(ds.verify_metadata(client))
    return 0


def cmd_collect(args, settings) -> int:
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
    plan = plan_collection(
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
            help="eia (EIA-930 via EIA API) or ercot (ERCOT NP6-345-CD direct)",
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
    ) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
