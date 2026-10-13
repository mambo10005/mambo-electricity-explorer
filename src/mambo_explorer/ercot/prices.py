"""ERCOT NP4-190-CD "DAM Settlement Point Prices" for ONE trading hub (Stage 19, ADR 0016).

Every fact below is backed by docs/source-register.md and docs/datasets/ercot-np4-190-cd.md
(review 2026-10-12). Unverified points stay explicit and are never filled in:
- the file states no unit; the Nodal Protocols state DAM Settlement Point Prices in $/MWh
  (Section 4.5.3(5) price-correction thresholds), so the unit is recorded with that basis;
- the file states no time zone; DeliveryDate, HourEnding, and DSTFlag are kept exactly as
  written and never converted to UTC (the load report's conventions are not borrowed);
- finality: the Protocols say DAM prices are final at 1000 on the second Business Day after
  the Operating Day (Section 4.5.3(6)); this app does not compute Business Days, so a stored
  price's finality is shown as "not determined" and never inferred from a refresh;
- price corrections are published in a separate report (NP4-196-M) that is not collected;
  a re-posted NP4-190-CD document with a changed value becomes a new revision.

Access: the same ercot.com public report listing and document download as NP6-345-CD (no
login, no credential). One document holds every settlement point for one DAM run; only the
selected hub's rows are stored, and the downloaded scope is recorded separately.
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
from mambo_explorer.ercot.client import (
    Document,
    ErcotClient,
    ErcotError,
    Report,
    UnavailableError,
)
from mambo_explorer.safe_zip import Limits
from mambo_explorer.storage import Store, now_utc

SOURCE = "ERCOT"
DATASET = "NP4-190-CD"
REPORT_TYPE_ID = "12331"
REPORT_NAME = "DAM Settlement Point Prices"
PRODUCT_PAGE = "https://www.ercot.com/mp/data-products/data-product-details?id=NP4-190-CD"
CSV_FRIENDLY_NAME = "DAMSPNP4190_csv"
STORE_NAMESPACE = "ercot-np4-190-cd"
PUBLIC_RETENTION_DAYS = 31  # EMIL "Display Duration 31"; the live list held 32 CSV documents
MARKET_STAGE = "day-ahead"
METRIC = "settlement_point_price"
LOCATION = "HB_NORTH"  # ERCOT settlement point name, as published
LOCATION_TYPE = "hub"
LOCATION_NAME = "North 345 kV Hub (Nodal Protocols Section 3.5.2.1)"
HEADER = ("DeliveryDate", "HourEnding", "SettlementPoint", "SettlementPointPrice", "DSTFlag")
UNIT = "$/MWh"
UNIT_TEXT = (
    "$/MWh. The file does not state a unit; ERCOT's Nodal Protocols express DAM Settlement "
    "Point Prices in $/MWh (Section 4.5.3(5), price-correction thresholds)."
)
TIME_TEXT = (
    "DeliveryDate, HourEnding ('01:00' … '24:00'), and DSTFlag are shown exactly as ERCOT "
    "writes them. The file states no time zone, so nothing is converted to UTC. The Protocols "
    "define an Operating Day as hours ending 0100 to 2400 and use Central Prevailing Time "
    "elsewhere, but this report's own convention, including how DST days appear, has not been "
    "observed, so the labels are not mapped to clock times."
)
FINALITY_TEXT = (
    "Not determined. ERCOT's Nodal Protocols (Section 4.5.3(6)) say DAM Settlement Point "
    "Prices are final at 1000 on the second Business Day after the Operating Day; this app "
    "does not compute Business Days, and a successful download does not make a price final. "
    "Corrections are published in a separate report (NP4-196-M) that is not collected."
)
DEFINITION_TEXT = (
    "A Day-Ahead Market (DAM) Settlement Point Price at a Hub, as ERCOT publishes it for one "
    "hour of the Operating Day. ERCOT describes the DAM as a voluntary, financially binding "
    "forward energy market. The North 345 kV Hub price in the Day-Ahead uses the aggregated "
    "Shift Factors of its Hub Buses (Protocols Section 3.5.2.1)."
)
NOT_THIS = [
    "Not a bus LMP: ERCOT publishes per-bus DAM LMPs separately (NP4-183-CD); a Hub price is "
    "computed from Hub Bus prices by the Hub's own method.",
    "Not a modeled nodal price: the Model Labs prices come from a synthetic teaching network.",
    "Not a retail tariff or bill: retail prices include other charges and contract terms.",
    "Not a forward price for a future month, and not a forecast of the real-time price.",
    "Not a real-time price: real-time Settlement Point Prices are a different report.",
]

# One document is ~190 KB zipped and ~1 MB of CSV (2026-10-12 review: 1,130 settlement
# points × 24 rows). Limits leave headroom without allowing an unbounded archive.
ZIP_LIMITS = Limits(
    max_archive_bytes=600_000,
    max_members=1,
    max_member_bytes=4_000_000,
    max_total_bytes=4_000_000,
    allowed_suffixes=(".csv",),
)
REPORT = Report(REPORT_TYPE_ID, CSV_FRIENDLY_NAME, DATASET, ZIP_LIMITS)
MAX_DOCUMENTS_PER_RUN = 3
DEFAULT_LATEST = 2
MAX_ROWS_PER_DOCUMENT = 200_000  # scope guard: more is not this report

SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("dataset", pa.string()),
        ("report_type_id", pa.string()),
        ("market_stage", pa.string()),
        ("location", pa.string()),
        ("location_type", pa.string()),
        ("entity", pa.string()),  # = location; the Store partitions files by entity
        ("metric", pa.string()),
        ("doc_id", pa.string()),
        ("doc_name", pa.string()),
        ("publish_time_raw", pa.string()),
        ("publication_time_utc", pa.timestamp("us", tz="UTC")),
        ("delivery_date_raw", pa.string()),
        ("delivery_date", pa.date32()),
        ("hour_ending", pa.string()),
        ("dst_flag", pa.string()),
        ("row_order", pa.int32()),
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
    "hour_ending",
    "dst_flag",
)

_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_HOUR = re.compile(r"(\d{2}):00")


class PriceFormatError(ValueError):
    pass


class SelectionError(ValueError):
    pass


@dataclass(frozen=True)
class PriceRow:
    delivery_date_raw: str
    delivery_date: date
    hour_ending: str
    dst_flag: str
    row_order: int
    value_raw: str


@dataclass(frozen=True)
class Parsed:
    rows: list[PriceRow]  # the selected location only, in file order
    downloaded_rows: int
    downloaded_settlement_points: int
    delivery_dates: tuple[str, ...]


def parse_csv(data: bytes, location: str = LOCATION) -> Parsed:
    """Validate the whole file, keep only `location`. Never imputes or reorders values."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise PriceFormatError("CSV is not UTF-8") from None
    reader = csv.reader(io.StringIO(text))
    header = tuple(next(reader, ()))
    if header != HEADER:
        raise PriceFormatError(f"unexpected header {header!r}; expected {HEADER!r}")
    kept: list[PriceRow] = []
    points: set[str] = set()
    dates: set[str] = set()
    total = 0
    seen: set[tuple[str, str, str]] = set()
    for line_no, cells in enumerate(reader, start=2):
        if not cells:
            continue
        if len(cells) != len(HEADER):
            raise PriceFormatError(f"line {line_no}: {len(cells)} fields")
        total += 1
        if total > MAX_ROWS_PER_DOCUMENT:
            raise PriceFormatError("more rows than this report can hold")
        day, hour, point, price, dst = (c.strip() for c in cells)
        m = _DATE.fullmatch(day)
        if not m:
            raise PriceFormatError(f"line {line_no}: DeliveryDate {day!r}")
        hm = _HOUR.fullmatch(hour)
        if not hm or not 1 <= int(hm.group(1)) <= 24:
            raise PriceFormatError(f"line {line_no}: HourEnding {hour!r}")
        if dst not in ("N", "Y"):
            raise PriceFormatError(f"line {line_no}: DSTFlag {dst!r}")
        if not point:
            raise PriceFormatError(f"line {line_no}: empty SettlementPoint")
        points.add(point)
        dates.add(day)
        if point != location:
            continue
        key = (day, hour, dst)
        if key in seen:
            raise PriceFormatError(f"duplicate {location} row for {key}")
        seen.add(key)
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        kept.append(PriceRow(day, date(y, mo, d), hour, dst, len(kept) + 1, price))
    if total == 0:
        raise PriceFormatError("no data rows")
    if not kept:
        raise PriceFormatError(f"settlement point {location} is not in this document")
    if len(kept) > 25:
        raise PriceFormatError(f"{len(kept)} rows for {location}; at most 25 hours per day")
    return Parsed(kept, total, len(points), tuple(sorted(dates)))


def parse_price(raw: str) -> tuple[float | None, list[str]]:
    """Signed price exactly as written; blank stays missing (never zero)."""
    return load_ds.parse_value(raw)


def store(data_dir: Path) -> Store:
    return Store(data_dir, namespace=STORE_NAMESPACE, schema=SCHEMA, identity=IDENTITY)


@dataclass(frozen=True)
class Selection:
    latest: int | None = DEFAULT_LATEST
    publish_dates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.publish_dates and self.latest is not None:
            raise SelectionError("use either latest or publish dates, not both")
        if self.latest is not None and not 1 <= self.latest <= MAX_DOCUMENTS_PER_RUN:
            raise SelectionError(f"latest must be 1..{MAX_DOCUMENTS_PER_RUN}")
        if len(self.publish_dates) > MAX_DOCUMENTS_PER_RUN:
            raise SelectionError(f"at most {MAX_DOCUMENTS_PER_RUN} publish dates per run")

    def apply(self, documents: list[Document]) -> list[Document]:
        if self.publish_dates:
            chosen = [d for d in documents if d.publish_time_raw[:10] in self.publish_dates]
            missing = sorted(set(self.publish_dates) - {d.publish_time_raw[:10] for d in chosen})
            if missing:
                raise UnavailableError(
                    f"no public {DATASET} CSV published on {missing}; ERCOT's public list keeps "
                    f"about {PUBLIC_RETENTION_DAYS} days"
                )
            if len(chosen) > MAX_DOCUMENTS_PER_RUN:
                raise SelectionError("selection matches more documents than the per-run limit")
            return chosen
        return documents[-self.latest :]

    def describe(self) -> dict:
        n = self.latest or len(self.publish_dates)
        return {
            "source": f"ERCOT {DATASET} '{REPORT_NAME}' (report type {REPORT_TYPE_ID})",
            "access": "ercot.com public report listing + document download (no login)",
            "selection": (
                f"documents published on {list(self.publish_dates)}"
                if self.publish_dates
                else f"latest {self.latest} CSV document(s) in the public list"
            ),
            "stored_scope": f"{LOCATION} ({LOCATION_NAME}) only; every other settlement point "
            "in each downloaded document is discarded after validation",
            "downloaded_scope": f"{n} whole document(s) (each about 1,100 settlement points × "
            "24 hours, about 190 KB zipped)",
            "request_budget": f"1 list request + up to {n} downloads, plus at most 2 retries "
            "each; 1 s pause between requests",
            "credential": "none (public download); EIA_API_KEY is never used",
        }


def normalize(document, parsed: Parsed, *, run_id, archive, retrieved_at) -> list[dict]:
    published = load_ds.parse_publish_time(document.publish_time_raw)
    records = []
    for row in parsed.rows:
        value, flags = parse_price(row.value_raw)
        records.append(
            {
                "source": SOURCE,
                "dataset": DATASET,
                "report_type_id": REPORT_TYPE_ID,
                "market_stage": MARKET_STAGE,
                "location": LOCATION,
                "location_type": LOCATION_TYPE,
                "entity": LOCATION,
                "metric": METRIC,
                "doc_id": document.doc_id,
                "doc_name": document.name,
                "publish_time_raw": document.publish_time_raw,
                "publication_time_utc": published,
                "delivery_date_raw": row.delivery_date_raw,
                "delivery_date": row.delivery_date,
                "hour_ending": row.hour_ending,
                "dst_flag": row.dst_flag,
                "row_order": row.row_order,
                "value_raw": row.value_raw.strip() or None,
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
        )
    return records


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
    """One bounded collection under the price store's writer lock."""
    with target.writer_lock():
        run_id = target.start_run(
            entity=LOCATION,
            metrics=f"{MARKET_STAGE} {METRIC}",
            request_start=",".join(selection.publish_dates) or f"latest {selection.latest}",
            request_end=None,
            lookback_days=0,
        )
        try:
            chosen = selection.apply(client.list_documents(REPORT))
            files, records, documents = [], [], []
            for document in chosen:  # oldest first, so a repost becomes the later revision
                body, csv_bytes, member = client.download_csv(document, REPORT)
                parsed = parse_csv(csv_bytes)
                record = target.write_raw(run_id, 0, body, False, name=f"{document.doc_id}.zip")
                files.append(record)
                records += normalize(
                    document,
                    parsed,
                    run_id=run_id,
                    archive=(record.path, record.sha256),
                    retrieved_at=now_utc(),
                )
                documents.append(
                    {
                        "doc_id": document.doc_id,
                        "published": document.publish_time_raw,
                        "delivery_dates": list(parsed.delivery_dates),
                        "downloaded_rows": parsed.downloaded_rows,
                        "downloaded_settlement_points": parsed.downloaded_settlement_points,
                        "stored_rows": len(parsed.rows),
                        "member": member,
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
        except (ErcotError, PriceFormatError, SelectionError) as exc:
            target.fail_run(
                run_id, str(exc), requests=client.stats.requests, retries=client.stats.retries
            )
            raise
    return {
        "run_id": run_id,
        "requests": client.stats.requests,
        "retries": client.stats.retries,
        "documents": documents,
        "downloaded_rows": sum(d["downloaded_rows"] for d in documents),
        "stored_scope_rows": len(records),
        **counts,
    }
