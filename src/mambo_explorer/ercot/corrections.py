"""ERCOT price-correction reports for ONE trading hub (Stage 27, ADR 0024).

Two reports, each its own store, each filtered to `HB_NORTH` only:
- NP4-196-M "DAM Price Corrections" (report type 13044), the `DAM_SPP` document kind;
- NP4-197-M "RTM Price Corrections" (report type 13045), the `RTM_SPP` document kind.

Facts below come from docs/datasets/ercot-np4-196-m.md and ercot-np4-197-m.md (review and
bounded live sample 2026-11-26). Unverified points stay explicit and are never filled in:
- a document lists ONLY the corrected rows, so absence of a row is not proof that no
  correction exists, and a document without a hub row is a normal, recorded outcome;
- the files state no unit; the Nodal Protocols state Settlement Point Prices in $/MWh;
- DeliveryDate, DeliveryHour (and DeliveryInterval), DSTFlag, and PriceCorrectionTime are
  kept exactly as written: no time zone is stated, nothing is converted to UTC, and these
  labels are never mapped to the HourEnding labels of NP4-190-CD (they are different fields);
- a correction event is one (interval label, PriceCorrectionTime); a later correction of the
  same interval is a separate observation, never a replacement. Corrections are never applied
  to stored prices and never make a price "final".

Access: the same ercot.com public report listing and download as the other ERCOT reports (no
login, no credential).
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
METRIC = "price_correction"
LOCATION = "HB_NORTH"  # ERCOT settlement point name, as published
UNIT = "$/MWh"
PUBLIC_RETENTION_DAYS = 180  # EMIL "Display Duration 180"; the live RTM list held 139 days
MAX_DOCUMENTS_PER_RUN = 3
DEFAULT_LATEST = 1
MAX_ROWS_PER_DOCUMENT = 500_000  # scope guard: more is not this report

UNIT_TEXT = (
    "$/MWh. The files do not state a unit; ERCOT's Nodal Protocols express Settlement Point "
    "Prices in $/MWh (Section 4.5.3(5) and Section 6.3 price-correction thresholds)."
)
TIME_TEXT = (
    "DeliveryDate, DeliveryHour (and DeliveryInterval), DSTFlag, and PriceCorrectionTime are "
    "shown exactly as ERCOT writes them. The files state no time zone, so nothing is converted "
    "to UTC. DeliveryHour is a different field from NP4-190-CD's HourEnding, and the labels are "
    "not mapped to clock times or to another report's labels."
)
CORRECTION_TEXT = (
    "A document lists only the rows ERCOT corrected, as an original and a corrected price with "
    "the time of the correction. A missing row is not evidence that no correction exists, and "
    "the corrected price is never written into the stored price series."
)
FINALITY_TEXT = (
    "Not determined. Collecting a correction does not make any price final, and the absence of "
    "a correction does not either; this app does not compute Business Days."
)
# Real-time documents are far larger than day-ahead ones (live sample: up to ~760 KB zipped).
ZIP_LIMITS = Limits(
    max_archive_bytes=3_000_000,
    max_members=1,
    max_member_bytes=30_000_000,
    max_total_bytes=30_000_000,
    allowed_suffixes=(".csv",),
)


@dataclass(frozen=True)
class Kind:
    key: str  # CLI source name
    dataset: str
    report_type_id: str
    report_name: str
    market_stage: str
    document_kind: str  # the one document family of the report that carries SPP corrections
    header: tuple[str, ...]
    namespace: str
    point_column: str
    interval: bool  # real-time files carry DeliveryInterval
    name_tag: str  # how the FriendlyName ends before "_csv" (the live names omit the "-M")

    @property
    def product_page(self) -> str:
        return f"https://www.ercot.com/mp/data-products/data-product-details?id={self.dataset}"

    @property
    def csv_pattern(self) -> str:
        tail = self.name_tag
        return rf"pricecorrection_{self.document_kind}_\d{{8}}_to_\d{{8}}_{tail}_csv"

    @property
    def report(self) -> Report:
        return Report(
            self.report_type_id, "", self.dataset, ZIP_LIMITS, csv_name_pattern=self.csv_pattern
        )

    @property
    def identity(self) -> tuple[str, ...]:
        keys = ["source", "dataset", "market_stage", "location", "delivery_date_raw"]
        keys += ["delivery_hour", "delivery_interval", "dst_flag", "correction_time_raw"]
        return tuple(keys)


DAM = Kind(
    key="ercot-dam-corrections",
    dataset="NP4-196-M",
    report_type_id="13044",
    report_name="DAM Price Corrections",
    market_stage="day-ahead",
    document_kind="DAM_SPP",
    header=(
        "DeliveryDate",
        "DeliveryHour",
        "SettlementPoint",
        "SPPOriginal",
        "SPPCorrected",
        "PriceCorrectionTime",
        "DSTFlag",
    ),
    namespace="ercot-np4-196-m",
    point_column="SettlementPoint",
    interval=False,
    name_tag="NP4196",
)
RTM = Kind(
    key="ercot-rt-corrections",
    dataset="NP4-197-M",
    report_type_id="13045",
    report_name="RTM Price Corrections",
    market_stage="real-time",
    document_kind="RTM_SPP",
    header=(
        "DeliveryDate",
        "DeliveryHour",
        "DeliveryInterval",
        "SettlementPointName",
        "SettlementPointType",
        "SPPOriginal",
        "SPPCorrected",
        "PriceCorrectionTime",
        "DSTFlag",
    ),
    namespace="ercot-np4-197-m",
    point_column="SettlementPointName",
    interval=True,
    name_tag="NP4197",
)
KINDS = {k.key: k for k in (DAM, RTM)}

SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("dataset", pa.string()),
        ("report_type_id", pa.string()),
        ("market_stage", pa.string()),
        ("location", pa.string()),
        ("location_type", pa.string()),  # as the file states it; null when the file has none
        ("entity", pa.string()),  # = location; the Store partitions files by entity
        ("metric", pa.string()),
        ("doc_id", pa.string()),
        ("doc_name", pa.string()),
        ("publish_time_raw", pa.string()),
        ("publication_time_utc", pa.timestamp("us", tz="UTC")),
        ("delivery_date_raw", pa.string()),
        ("delivery_date", pa.date32()),
        ("delivery_hour", pa.string()),
        ("delivery_interval", pa.string()),  # null for day-ahead
        ("dst_flag", pa.string()),
        ("correction_time_raw", pa.string()),
        ("row_order", pa.int32()),
        ("original_raw", pa.string()),
        ("original_value", pa.float64()),
        ("corrected_raw", pa.string()),
        ("corrected_value", pa.float64()),
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

_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_STAMP = re.compile(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}")


class CorrectionFormatError(ValueError):
    pass


class SelectionError(ValueError):
    pass


@dataclass(frozen=True)
class CorrectionRow:
    delivery_date_raw: str
    delivery_date: date
    delivery_hour: str
    delivery_interval: str | None
    dst_flag: str
    correction_time_raw: str
    row_order: int
    original_raw: str
    corrected_raw: str
    location_type: str | None


@dataclass(frozen=True)
class Parsed:
    rows: list[CorrectionRow]  # the hub's rows only, in file order (may be empty)
    downloaded_rows: int
    downloaded_settlement_points: int
    delivery_dates: tuple[str, ...]


def parse_csv(data: bytes, kind: Kind, location: str = LOCATION) -> Parsed:
    """Validate the whole file, keep only `location`. A file without the hub is valid."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CorrectionFormatError("CSV is not UTF-8") from None
    reader = csv.reader(io.StringIO(text))
    header = tuple(next(reader, ()))
    if header != kind.header:
        raise CorrectionFormatError(f"unexpected header {header!r}; expected {kind.header!r}")
    index = {name: i for i, name in enumerate(kind.header)}
    kept: list[CorrectionRow] = []
    points: set[str] = set()
    dates: set[str] = set()
    seen: set[tuple] = set()
    total = 0
    for line_no, cells in enumerate(reader, start=2):
        if not cells:
            continue
        if len(cells) != len(kind.header):
            raise CorrectionFormatError(f"line {line_no}: {len(cells)} fields")
        total += 1
        if total > MAX_ROWS_PER_DOCUMENT:
            raise CorrectionFormatError("more rows than this report can hold")
        row = {name: cells[i].strip() for name, i in index.items()}
        match = _DATE.fullmatch(row["DeliveryDate"])
        if not match:
            raise CorrectionFormatError(f"line {line_no}: DeliveryDate {row['DeliveryDate']!r}")
        if not row["DeliveryHour"].isdigit() or not 1 <= int(row["DeliveryHour"]) <= 24:
            raise CorrectionFormatError(f"line {line_no}: DeliveryHour {row['DeliveryHour']!r}")
        interval = row.get("DeliveryInterval")
        if kind.interval and (interval is None or interval not in ("1", "2", "3", "4")):
            raise CorrectionFormatError(f"line {line_no}: DeliveryInterval {interval!r}")
        if row["DSTFlag"] not in ("N", "Y"):
            raise CorrectionFormatError(f"line {line_no}: DSTFlag {row['DSTFlag']!r}")
        if not _STAMP.fullmatch(row["PriceCorrectionTime"]):
            raise CorrectionFormatError(
                f"line {line_no}: PriceCorrectionTime {row['PriceCorrectionTime']!r}"
            )
        point = row[kind.point_column]
        if not point:
            raise CorrectionFormatError(f"line {line_no}: empty settlement point")
        points.add(point)
        dates.add(row["DeliveryDate"])
        if point != location:
            continue
        key = (
            row["DeliveryDate"],
            row["DeliveryHour"],
            interval,
            row["DSTFlag"],
            row["PriceCorrectionTime"],
        )
        if key in seen:
            raise CorrectionFormatError(f"duplicate {location} correction for {key}")
        seen.add(key)
        mo, d, y = (int(g) for g in match.groups())
        kept.append(
            CorrectionRow(
                row["DeliveryDate"],
                date(y, mo, d),
                row["DeliveryHour"],
                interval,
                row["DSTFlag"],
                row["PriceCorrectionTime"],
                len(kept) + 1,
                row["SPPOriginal"],
                row["SPPCorrected"],
                row.get("SettlementPointType") or None,
            )
        )
    if total == 0:
        raise CorrectionFormatError("no data rows")
    return Parsed(kept, total, len(points), tuple(sorted(dates)))


def parse_price(raw: str) -> tuple[float | None, list[str]]:
    """Signed price exactly as written; blank stays missing (never zero)."""
    return load_ds.parse_value(raw)


def store(data_dir: Path, kind: Kind) -> Store:
    return Store(data_dir, namespace=kind.namespace, schema=SCHEMA, identity=kind.identity)


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

    def apply(self, documents: list[Document], kind: Kind) -> list[Document]:
        if self.publish_dates:
            chosen = [d for d in documents if d.publish_time_raw[:10] in self.publish_dates]
            missing = sorted(set(self.publish_dates) - {d.publish_time_raw[:10] for d in chosen})
            if missing:
                raise UnavailableError(
                    f"no public {kind.dataset} {kind.document_kind} CSV published on {missing}; "
                    f"ERCOT's public list keeps about {PUBLIC_RETENTION_DAYS} days"
                )
            if len(chosen) > MAX_DOCUMENTS_PER_RUN:
                raise SelectionError(
                    f"{len(chosen)} documents match; the per-run limit is {MAX_DOCUMENTS_PER_RUN}"
                )
            return chosen
        return documents[-self.latest :]

    def describe(self, kind: Kind) -> dict:
        n = self.latest or len(self.publish_dates)
        return {
            "source": f"ERCOT {kind.dataset} '{kind.report_name}' (report type "
            f"{kind.report_type_id}), document kind {kind.document_kind}",
            "access": "ercot.com public report listing + document download (no login)",
            "selection": (
                f"documents published on {list(self.publish_dates)}"
                if self.publish_dates
                else f"latest {self.latest} {kind.document_kind} CSV document(s) in the list"
            ),
            "stored_scope": f"{LOCATION} only; every other settlement point in each downloaded "
            "document is discarded after validation. The report's other document kinds (LMP, "
            "ancillary, shadow price) are never downloaded.",
            "downloaded_scope": f"{n} whole document(s); sizes vary, up to about 760 KB zipped",
            "request_budget": f"1 list request + up to {n} downloads, plus at most 2 retries "
            "each; 1 s pause between requests",
            "credential": "none (public download); EIA_API_KEY is never used",
        }


def normalize(document, parsed: Parsed, kind: Kind, *, run_id, archive, retrieved_at) -> list[dict]:
    published = load_ds.parse_publish_time(document.publish_time_raw)
    records = []
    for row in parsed.rows:
        original, flags_o = parse_price(row.original_raw)
        corrected, flags_c = parse_price(row.corrected_raw)
        flags = [f"original_{f}" for f in flags_o] + [f"corrected_{f}" for f in flags_c]
        records.append(
            {
                "source": SOURCE,
                "dataset": kind.dataset,
                "report_type_id": kind.report_type_id,
                "market_stage": kind.market_stage,
                "location": LOCATION,
                "location_type": row.location_type,
                "entity": LOCATION,
                "metric": METRIC,
                "doc_id": document.doc_id,
                "doc_name": document.name,
                "publish_time_raw": document.publish_time_raw,
                "publication_time_utc": published,
                "delivery_date_raw": row.delivery_date_raw,
                "delivery_date": row.delivery_date,
                "delivery_hour": row.delivery_hour,
                "delivery_interval": row.delivery_interval,
                "dst_flag": row.dst_flag,
                "correction_time_raw": row.correction_time_raw,
                "row_order": row.row_order,
                "original_raw": row.original_raw.strip() or None,
                "original_value": original,
                "corrected_raw": row.corrected_raw.strip() or None,
                "corrected_value": corrected,
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


def assign_revisions(target: Store, records: list[dict], kind: Kind) -> tuple[list[dict], dict]:
    """A re-posted correction event with changed prices becomes revision n + 1."""
    counts = {"rows_new": 0, "rows_revised": 0, "rows_unchanged": 0}
    if not records:
        return [], counts
    columns = ", ".join(kind.identity)
    with target.query() as con:
        rows = con.execute(
            f"SELECT {columns}, original_raw, corrected_raw, revision FROM latest "
            "WHERE list_contains(?, delivery_date_raw)",
            [sorted({r["delivery_date_raw"] for r in records})],
        ).fetchall()
    n = len(kind.identity)
    latest = {tuple(r[:n]): (r[n], r[n + 1], r[n + 2]) for r in rows}
    keep = []
    for record in records:
        key = tuple(record[c] for c in kind.identity)
        previous = latest.get(key)
        if previous is None:
            record["revision"] = 1
            counts["rows_new"] += 1
        elif (previous[0], previous[1]) == (record["original_raw"], record["corrected_raw"]):
            counts["rows_unchanged"] += 1
            continue
        else:
            record["revision"] = previous[2] + 1
            counts["rows_revised"] += 1
        latest[key] = (record["original_raw"], record["corrected_raw"], record["revision"])
        keep.append(record)
    return keep, counts


def collect(kind: Kind, selection: Selection, client: ErcotClient, target: Store) -> dict:
    """One bounded collection under the store's writer lock."""
    with target.writer_lock():
        run_id = target.start_run(
            entity=LOCATION,
            metrics=f"{kind.market_stage} {METRIC}",
            request_start=",".join(selection.publish_dates) or f"latest {selection.latest}",
            request_end=None,
            lookback_days=0,
        )
        try:
            listed = client.list_documents(kind.report)
            if not listed:
                raise UnavailableError(
                    f"no {kind.dataset} {kind.document_kind} CSV documents are listed; the "
                    "report's file naming may have changed"
                )
            chosen = selection.apply(listed, kind)
            files, records, documents = [], [], []
            for document in chosen:  # oldest first, so a repost becomes the later revision
                body, csv_bytes, member = client.download_csv(document, kind.report)
                parsed = parse_csv(csv_bytes, kind)
                record = target.write_raw(run_id, 0, body, False, name=f"{document.doc_id}.zip")
                files.append(record)
                records += normalize(
                    document,
                    parsed,
                    kind,
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
            keep, counts = assign_revisions(target, records, kind)
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
        except (ErcotError, CorrectionFormatError, SelectionError) as exc:
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
