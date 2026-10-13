"""SYNTHETIC ERCOT NP6-905-CD fixtures for offline tests (one 15-minute interval per document).

The structure follows the 2026-10-12 review (header, per-document FriendlyName, one CSV member
per ZIP, every settlement point in one interval). Every price is made up.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date

from mambo_explorer.ercot import rt_prices as rt

OTHERS = (("HB_SOUTH", "HU"), ("LZ_NORTH", "LZ"), ("A4_DGR1_RN", "RN"))
LIST_URL = (
    f"https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId={rt.REPORT_TYPE_ID}"
)


def synthetic_price(hour: int, interval: int) -> str:
    """Synthetic: a negative pre-dawn hour, otherwise rising through the day."""
    if hour == 4:
        return f"{-3.0 - interval:.2f}"
    return f"{20 + hour * 1.25 + interval * 0.25:.2f}"


def csv_for(day: date, hour: int, interval: int, *, dst="N", price=None, ptype="HU", extra=()):
    label = day.strftime("%m/%d/%Y")
    north = synthetic_price(hour, interval) if price is None else price
    lines = [[label, str(hour), str(interval), rt.LOCATION, ptype, north, dst]]
    for name, kind in OTHERS:
        lines.append([label, str(hour), str(interval), name, kind, "25.00", dst])
    lines += [list(x) for x in extra]
    text = ",".join(rt.HEADER) + "\n" + "\n".join(",".join(x) for x in lines) + "\n"
    return text.encode("utf-8")


def zip_bytes(
    csv: bytes,
    member="cdr.00012301.0000000000000000.20261013.001701.SPPHLZNP6905_20261013_0015.csv",
):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, csv)
    return buffer.getvalue()


def interval_doc(
    day: date, hour: int, interval: int, doc_id: str, published: str | None = None, **kw
):
    """(doc_id, (publish time, friendly name, zip)) for one interval."""
    minute = interval * 15
    hh, mm = (hour - 1 + minute // 60), minute % 60
    friendly = f"SPPHLZNP6905_{day:%Y%m%d}_{hh:02d}{mm:02d}_csv"
    published = published or f"{day}T{min(hh, 23):02d}:{mm:02d}:02-05:00"
    return doc_id, (published, friendly, zip_bytes(csv_for(day, hour, interval, **kw)))


def day_docs(day: date, hours=range(1, 3), start_id=7000) -> dict:
    out, n = {}, start_id
    for h in hours:
        for i in range(1, 5):
            out.update(dict([interval_doc(day, h, i, str(n))]))
            n += 1
    return out


class FakeRt:
    """Serves the NP6-905-CD listing and ZIPs. docs: doc_id -> (publish time, friendly, zip)."""

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
            entries = []
            for doc_id, (pub, friendly, z) in self.docs.items():
                for name, did in (
                    (friendly, doc_id),
                    (friendly.replace("_csv", "_xml"), "9" + doc_id),
                ):
                    entries.append(
                        {
                            "Document": {
                                "SecurityStatus": "P",
                                "ContentSize": str(len(z)),
                                "Extension": "zip",
                                "ReportTypeID": rt.REPORT_TYPE_ID,
                                "FriendlyName": name,
                                "ConstructedName": f"cdr.00012301.0000000000000000.{name}.zip",
                                "DocID": did,
                                "PublishDate": pub,
                                "ReportName": rt.REPORT_NAME,
                            }
                        }
                    )
            return (
                200,
                "application/json",
                json.dumps({"ListDocsByRptTypeRes": {"DocumentList": entries}}).encode(),
            )
        doc_id = url.rsplit("=", 1)[1]
        if doc_id not in self.docs:
            return 404, "text/html", b"<html>not found</html>"
        return 200, "application/zip", self.docs[doc_id][2]
