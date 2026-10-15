"""SYNTHETIC ERCOT NP6-345-CD fixtures for offline tests.

The structure follows the 2026-10-11 source review (header, listing JSON layout, ZIP with
one CSV member). Every value is made up. No ERCOT file is copied here; committing actual
ERCOT files is deferred until publication permission is reviewed.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date

from mambo_explorer.ercot import dataset as ds

BASE = {
    "COAST": 13000.0,
    "EAST": 1600.0,
    "FAR_WEST": 7500.0,
    "NORTH": 1350.0,
    "NORTH_C": 13500.0,
    "SOUTHERN": 4400.0,
    "SOUTH_C": 8000.0,
    "WEST": 1850.0,
}


def rows_for(day: date, *, hours=None, dst=None, overrides=None, total_offset=0.0):
    """CSV data rows for one OperDay. hours: list of 'HH:00'; dst: dict hour->flag list."""
    hours = hours or [f"{h:02d}:00" for h in range(1, 25)]
    overrides = overrides or {}
    lines = []
    for hour in hours:
        for flag in (dst or {}).get(hour, ["N"]):
            h = int(hour[:2])
            zones = {z: round(v + h * 10 + (5 if flag == "Y" else 0), 2) for z, v in BASE.items()}
            values = {z: f"{zones[z]:.2f}" for z in ds.ZONES}
            values["TOTAL"] = f"{sum(zones.values()) + total_offset:.2f}"
            values.update(overrides.get((hour, flag), {}))
            lines.append(
                [
                    day.strftime("%m/%d/%Y"),
                    hour,
                    *(values[z] for z in ds.ZONES),
                    values["TOTAL"],
                    flag,
                ]
            )
    return lines


def csv_bytes(lines, header=ds.HEADER) -> bytes:
    text = ",".join(header) + "\n" + "\n".join(",".join(line) for line in lines) + "\n"
    return text.encode("utf-8")


def zip_bytes(
    csv: bytes, member="cdr.00013101.0000000000000000.20261011.055000.ACTUALSYSLOADWZNP6345.csv"
):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, csv)
    return buffer.getvalue()


def document(
    doc_id: str,
    published: str,
    size: int = 1500,
    friendly=ds.CSV_FRIENDLY_NAME,
    security="P",
    report=ds.REPORT_TYPE_ID,
) -> dict:
    return {
        "Document": {
            "ExpiredDate": "2026-11-11T23:59:59-06:00",
            "ILMStatus": "EXT",
            "SecurityStatus": security,
            "ContentSize": str(size),
            "Extension": "zip",
            "ReportTypeID": report,
            "Prefix": "cdr",
            "FriendlyName": friendly,
            "ConstructedName": f"cdr.00013101.0000000000000000.{published[:10].replace('-', '')}"
            f".055000448.{friendly}.zip",
            "DocID": doc_id,
            "PublishDate": published,
            "ReportName": ds.REPORT_NAME,
            "DUNS": "0000000000000000",
            "DocCount": "0",
        }
    }


def listing(documents: list[dict]) -> bytes:
    return json.dumps({"ListDocsByRptTypeRes": {"DocumentList": documents}}).encode("utf-8")


class FakeErcot:
    """Serves a listing and document ZIPs by DocID. script: responses to emit first."""

    def __init__(self, docs: dict[str, tuple[str, bytes]], *, script=None, extra_listing=()):
        self.docs = docs  # doc_id -> (publish date, zip bytes)
        self.script = list(script or [])
        self.extra_listing = list(extra_listing)
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float):
        self.urls.append(url)
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if url == ds.LIST_URL:
            docs = [document(i, pub, len(z)) for i, (pub, z) in self.docs.items()]
            docs += [
                document(f"9{i}", pub, friendly="ACTUALSYSLOADWZNP6345_xml")
                for i, (pub, _) in self.docs.items()
            ]
            return 200, "application/json", listing(docs + self.extra_listing)
        doc_id = url.rsplit("=", 1)[1]
        if doc_id not in self.docs:
            return 404, "text/html", b"<html>not found</html>"
        return 200, "application/zip", self.docs[doc_id][1]


def day_doc(day: date, doc_id: str, published: str, **kw) -> tuple[str, tuple[str, bytes]]:
    return doc_id, (published, zip_bytes(csv_bytes(rows_for(day, **kw))))
