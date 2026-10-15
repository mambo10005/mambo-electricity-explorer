"""SYNTHETIC ERCOT NP4-190-CD fixtures for offline tests.

The structure follows the 2026-10-12 review (header, listing JSON layout, one CSV member per
ZIP, every settlement point in one document). Every price is made up; no ERCOT file is
copied here.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date

from mambo_explorer.ercot import prices as px

# A few non-selected settlement points so location filtering is exercised.
OTHER_POINTS = ("HB_SOUTH", "HB_WEST", "LZ_NORTH", "A4_DGR1_RN")


def price(hour: int, base: float = 30.0) -> str:
    """Synthetic: a morning dip below zero and an evening peak."""
    if hour in (3, 4):
        return f"{-2.5 * (hour - 2):.2f}"
    return f"{base + (hour % 24) * 1.5:.2f}"


def rows_for(
    day: date,
    *,
    hours=None,
    overrides=None,
    dst=None,
    location: str = px.LOCATION,
    others=OTHER_POINTS,
):
    """CSV lines for one DeliveryDate. overrides: (hour_label, dst) -> raw text."""
    hours = hours or [f"{h:02d}:00" for h in range(1, 25)]
    dst = dst or {}
    overrides = overrides or {}
    label = day.strftime("%m/%d/%Y")
    lines = []
    for hour in hours:
        for flag in dst.get(hour, ["N"]):
            for point in sorted((location, *others)):
                raw = price(int(hour[:2]), 30.0 if point == location else 25.0)
                if point == location:
                    raw = overrides.get((hour, flag), raw)
                lines.append([label, hour, point, f" {raw}" if raw else "", flag])
    return lines


def csv_bytes(lines, header=px.HEADER) -> bytes:
    text = ",".join(header) + "\n" + "\n".join(",".join(line) for line in lines) + "\n"
    return text.encode("utf-8")


def zip_bytes(csv: bytes, member="cdr.00012331.0000000000000000.20261012.124627.DAMSPNP4190.csv"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, csv)
    return buffer.getvalue()


def document(doc_id, published, size=4000, friendly=px.CSV_FRIENDLY_NAME, report=px.REPORT_TYPE_ID):
    return {
        "Document": {
            "SecurityStatus": "P",
            "ContentSize": str(size),
            "Extension": "zip",
            "ReportTypeID": report,
            "FriendlyName": friendly,
            "ConstructedName": f"cdr.00012331.0000000000000000.{published[:10].replace('-', '')}"
            f".124627.{friendly}.zip",
            "DocID": doc_id,
            "PublishDate": published,
            "ReportName": px.REPORT_NAME,
        }
    }


LIST_URL = (
    f"https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId={px.REPORT_TYPE_ID}"
)


class FakePrices:
    """Serves the NP4-190-CD listing and ZIPs. docs: doc_id -> (publish time, zip bytes)."""

    def __init__(self, docs: dict, *, script=None):
        self.docs = docs
        self.script = list(script or [])
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float):
        self.urls.append(url)
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if url == LIST_URL:
            entries = [document(i, pub, len(z)) for i, (pub, z) in self.docs.items()]
            entries += [
                document(f"9{i}", pub, friendly="DAMSPNP4190_xml")
                for i, (pub, _) in self.docs.items()
            ]
            body = json.dumps({"ListDocsByRptTypeRes": {"DocumentList": entries}}).encode()
            return 200, "application/json", body
        if "reportTypeId=" in url:
            return 200, "application/json", b'{"ListDocsByRptTypeRes": {"DocumentList": []}}'
        doc_id = url.rsplit("=", 1)[1]
        if doc_id not in self.docs:
            return 404, "text/html", b"<html>not found</html>"
        return 200, "application/zip", self.docs[doc_id][1]


def day_doc(day: date, doc_id: str, published: str | None = None, **kw):
    """(doc_id, (publish time, zip)) for the DAM run that publishes `day`'s prices (day before)."""
    published = published or f"{date.fromordinal(day.toordinal() - 1)}T12:46:27-05:00"
    return doc_id, (published, zip_bytes(csv_bytes(rows_for(day, **kw))))


def docs_ending(last_day: date, count: int) -> dict:
    out = {}
    for i in range(count):
        day = date.fromordinal(last_day.toordinal() - (count - 1 - i))
        out.update(dict([day_doc(day, str(5000 + day.toordinal() % 1000))]))
    return out
