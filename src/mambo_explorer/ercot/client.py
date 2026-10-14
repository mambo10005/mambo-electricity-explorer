"""Bounded client for ERCOT's public report listing and document download (no login).

Uses the two URLs that ERCOT's official NP6-345-CD product page uses: the JSON document
list and the document download. ERCOT does not publish them as a developer API, so
every response is validated and any change fails loudly. There is no fallback to HTML
scraping or to another source.

No credentials are used or accepted. In particular this client never reads EIA_API_KEY.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from mambo_explorer.ercot import dataset as ds
from mambo_explorer.safe_zip import ArchiveError, Limits, read_members

USER_AGENT = "mambo-electricity-explorer/0.1 (local educational collector; low volume)"
MAX_LIST_BYTES = 1_000_000
ZIP_LIMITS = Limits(
    max_archive_bytes=500_000,
    max_members=1,
    max_member_bytes=200_000,
    max_total_bytes=200_000,
    allowed_suffixes=(".csv",),
)

# (status, content_type, body)
Transport = Callable[[str, float], tuple[int, str, bytes]]


class ErcotError(Exception):
    pass


class AccessError(ErcotError):
    """The public endpoint refused access (e.g. 401/403)."""


class UnavailableError(ErcotError):
    """The requested report document is not in the public listing (or has expired)."""


class ResponseError(ErcotError):
    pass


class BudgetExceeded(ErcotError):
    pass


def urllib_transport(url: str, timeout: float) -> tuple[int, str, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (
                response.status,
                response.headers.get("Content-Type", ""),
                response.read(MAX_LIST_BYTES + 1),
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", "") if exc.headers else "", exc.read(2000)


@dataclass(frozen=True)
class Report:
    """One ERCOT public report this client may list and download (reviewed in the register)."""

    report_type_id: str
    csv_friendly_name: str
    label: str
    limits: Limits
    # Reports with one document per interval give each document its own FriendlyName
    # (e.g. SPPHLZNP6905_20261013_0015_csv); a full-match regex selects their CSV twins.
    csv_name_pattern: str | None = None

    def is_csv(self, friendly_name: str) -> bool:
        if self.csv_name_pattern:
            return re.fullmatch(self.csv_name_pattern, friendly_name) is not None
        return friendly_name == self.csv_friendly_name


LOAD_REPORT = Report(ds.REPORT_TYPE_ID, ds.CSV_FRIENDLY_NAME, ds.DATASET, ZIP_LIMITS)
LIST_URL_TEMPLATE = "https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId={id}"


@dataclass(frozen=True)
class Document:
    doc_id: str
    name: str
    publish_time_raw: str
    content_size: int
    friendly_name: str = ""


@dataclass
class Stats:
    """Every HTTP attempt counts as a request, including retries; `by_kind` splits the same
    attempts into listings and document downloads, so the parts always add up to `requests`."""

    requests: int = 0
    retries: int = 0
    failures: list[str] = field(default_factory=list)
    by_kind: dict[str, int] = field(default_factory=dict)

    def breakdown(self) -> dict:
        return {
            "list": self.by_kind.get("list", 0),
            "download": self.by_kind.get("download", 0),
            "other": self.requests - self.by_kind.get("list", 0) - self.by_kind.get("download", 0),
            "retries_included": self.retries,
            "total": self.requests,
        }


class ErcotClient:
    def __init__(
        self,
        *,
        transport: Transport = urllib_transport,
        timeout: float = 30.0,
        max_retries: int = 2,
        backoff_seconds: float = 5.0,
        max_requests: int = 10,
        pause_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.max_requests = max_requests
        self.pause_seconds = pause_seconds
        self._sleep = sleep
        self.stats = Stats()

    def _get(self, url: str, what: str, kind: str = "other") -> tuple[str, bytes]:
        for attempt in range(self.max_retries + 1):
            if self.stats.requests >= self.max_requests:
                raise BudgetExceeded(f"request budget of {self.max_requests} exhausted")
            if self.stats.requests:
                self._sleep(self.pause_seconds)  # be gentle with ERCOT (Terms of Use §6)
            self.stats.requests += 1
            self.stats.by_kind[kind] = self.stats.by_kind.get(kind, 0) + 1
            try:
                status, content_type, body = self._transport(url, self.timeout)
            except (OSError, urllib.error.URLError) as exc:
                retryable, message = True, f"network error fetching {what}: {type(exc).__name__}"
            else:
                if status == 200:
                    return content_type, body
                if status in (401, 403):
                    raise AccessError(
                        f"ERCOT refused access to {what} (HTTP {status}). The public download "
                        "may now require an account; this app will not register or accept "
                        "terms automatically."
                    )
                if status == 404:
                    raise UnavailableError(f"{what} not found (HTTP 404); it may have expired")
                retryable = status == 429 or status >= 500
                message = f"HTTP {status} fetching {what}"
            self.stats.failures.append(message)
            if not retryable or attempt == self.max_retries:
                raise ResponseError(message)
            self.stats.retries += 1
            self._sleep(self.backoff_seconds * 2**attempt)
        raise AssertionError("unreachable")

    def list_documents(self, report: Report = LOAD_REPORT) -> list[Document]:
        """Public CSV documents for `report`, oldest first (validated)."""
        url = LIST_URL_TEMPLATE.format(id=report.report_type_id)
        content_type, body = self._get(url, f"the {report.label} document list", "list")
        if len(body) > MAX_LIST_BYTES:
            raise ResponseError("document list exceeds size limit")
        if "html" in content_type.lower():
            raise ResponseError(f"document list returned {content_type!r}, not JSON")
        try:
            payload = json.loads(body.decode("utf-8"))
            entries = payload["ListDocsByRptTypeRes"]["DocumentList"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            raise ResponseError("document list is not the expected JSON structure") from None
        if not isinstance(entries, list):
            raise ResponseError("DocumentList is not a list")
        documents = []
        for entry in entries:
            doc = entry.get("Document") if isinstance(entry, dict) else None
            if not isinstance(doc, dict):
                raise ResponseError("DocumentList entry without a Document object")
            if not report.is_csv(str(doc.get("FriendlyName", ""))):
                continue  # XML twin of each document; only CSV is used
            if doc.get("ReportTypeID") != report.report_type_id or doc.get("SecurityStatus") != "P":
                raise ResponseError(f"unexpected document metadata for {doc.get('DocID')!r}")
            doc_id = str(doc.get("DocID", ""))
            if not doc_id.isdigit():
                raise ResponseError(f"invalid DocID {doc_id!r}")
            ds.parse_publish_time(str(doc.get("PublishDate")))  # validates offset
            try:
                size = int(doc.get("ContentSize", "0"))
            except ValueError:
                raise ResponseError(f"invalid ContentSize for {doc_id}") from None
            documents.append(
                Document(
                    doc_id,
                    str(doc.get("ConstructedName", "")),
                    str(doc["PublishDate"]),
                    size,
                    str(doc.get("FriendlyName", "")),
                )
            )
        return sorted(
            documents, key=lambda d: (ds.parse_publish_time(d.publish_time_raw), d.doc_id)
        )

    def download_csv(
        self, document: Document, report: Report = LOAD_REPORT
    ) -> tuple[bytes, bytes, str]:
        """(zip bytes as received, CSV member bytes, member name). Nothing touches disk."""
        if document.content_size > report.limits.max_archive_bytes:
            raise ResponseError(
                f"document {document.doc_id} declares {document.content_size} bytes"
            )
        content_type, body = self._get(
            ds.DOWNLOAD_URL.format(doc_id=document.doc_id),
            f"document {document.doc_id}",
            "download",
        )
        if "html" in content_type.lower() or not body.startswith(b"PK\x03\x04"):
            raise ResponseError(f"document {document.doc_id} is not a ZIP ({content_type!r})")
        try:
            members = read_members(body, report.limits)
        except ArchiveError as exc:
            raise ResponseError(f"document {document.doc_id}: {exc}") from None
        ((name, data),) = members.items()
        return body, data, name
