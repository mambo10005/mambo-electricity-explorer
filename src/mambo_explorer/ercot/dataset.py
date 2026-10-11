"""Dataset contract for ERCOT NP6-345-CD, "Actual System Load by Weather Zone".

Every fact here is backed by docs/source-register.md (ERCOT NP6-345-CD review,
2026-10-11). Unverified points are explicit and are never filled in by assumption:
- units: not stated in the file, the EMIL entry, or the XSD, so stored as unknown
- time zone of OperDay/HourEnding: not stated; labels are kept raw, never converted to UTC
- the DST repeated and missing hours: representation not yet observed, so rows are kept
  exactly as sent; nothing is deduplicated across DSTFlag and no hour is invented
- the TOTAL definition: provided by ERCOT, not documented as the zone sum; the
  difference is recorded as a diagnostic, never used to change values
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pyarrow as pa

SOURCE = "ERCOT"
DATASET = "NP6-345-CD"
REPORT_TYPE_ID = "13101"
REPORT_NAME = "Actual System Load by Weather Zone"
PRODUCT_PAGE = "https://www.ercot.com/mp/data-products/data-product-details?id=NP6-345-CD"
LIST_URL = f"https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId={REPORT_TYPE_ID}"
DOWNLOAD_URL = "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId={doc_id}"
CSV_FRIENDLY_NAME = "ACTUALSYSLOADWZNP6345_csv"
STORE_NAMESPACE = "ercot-np6-345-cd"
PUBLIC_RETENTION_DAYS = 31  # EMIL "Display Duration"

ZONES = ("COAST", "EAST", "FAR_WEST", "NORTH", "NORTH_C", "SOUTHERN", "SOUTH_C", "WEST")
TOTAL = "TOTAL"
HEADER = ("OperDay", "HourEnding", *ZONES, TOTAL, "DSTFlag")
METRIC = "actual_load"
UNIT = "not stated by source"
UNIT_TEXT = (
    "Not stated by ERCOT in the file, the report listing (EMIL), or the schema (XSD). ERCOT "
    "load reports are commonly read as MW, but this app does not assume it."
)
TIME_TEXT = (
    "OperDay and HourEnding are shown exactly as ERCOT writes them (e.g. '10/10/2026', "
    "'01:00' … '24:00') with ERCOT's DSTFlag. The file does not state a time zone, so the "
    "labels are not converted to UTC. Publication time comes from ERCOT's document listing "
    "and includes a UTC offset."
)
ZONE_NAMES = {
    "COAST": "Coast",
    "EAST": "East",
    "FAR_WEST": "Far West",
    "NORTH": "North",
    "NORTH_C": "North Central",
    "SOUTHERN": "Southern",
    "SOUTH_C": "South Central",
    "WEST": "West",
    "TOTAL": "ERCOT total (as provided by ERCOT)",
}

_OPER_DAY = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_HOUR_ENDING = re.compile(r"(\d{2}):(\d{2})")

SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("dataset", pa.string()),
        ("report_type_id", pa.string()),
        ("doc_id", pa.string()),
        ("doc_name", pa.string()),
        ("publish_time_raw", pa.string()),
        ("publication_time_utc", pa.timestamp("us", tz="UTC")),
        ("oper_day", pa.string()),
        ("oper_date", pa.date32()),
        ("hour_ending", pa.string()),
        ("dst_flag", pa.string()),
        ("row_order", pa.int32()),
        ("entity", pa.string()),
        ("metric", pa.string()),
        ("value_raw", pa.string()),
        ("value", pa.float64()),
        ("unit", pa.string()),
        ("quality_flags", pa.string()),
        ("zone_sum_minus_total", pa.float64()),
        ("revision", pa.int32()),
        ("retrieved_at_utc", pa.timestamp("us", tz="UTC")),
        ("run_id", pa.string()),
        ("archive_path", pa.string()),
        ("archive_sha256", pa.string()),
    ]
)
# DSTFlag is part of the identity, so a repeated fall-back hour (if ERCOT sends one with a
# different flag) is a distinct observation, never collapsed into its twin.
IDENTITY = ("source", "dataset", "entity", "metric", "oper_day", "hour_ending", "dst_flag")


class ReportFormatError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedRow:
    oper_day: str
    oper_date: date
    hour_ending: str
    dst_flag: str
    row_order: int
    values: dict[str, str]  # column -> raw text exactly as in the file


def parse_publish_time(text: str) -> datetime:
    """ERCOT listing PublishDate, e.g. 2026-10-11T05:50:00-05:00 (offset is explicit)."""
    try:
        stamp = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        raise ReportFormatError(f"unparseable PublishDate {text!r}") from None
    if stamp.tzinfo is None:
        raise ReportFormatError(f"PublishDate {text!r} has no UTC offset")
    return stamp.astimezone(UTC)


def parse_value(raw: str) -> tuple[float | None, list[str]]:
    text = raw.strip()
    if text == "":
        return None, ["missing"]
    try:
        value = float(text)
    except ValueError:
        return None, ["non_numeric"]
    return value, (["negative"] if value < 0 else [])


def parse_csv(data: bytes) -> list[ParsedRow]:
    """Strictly parse one report CSV. Any schema or format surprise raises."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ReportFormatError("CSV is not UTF-8") from None
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = tuple(h.strip() for h in next(reader))
    except StopIteration:
        raise ReportFormatError("CSV is empty") from None
    if header != HEADER:
        missing = [h for h in HEADER if h not in header]
        extra = [h for h in header if h not in HEADER]
        raise ReportFormatError(
            f"unexpected header (missing {missing}, extra {extra}, order "
            f"{'differs' if not missing and not extra else 'n/a'}); the report schema may "
            "have changed — update the dataset contract after review"
        )
    rows: list[ParsedRow] = []
    seen: set[tuple[str, str, str]] = set()
    for line_no, fields in enumerate(reader, start=2):
        if not fields or all(not f.strip() for f in fields):
            continue
        if len(fields) != len(HEADER):
            raise ReportFormatError(f"line {line_no}: {len(fields)} fields, expected {len(HEADER)}")
        record = dict(zip(HEADER, (f.strip() for f in fields), strict=True))
        day = _OPER_DAY.fullmatch(record["OperDay"])
        if not day:
            raise ReportFormatError(f"line {line_no}: bad OperDay {record['OperDay']!r}")
        try:
            oper_date = date(int(day[3]), int(day[1]), int(day[2]))
        except ValueError:
            raise ReportFormatError(f"line {line_no}: invalid date {record['OperDay']!r}") from None
        hour = _HOUR_ENDING.fullmatch(record["HourEnding"])
        if not hour or not 1 <= int(hour[1]) <= 24 or hour[2] != "00":
            raise ReportFormatError(f"line {line_no}: bad HourEnding {record['HourEnding']!r}")
        if record["DSTFlag"] not in ("Y", "N"):
            raise ReportFormatError(f"line {line_no}: bad DSTFlag {record['DSTFlag']!r}")
        key = (record["OperDay"], record["HourEnding"], record["DSTFlag"])
        if key in seen:
            raise ReportFormatError(f"line {line_no}: duplicate row for {key}")
        seen.add(key)
        rows.append(
            ParsedRow(
                record["OperDay"],
                oper_date,
                record["HourEnding"],
                record["DSTFlag"],
                len(rows),
                {c: record[c] for c in (*ZONES, TOTAL)},
            )
        )
    if not rows:
        raise ReportFormatError("CSV has a header but no data rows")
    if len({r.oper_day for r in rows}) != 1:
        raise ReportFormatError("CSV contains more than one OperDay")
    if len(rows) > 25:
        raise ReportFormatError(f"{len(rows)} hourly rows for one day (max 25 on a DST day)")
    return rows


def zone_sum_minus_total(values: dict[str, str]) -> float | None:
    """Diagnostic only: sum of zone values minus the provided TOTAL (None if any missing)."""
    parsed = [parse_value(values[z])[0] for z in ZONES]
    total = parse_value(values[TOTAL])[0]
    if total is None or any(v is None for v in parsed):
        return None
    return round(sum(parsed) - total, 6)
