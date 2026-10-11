"""Command line: `mambo <command>` (or `python -m mambo_explorer.cli <command>`).

Commands:
    sources    reviewed dataset scope; --remote verifies route, entity, and metrics live
    collect    bounded collection (--dry-run shows scope and request budget, no key needed)
    validate   check stored files against the catalog; report orphans/interrupted runs
    status     recent collection runs
    storage    storage diagnostics

Nothing is deleted by default. Exit codes: 0 ok, 1 check failed, 2 configuration or
source error.
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
from mambo_explorer.storage import Store, WriterLockError


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_sources(args, settings) -> int:
    _print(ds.review_summary())
    if not args.remote:
        print("\n(offline summary; add --remote to verify route, entity, and metrics with EIA)")
        return 0
    client = EIAClient(settings.api_key, max_requests=5)
    _print(ds.verify_metadata(client))
    return 0


def cmd_collect(args, settings) -> int:
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
    report = Store(settings.data_dir).validate(
        mark_interrupted=args.mark_interrupted, quarantine_orphans=args.quarantine_orphans
    )
    _print(report)
    return 0 if report["ok"] else 1


def cmd_status(args, settings) -> int:
    store = Store(settings.data_dir)
    runs = store.runs(limit=args.limit)
    if not runs:
        print(f"No collection runs in {store.root}.")
    _print(runs)
    return 0


def cmd_storage(args, settings) -> int:
    _print(Store(settings.data_dir).diagnostics())
    return 0


def _date(text: str) -> date:
    return date.fromisoformat(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mambo", description=__doc__.split("\n")[0])
    parser.add_argument("--no-dotenv", action="store_true", help="do not load ./.env")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sources", help="show reviewed dataset scope")
    p.add_argument("--remote", action="store_true", help="verify metadata with EIA (needs key)")
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser("collect", help="bounded EIA-930 collection")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS, help="completed UTC days to fetch")
    p.add_argument("--start", type=_date, help="first UTC day (YYYY-MM-DD)")
    p.add_argument("--end", type=_date, help="UTC day after the last day (exclusive)")
    p.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="extra earlier days re-fetched to detect revisions",
    )
    p.add_argument("--page-size", type=int, default=ds.MAX_ROWS_PER_REQUEST)
    p.add_argument("--max-requests", type=int, help="request budget including retries")
    p.add_argument("--dry-run", action="store_true", help="show scope and budget only")
    p.set_defaults(func=cmd_collect)
    p.epilog = f"At most {MAX_DAYS_PER_RUN} days per run, including lookback."

    p = sub.add_parser("validate", help="verify stored files and catalog")
    p.add_argument("--mark-interrupted", action="store_true", help="mark stale runs abandoned")
    p.add_argument(
        "--quarantine-orphans", action="store_true", help="move unregistered files to quarantine/"
    )
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("status", help="recent collection runs")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("storage", help="storage diagnostics")
    p.set_defaults(func=cmd_storage)
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
    except (ConfigError, PlanError, EIAError, WriterLockError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
