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
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pyarrow as pa

from mambo_explorer.ercot import dataset as load_ds
from mambo_explorer.ercot.client import Document, ErcotClient, ErcotError, Report
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
        raise RtFormatError(
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
    return {f["path"].rsplit("/", 1)[1].removesuffix(".zip") for f in target.committed_files("raw")}


@dataclass(frozen=True)
class Selection:
    """The newest `latest` CSV documents in the public list, skipping documents already stored
    (unless `include_stored`, used to re-check for reposts and to prove idempotence)."""

    latest: int = DEFAULT_LATEST
    include_stored: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.latest <= MAX_DOCUMENTS_PER_RUN:
            raise SelectionError(f"latest must be 1..{MAX_DOCUMENTS_PER_RUN}")

    def apply(self, documents: list[Document], stored: set[str]) -> tuple[list[Document], dict]:
        candidates = (
            documents if self.include_stored else [d for d in documents if d.doc_id not in stored]
        )
        chosen = candidates[-self.latest :]
        scope = {
            "listed_documents": len(documents),
            "already_stored_documents": sum(d.doc_id in stored for d in documents),
            "published_not_requested": len(candidates) - len(chosen),
            "oldest_listed_publish_time": documents[0].publish_time_raw if documents else None,
            "newest_listed_publish_time": documents[-1].publish_time_raw if documents else None,
        }
        return chosen, scope

    def describe(self) -> dict:
        return {
            "source": f"ERCOT {DATASET} '{REPORT_NAME}' (report type {REPORT_TYPE_ID})",
            "access": "ercot.com public report listing + document download (no login)",
            "selection": f"newest {self.latest} CSV document(s) in the public list"
            + ("" if self.include_stored else " not already stored"),
            "stored_scope": f"{LOCATION} ({LOCATION_NAME}) only; one 15-minute interval per "
            "document; every other settlement point is discarded after validation",
            "downloaded_scope": f"up to {self.latest} whole document(s) (each about 1,100 "
            "settlement points for one interval, about 8 KB zipped)",
            "request_budget": f"1 list request + up to {self.latest} downloads, plus at most "
            "2 retries each; 1 s pause between requests",
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


def collect(selection: Selection, client: ErcotClient, target: Store) -> dict:
    """One bounded collection under the real-time price store's writer lock."""
    with target.writer_lock():
        run_id = target.start_run(
            entity=LOCATION,
            metrics=f"{MARKET_STAGE} {METRIC}",
            request_start=f"latest {selection.latest}",
            request_end=None,
            lookback_days=0,
        )
        try:
            chosen, scope = selection.apply(client.list_documents(REPORT), stored_doc_ids(target))
            files, records, documents = [], [], []
            for document in chosen:  # oldest first, so a repost becomes the later revision
                body, csv_bytes, member = client.download_csv(document, REPORT)
                parsed = parse_csv(csv_bytes)
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
                documents.append(
                    {
                        "doc_id": document.doc_id,
                        "friendly_name": document.friendly_name,
                        "published": document.publish_time_raw,
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
                pages=len(chosen),
                rows_received=len(records),
                **counts,
            )
        except (ErcotError, RtFormatError, SelectionError) as exc:
            target.fail_run(
                run_id, str(exc), requests=client.stats.requests, retries=client.stats.retries
            )
            raise
    status = (
        "no newer document published yet"
        if not chosen
        else ("collected" if not scope["published_not_requested"] else "partial catch-up")
    )
    return {
        "run_id": run_id,
        "status": status,
        "requests": client.stats.requests,
        "retries": client.stats.retries,
        "documents": documents,
        "scope": scope,
        "downloaded_rows": sum(d["downloaded_rows"] for d in documents),
        "stored_scope_rows": len(records),
        **counts,
    }
