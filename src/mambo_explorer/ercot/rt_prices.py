"""ERCOT NP6-905-CD real-time Settlement Point Prices for ONE hub, HB_NORTH (Stage 20, ADR 0017).

Facts below are backed by docs/source-register.md and docs/datasets/ercot-np6-905-cd.md
(review 2026-10-12). Unverified points stay explicit:
- Product: "Settlement Point Price for each Settlement Point, produced from SCED LMPs every
  15 minutes" (report type 12301). These are real-time SETTLEMENT POINT PRICES, not SCED LMPs
  (ERCOT publishes LMPs in other reports, e.g. NP6-788-CD).
- Interval: one 15-minute Settlement Interval per document, identified by DeliveryDate,
  DeliveryHour (1-24), DeliveryInterval (1-4), and DSTFlag exactly as written. The file
  states no time zone, so no clock time or UTC boundary is derived; DST representation has
  not been observed and no fixed interval count per day is assumed.
- Price: Protocols Section 3.5.2.1(4): RTSPP North345 = Max[-$251, (RTRDP + time-weighted
  Hub Bus prices)] for each 15-minute Settlement Interval, so the Real-Time Reliability
  Deployment Price Adder for Energy is included and a -$251/MWh floor applies. Unit $/MWh.
- Finality: Protocols Section 6.3(7): final at 1600 of the second Business Day after the
  Operating Day; not computed here. Corrections: report NP4-197-M (not collected).
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pyarrow as pa

from mambo_explorer.ercot import dataset as load_ds
from mambo_explorer.ercot import rt_inventory
from mambo_explorer.ercot.client import (
    AccessError,
    BudgetExceeded,
    Document,
    ErcotClient,
    ErcotError,
    Report,
)
from mambo_explorer.safe_zip import Limits
from mambo_explorer.storage import Store, now_utc

SOURCE = "ERCOT"
DATASET = "NP6-905-CD"
REPORT_TYPE_ID = "12301"
REPORT_NAME = "Settlement Point Prices at Resource Nodes, Hubs and Load Zones"
PRODUCT_PAGE = "https://www.ercot.com/mp/data-products/data-product-details?id=NP6-905-CD"
CSV_NAME_PATTERN = r"SPPHLZNP6905_\d{8}_\d{4}_csv"
STORE_NAMESPACE = "ercot-np6-905-cd"
PUBLIC_RETENTION_DAYS = 7  # product page "Display Duration 7"; live list: about 7 days
INTERVAL_MINUTES = 15  # product: "every 15 minutes"; Protocols: 15-minute Settlement Interval
MARKET_STAGE = "real-time"
METRIC = "settlement_point_price"
LOCATION = "HB_NORTH"
LOCATION_TYPE_CODE = "HU"  # SettlementPointType written in the file for hubs
LOCATION_NAME = "North 345 kV Hub (Nodal Protocols Section 3.5.2.1)"
HEADER = (
    "DeliveryDate",
    "DeliveryHour",
    "DeliveryInterval",
    "SettlementPointName",
    "SettlementPointType",
    "SettlementPointPrice",
    "DSTFlag",
)
UNIT = "$/MWh"
UNIT_TEXT = (
    "$/MWh. The file does not state a unit; ERCOT's Nodal Protocols define the hub price "
    "with a -$251/MWh floor (Section 3.5.2.1(4))."
)
PRICE_DEFINITION = (
    "A real-time Settlement Point Price for one 15-minute Settlement Interval at the North "
    "345 kV Hub, as ERCOT publishes it. ERCOT produces it from SCED LMPs; for this hub it is "
    "the time-weighted Hub Bus prices plus the Real-Time Reliability Deployment Price Adder for "
    "Energy, floored at -$251/MWh (Protocols Section 3.5.2.1(4))."
)
TIME_TEXT = (
    "DeliveryDate, DeliveryHour (1-24), DeliveryInterval (1-4), and DSTFlag are shown exactly "
    "as ERCOT writes them; each identifies one 15-minute Settlement Interval. The file states "
    "no time zone, so no clock time or UTC boundary is derived, and the number of intervals on "
    "a daylight-saving day is not assumed."
)
FINALITY_TEXT = (
    "Not determined. ERCOT's Nodal Protocols (Section 6.3(7)) say real-time Settlement Point "
    "Prices are final at 1600 on the second Business Day after the Operating Day, and the "
    "ERCOT Board may still review timely-noticed prices later; this app does not compute "
    "Business Days, and a successful download does not make a price final. Corrections are "
    "published in a separate report (NP4-197-M) that is not collected."
)
NOT_THIS = [
    "Not a SCED LMP: SCED runs every few minutes and its LMPs are separate reports; this is "
    "the 15-minute settlement price produced from them.",
    "Not a day-ahead price: the day-ahead Settlement Point Price is a different market stage "
    "and report (NP4-190-CD). The two are not compared here.",
    "Not a settlement invoice: a market participant's real-time charges also depend on "
    "metered quantities, day-ahead positions, ancillary services, and other charge types.",
    "Not a retail price, a forecast, or a forward price.",
]

# One document is ~8 KB zipped and ~45 KB of CSV (live 2026-10-12: 1,130 points, 1 interval).
ZIP_LIMITS = Limits(
    max_archive_bytes=100_000,
    max_members=1,
    max_member_bytes=500_000,
    max_total_bytes=500_000,
    allowed_suffixes=(".csv",),
)
REPORT = Report(REPORT_TYPE_ID, "", DATASET, ZIP_LIMITS, csv_name_pattern=CSV_NAME_PATTERN)
MAX_DOCUMENTS_PER_RUN = 16  # 4 hours of intervals at most per collection
DEFAULT_LATEST = 4
MAX_ROWS_PER_DOCUMENT = 20_000

SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("dataset", pa.string()),
        ("report_type_id", pa.string()),
        ("market_stage", pa.string()),
        ("location", pa.string()),
        ("settlement_point_type", pa.string()),
        ("entity", pa.string()),
        ("metric", pa.string()),
        ("doc_id", pa.string()),
        ("doc_friendly_name", pa.string()),
        ("publish_time_raw", pa.string()),
        ("publication_time_utc", pa.timestamp("us", tz="UTC")),
        ("delivery_date_raw", pa.string()),
        ("delivery_date", pa.date32()),
        ("delivery_hour", pa.string()),
        ("delivery_interval", pa.string()),
        ("dst_flag", pa.string()),
        ("interval_minutes", pa.int32()),
        ("value_raw", pa.string()),
        ("value", pa.float64()),
        ("unit", pa.string()),
        ("quality_flags", pa.string()),
        ("revision", pa.int32()),
        ("retrieved_at_utc", pa.timestamp("us", tz="UTC")),
        ("downloaded_rows", pa.int32()),
        ("downloaded_settlement_points", pa.int32()),
        ("run_id", pa.string()),
        ("archive_path", pa.string()),
        ("archive_sha256", pa.string()),
    ]
)
IDENTITY = (
    "source",
    "dataset",
    "market_stage",
    "location",
    "delivery_date_raw",
    "delivery_hour",
    "delivery_interval",
    "dst_flag",
)

_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


class RtFormatError(ValueError):
    pass


class LocationAbsentError(RtFormatError):
    """A valid document without the HB_NORTH/HU row: the interval is missing inside it."""


class SelectionError(ValueError):
    pass


@dataclass(frozen=True)
class Parsed:
    delivery_date_raw: str
    delivery_date: date
    delivery_hour: str
    delivery_interval: str
    dst_flag: str
    settlement_point_type: str
    value_raw: str
    downloaded_rows: int
    downloaded_settlement_points: int


def parse_csv(data: bytes, location: str = LOCATION) -> Parsed:
    """Validate the whole file (one interval), keep `location`'s single row."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RtFormatError("CSV is not UTF-8") from None
    reader = csv.reader(io.StringIO(text))
    header = tuple(next(reader, ()))
    if header != HEADER:
        raise RtFormatError(f"unexpected header {header!r}; expected {HEADER!r}")
    keys: set[tuple[str, str, str, str]] = set()
    # Rows are unique by (name, type): the live file (2026-10-12) lists some load zones and DC
    # ties twice with different types (LZ and LZEW, LZ_DC and LZ_DCEW).
    pairs: set[tuple[str, str]] = set()
    points: set[str] = set()
    kept = []
    total = 0
    for line_no, cells in enumerate(reader, start=2):
        if not cells:
            continue
        if len(cells) != len(HEADER):
            raise RtFormatError(f"line {line_no}: {len(cells)} fields")
        total += 1
        if total > MAX_ROWS_PER_DOCUMENT:
            raise RtFormatError("more rows than this report can hold")
        day, hour, interval, point, ptype, price, dst = (c.strip() for c in cells)
        if not _DATE.fullmatch(day):
            raise RtFormatError(f"line {line_no}: DeliveryDate {day!r}")
        if not hour.isdigit() or not 1 <= int(hour) <= 24:
            raise RtFormatError(f"line {line_no}: DeliveryHour {hour!r}")
        if not interval.isdigit() or not 1 <= int(interval) <= 4:
            raise RtFormatError(f"line {line_no}: DeliveryInterval {interval!r}")
        if dst not in ("N", "Y"):
            raise RtFormatError(f"line {line_no}: DSTFlag {dst!r}")
        if not point:
            raise RtFormatError(f"line {line_no}: empty SettlementPointName")
        keys.add((day, hour, interval, dst))
        if (point, ptype) in pairs:
            raise RtFormatError(f"duplicate row for {point!r} type {ptype!r} in one interval")
        pairs.add((point, ptype))
        points.add(point)
        if point == location and ptype == LOCATION_TYPE_CODE:
            kept.append((day, hour, interval, dst, ptype, price))
    if total == 0:
        raise RtFormatError("no data rows")
    if len(keys) != 1:
        raise RtFormatError(f"document covers {len(keys)} intervals; expected exactly one")
    if not kept:
        raise LocationAbsentError(
            f"settlement point {location} with type {LOCATION_TYPE_CODE!r} is not in this document"
        )
    day, hour, interval, dst, ptype, price = kept[0]
    m = _DATE.fullmatch(day)
    return Parsed(
        day,
        date(int(m.group(3)), int(m.group(1)), int(m.group(2))),
        hour,
        interval,
        dst,
        ptype,
        price,
        total,
        len(points),
    )


def store(data_dir: Path) -> Store:
    return Store(data_dir, namespace=STORE_NAMESPACE, schema=SCHEMA, identity=IDENTITY)


def stored_doc_ids(target: Store) -> set[str]:
    """DocIDs with a committed raw archive (collected, or downloaded without an HB_NORTH row)."""
    return {f["path"].rsplit("/", 1)[1].removesuffix(".zip") for f in target.committed_files("raw")}


SNAPSHOT, COVERAGE = "snapshot", "coverage"
MODES = (SNAPSHOT, COVERAGE)
MAX_RECHECK_PER_RUN = 4  # already-collected documents re-downloaded to look for reposts
RETRY_ALLOWANCE = 1  # retries budgeted per run on top of 1 list + downloads


def _day(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


@dataclass(frozen=True)
class Selection:
    """Which listed documents one bounded run requests.

    - snapshot (default): the newest `latest` documents not yet collected (recent observations).
    - coverage: documents whose PublishDate label (as ERCOT writes it) falls in
      [publish_from, publish_to], OLDEST eligible first, so repeated bounded runs make progress
      through a range instead of always favoring the newest intervals.
    In both modes, never-requested and deferred documents come before previously failed ones,
    so one document that keeps failing cannot starve the rest.

    `recheck` is a separate allocation: that many already-collected documents (least recently
    downloaded first) are downloaded again to look for reposts. With recheck 0 revisions are
    not monitored, only unseen documents are fetched.

    `include_stored` keeps Stage 20's revision check: the newest `latest` listed documents,
    stored or not.
    """

    latest: int = DEFAULT_LATEST
    include_stored: bool = False
    mode: str = SNAPSHOT
    publish_from: date | None = None
    publish_to: date | None = None
    recheck: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.latest <= MAX_DOCUMENTS_PER_RUN:
            raise SelectionError(f"latest must be 1..{MAX_DOCUMENTS_PER_RUN}")
        if self.mode not in MODES:
            raise SelectionError(f"mode must be one of {MODES}")
        if not 0 <= self.recheck <= MAX_RECHECK_PER_RUN:
            raise SelectionError(f"recheck must be 0..{MAX_RECHECK_PER_RUN}")
        if self.latest + self.recheck > MAX_DOCUMENTS_PER_RUN:
            raise SelectionError(
                f"documents plus rechecks must be at most {MAX_DOCUMENTS_PER_RUN} per run"
            )
        if self.mode == COVERAGE:
            if self.publish_from is None:
                raise SelectionError("coverage mode needs a first PublishDate")
            if self.publish_to is not None and self.publish_to < self.publish_from:
                raise SelectionError("the last PublishDate is before the first")
            if self.include_stored:
                raise SelectionError("coverage mode uses --recheck, not --include-stored")
        elif self.publish_from or self.publish_to:
            raise SelectionError("a PublishDate range needs coverage mode")

    @property
    def request_budget(self) -> int:
        """1 list request + every planned download + a small retry allowance."""
        return 1 + self.latest + self.recheck + RETRY_ALLOWANCE

    def range_text(self) -> str:
        if self.mode == SNAPSHOT:
            return "every listed document (snapshot mode)"
        end = _day(self.publish_to) or "the newest listed"
        return f"PublishDate {_day(self.publish_from)} through {end} (ERCOT's labels, as written)"

    def in_range(self, document: Document) -> bool:
        if self.mode == SNAPSHOT:
            return True
        day = rt_inventory.publish_date(document.publish_time_raw)
        start, end = _day(self.publish_from), _day(self.publish_to)
        return day >= start and (end is None or day <= end)

    def apply(
        self,
        documents: list[Document],
        statuses: dict[str, str],
        last_downloaded: dict[str, str | None] | None = None,
    ) -> tuple[list[Document], list[Document], dict]:
        """(new documents, recheck documents, scope). `documents` is the listing, oldest first;
        `statuses` maps DocID to its inventory status (missing means never seen before)."""
        last_downloaded = last_downloaded or {}
        status = {d.doc_id: statuses.get(d.doc_id, rt_inventory.DISCOVERED) for d in documents}
        done = (rt_inventory.COLLECTED, rt_inventory.SUPERSEDED)
        scoped = [d for d in documents if self.in_range(d)]
        recheck: list[Document] = []
        if self.include_stored:
            chosen, eligible = scoped[-self.latest :], scoped
        else:
            eligible = [
                d
                for d in scoped
                if status[d.doc_id]
                in (rt_inventory.DISCOVERED, rt_inventory.DEFERRED, rt_inventory.FAILED)
            ]
            unseen = [d for d in eligible if status[d.doc_id] != rt_inventory.FAILED]
            failed = [d for d in eligible if status[d.doc_id] == rt_inventory.FAILED]
            if self.mode == SNAPSHOT:
                ordered = unseen[::-1] + failed[::-1]
            else:
                ordered = unseen + failed
            chosen = sorted(ordered[: self.latest], key=documents.index)
            # Superseded documents are never rechecked: re-reading an older posting would
            # look like a new revision of an interval a later document already revised.
            collected = [d for d in scoped if status[d.doc_id] == rt_inventory.COLLECTED]
            collected.sort(key=lambda d: (last_downloaded.get(d.doc_id) or "", documents.index(d)))
            recheck = sorted(collected[: self.recheck], key=documents.index)
        deferred = [d for d in eligible if d not in chosen]
        scope = {
            "mode": self.mode,
            "range": self.range_text(),
            "listed_documents": len(documents),
            "listed_in_range": len(scoped),
            "collected_in_range": sum(status[d.doc_id] in done for d in scoped),
            "eligible_in_range": len(eligible),
            "uncollected_in_range": sum(
                status[d.doc_id]
                in (rt_inventory.DISCOVERED, rt_inventory.DEFERRED, rt_inventory.FAILED)
                for d in scoped
            ),
            "requested_new": len(chosen),
            "requested_recheck": len(recheck),
            "deferred_by_document_bound": len(deferred),
            "previously_failed_in_range": sum(
                status[d.doc_id] == rt_inventory.FAILED for d in scoped
            ),
            "interval_row_absent_in_range": sum(
                status[d.doc_id] == rt_inventory.ROW_ABSENT for d in scoped
            ),
            # Stage 20 names, kept for the refresh log and existing readers
            "already_stored_documents": sum(status[d.doc_id] in done for d in documents),
            "published_not_requested": len(deferred),
            "oldest_listed_publish_time": documents[0].publish_time_raw if documents else None,
            "newest_listed_publish_time": documents[-1].publish_time_raw if documents else None,
            "unavailable": self.unavailable(documents),
        }
        return chosen, recheck, scope

    def unavailable(self, documents: list[Document]) -> str | None:
        """What part of a coverage range this access method cannot reach (None if nothing)."""
        if self.mode == SNAPSHOT:
            return None
        start, end = _day(self.publish_from), _day(self.publish_to)
        if not documents:
            return "ERCOT's public list returned no documents; nothing in the range is reachable"
        oldest = rt_inventory.publish_date(documents[0].publish_time_raw)
        newest = rt_inventory.publish_date(documents[-1].publish_time_raw)
        notes = []
        if start < oldest:
            day_before = (date.fromisoformat(oldest) - timedelta(days=1)).isoformat()
            last_missing = end if end is not None and end < oldest else day_before
            notes.append(
                f"PublishDates {start} through {last_missing} are older than ERCOT's public "
                f"list, which begins at {documents[0].publish_time_raw}; they are not available "
                "through the access method this app implements (ERCOT or another authorized "
                "archive may still hold them)"
            )
        elif start == oldest:
            notes.append(
                f"ERCOT's public list begins at {documents[0].publish_time_raw}, the first "
                f"listed document with PublishDate {oldest}; whether earlier documents with "
                "that date were published is not known from the list"
            )
        if start > newest:
            notes.append(f"no document with PublishDate {start} or later is listed yet")
        elif end is not None and end > newest:
            notes.append(f"no document with PublishDate after {newest} is listed yet")
        return "; ".join(notes) or None

    def describe(self) -> dict:
        if self.include_stored:
            selection = f"newest {self.latest} CSV document(s) in the public list, stored or not"
        elif self.mode == SNAPSHOT:
            selection = f"newest {self.latest} listed CSV document(s) not yet collected"
        else:
            selection = (
                f"up to {self.latest} OLDEST listed CSV document(s) not yet collected in the "
                "range; later runs continue where this one stops"
            )
        return {
            "source": f"ERCOT {DATASET} '{REPORT_NAME}' (report type {REPORT_TYPE_ID})",
            "access": "ercot.com public report listing + document download (no login)",
            "mode": self.mode,
            "range": self.range_text(),
            "selection": selection,
            "revision_recheck": (
                f"{self.recheck} already-collected document(s) re-downloaded, least recently "
                "checked first"
                if self.recheck
                else "none allocated: only unseen documents are fetched, so reposts of "
                "collected documents are not monitored by this run"
            ),
            "stored_scope": f"{LOCATION} ({LOCATION_NAME}) only; one 15-minute interval per "
            "document; every other settlement point is discarded after validation",
            "downloaded_scope": f"up to {self.latest + self.recheck} whole document(s) (each "
            "about 1,100 settlement points for one interval, about 8 KB zipped)",
            "request_budget": f"{self.request_budget} requests: 1 list + up to "
            f"{self.latest + self.recheck} downloads + {RETRY_ALLOWANCE} retry; every HTTP "
            "attempt, retries included, counts; sequential with a 1 s pause; the run stops "
            "at the budget and commits what it has",
            "credential": "none (public download); EIA_API_KEY is never used",
        }


def normalize(document: Document, parsed: Parsed, *, run_id, archive, retrieved_at) -> dict:
    value, flags = load_ds.parse_value(parsed.value_raw)
    return {
        "source": SOURCE,
        "dataset": DATASET,
        "report_type_id": REPORT_TYPE_ID,
        "market_stage": MARKET_STAGE,
        "location": LOCATION,
        "settlement_point_type": parsed.settlement_point_type,
        "entity": LOCATION,
        "metric": METRIC,
        "doc_id": document.doc_id,
        "doc_friendly_name": document.friendly_name,
        "publish_time_raw": document.publish_time_raw,
        "publication_time_utc": load_ds.parse_publish_time(document.publish_time_raw),
        "delivery_date_raw": parsed.delivery_date_raw,
        "delivery_date": parsed.delivery_date,
        "delivery_hour": parsed.delivery_hour,
        "delivery_interval": parsed.delivery_interval,
        "dst_flag": parsed.dst_flag,
        "interval_minutes": INTERVAL_MINUTES,
        "value_raw": parsed.value_raw or None,
        "value": value,
        "unit": UNIT,
        "quality_flags": ",".join(flags),
        "revision": 0,
        "retrieved_at_utc": retrieved_at,
        "downloaded_rows": parsed.downloaded_rows,
        "downloaded_settlement_points": parsed.downloaded_settlement_points,
        "run_id": run_id,
        "archive_path": archive[0],
        "archive_sha256": archive[1],
    }


def assign_revisions(target: Store, records: list[dict]) -> tuple[list[dict], dict]:
    latest = target.latest_index(
        {"delivery_date_raw": sorted({r["delivery_date_raw"] for r in records})}
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
        latest[key] = (record["value_raw"], record["unit"], record["revision"])
        keep.append(record)
    return keep, counts


def _status(selection: Selection, scope: dict, work: int, failed: int, stopped: str | None):
    if stopped:
        return f"stopped early ({stopped}); collected documents were committed"
    if failed:
        return "completed with document failures"
    if not work:
        if selection.mode == COVERAGE:
            return (
                "no uncollected listed document in the range"
                if scope["listed_in_range"]
                else "no listed document in the range"
            )
        return "no newer document published yet"
    if scope["deferred_by_document_bound"]:
        return "partial catch-up" if selection.mode == SNAPSHOT else "range in progress"
    return "collected"


def collect(
    selection: Selection,
    client: ErcotClient,
    target: Store,
    *,
    now: Callable[[], datetime] = now_utc,
) -> dict:
    """One bounded run under the real-time store's writer lock.

    The listing is recorded in the inventory first. Each document then succeeds or fails on its
    own: a missing, refused-as-not-a-ZIP, or malformed document is recorded as failed and the
    run continues; a document without an HB_NORTH row keeps its archive and is recorded as
    interval-row-absent. Reaching the request budget, or an access refusal, stops the run; what
    was downloaded is committed and the rest is recorded as deferred, so the next run resumes
    without duplicate observations (identity + revision rules).
    """
    inventory = rt_inventory.Inventory(target)
    with target.writer_lock():
        run_id = target.start_run(
            entity=LOCATION,
            metrics=f"{MARKET_STAGE} {METRIC}",
            request_start=(
                f"latest {selection.latest}"
                if selection.mode == SNAPSHOT
                else f"coverage {_day(selection.publish_from)}"
            ),
            request_end=_day(selection.publish_to),
            lookback_days=0,
        )
        try:
            listed = client.list_documents(REPORT)
            listing = inventory.record_listing(listed, now())
            rows = rt_inventory.classify(
                inventory.documents(),
                rt_inventory.collected_doc_ids(target),
                rt_inventory.superseded_doc_ids(target),
            )
            statuses = {r["doc_id"]: r["status"] for r in rows}
            downloaded = {r["doc_id"]: r["last_downloaded_utc"] for r in rows}
            chosen, recheck, scope = selection.apply(listed, statuses, downloaded)
            work = sorted(
                [(d, "new") for d in chosen] + [(d, "recheck") for d in recheck],
                key=lambda item: listed.index(item[0]),
            )
            files, records, documents, outcomes = [], [], [], []
            stopped = None
            for index, (document, why) in enumerate(work):
                try:
                    body, csv_bytes, _member = client.download_csv(document, REPORT)
                except (BudgetExceeded, AccessError) as exc:
                    stopped = str(exc)
                    outcomes += [
                        (d.doc_id, rt_inventory.DEFERRED, f"not requested: {exc}")
                        for d, kind in work[index:]
                        if kind == "new" and statuses.get(d.doc_id) != rt_inventory.FAILED
                    ]
                    break
                except ErcotError as exc:
                    outcomes.append((document.doc_id, rt_inventory.FAILED, str(exc)))
                    documents.append(_doc_entry(document, why, rt_inventory.FAILED, str(exc)))
                    continue
                try:
                    parsed = parse_csv(csv_bytes)
                except LocationAbsentError as exc:
                    files.append(
                        target.write_raw(run_id, 0, body, False, name=f"{document.doc_id}.zip")
                    )
                    outcomes.append((document.doc_id, rt_inventory.ROW_ABSENT, str(exc)))
                    documents.append(_doc_entry(document, why, rt_inventory.ROW_ABSENT, str(exc)))
                    continue
                except RtFormatError as exc:
                    message = f"format: {exc}"
                    outcomes.append((document.doc_id, rt_inventory.FAILED, message))
                    documents.append(_doc_entry(document, why, rt_inventory.FAILED, message))
                    continue
                record = target.write_raw(run_id, 0, body, False, name=f"{document.doc_id}.zip")
                files.append(record)
                records.append(
                    normalize(
                        document,
                        parsed,
                        run_id=run_id,
                        archive=(record.path, record.sha256),
                        retrieved_at=now_utc(),
                    )
                )
                outcomes.append((document.doc_id, rt_inventory.COLLECTED, None))
                documents.append(
                    {
                        **_doc_entry(document, why, rt_inventory.COLLECTED),
                        "interval": f"{parsed.delivery_date_raw} H{parsed.delivery_hour} "
                        f"I{parsed.delivery_interval} {parsed.dst_flag}",
                        "downloaded_rows": parsed.downloaded_rows,
                        "downloaded_settlement_points": parsed.downloaded_settlement_points,
                        "stored_rows": 1,
                    }
                )
            keep, counts = assign_revisions(target, records)
            files += target.write_observations(run_id, keep)
            target.commit_run(
                run_id,
                files,
                requests=client.stats.requests,
                retries=client.stats.retries,
                pages=len(documents),
                rows_received=len(records),
                **counts,
            )
        except (ErcotError, RtFormatError, SelectionError) as exc:
            target.fail_run(
                run_id, str(exc), requests=client.stats.requests, retries=client.stats.retries
            )
            raise
        # Eligible documents this run left because of its document bound. A previously failed
        # one keeps "failed" so it stays behind never-requested documents next time.
        outcomes += [
            (d.doc_id, rt_inventory.DEFERRED, "left by this run's document bound")
            for d in listed
            if d not in chosen
            and selection.in_range(d)
            and not selection.include_stored
            and statuses.get(d.doc_id) in (rt_inventory.DISCOVERED, rt_inventory.DEFERRED)
        ]
        inventory.record_outcomes(outcomes, now())
    failed = sum(d["outcome"] == rt_inventory.FAILED for d in documents)
    collected_new = sum(
        d["outcome"] in (rt_inventory.COLLECTED, rt_inventory.ROW_ABSENT)
        and statuses.get(d["doc_id"]) not in (rt_inventory.COLLECTED, rt_inventory.SUPERSEDED)
        for d in documents
    )
    deferred = sum(o[1] == rt_inventory.DEFERRED for o in outcomes)
    return {
        "run_id": run_id,
        "status": _status(selection, scope, len(work), failed, stopped),
        "mode": selection.mode,
        "range": selection.range_text(),
        "requests": client.stats.requests,
        "retries": client.stats.retries,
        "request_breakdown": client.stats.breakdown(),
        "listing": listing,
        "documents": documents,
        "documents_failed": failed,
        "documents_deferred": deferred,
        "stopped_early": stopped,
        "revision_recheck": {
            "allocated": selection.recheck,
            "rechecked": sum(
                d["kind"] == "recheck" and d["outcome"] == rt_inventory.COLLECTED for d in documents
            ),
        },
        "scope": scope,
        # Listed, in range, still not collected after this run (failed ones included).
        "remaining_uncollected_in_range": scope["uncollected_in_range"] - collected_new,
        "downloaded_rows": sum(d.get("downloaded_rows", 0) for d in documents),
        "stored_scope_rows": len(records),
        **counts,
    }


def _doc_entry(document: Document, kind: str, outcome: str, error: str | None = None) -> dict:
    entry = {
        "doc_id": document.doc_id,
        "friendly_name": document.friendly_name,
        "published": document.publish_time_raw,
        "kind": kind,
        "outcome": outcome,
    }
    if error:
        entry["error"] = error
    return entry


def preview(selection: Selection, target: Store) -> dict:
    """Dry-run scope from the LAST RECORDED listing (sends nothing, writes nothing).

    The real run lists again first, so its counts can differ: new documents may have been
    published and old ones may have left the list since.
    """
    inventory = rt_inventory.Inventory(target)
    listing = inventory.last_listing()
    if listing is None:
        return {
            "as_of": "no listing recorded yet; the run will list ERCOT's documents first",
            "request_budget": selection.request_budget,
        }
    rows = rt_inventory.classify(
        inventory.documents(),
        rt_inventory.collected_doc_ids(target),
        rt_inventory.superseded_doc_ids(target),
    )
    listed = [r for r in rows if r["listed"]]
    documents = [
        Document(r["doc_id"], "", r["publish_time_raw"], 0, r["friendly_name"]) for r in listed
    ]
    chosen, recheck, scope = selection.apply(
        documents,
        {r["doc_id"]: r["status"] for r in rows},
        {r["doc_id"]: r["last_downloaded_utc"] for r in rows},
    )
    return {
        "as_of": f"the listing recorded at {listing['listed_at_utc']} (UTC); the run lists "
        "again first, so counts can change",
        "would_request_new": [d.friendly_name for d in chosen],
        "would_recheck": [d.friendly_name for d in recheck],
        "scope": scope,
        "request_budget": selection.request_budget,
    }
