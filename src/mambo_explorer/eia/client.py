"""Bounded EIA API v2 client.

Every message that leaves this module (exceptions, stats, archived bodies) is passed
through redact(). Authenticated URLs are built only inside _get() and are never
stored, logged, or included in errors.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode

from mambo_explorer.eia import dataset as ds
from mambo_explorer.eia.redact import redact, redact_bytes

BASE_URL = "https://api.eia.gov/v2/"
MAX_BODY_BYTES = 20_000_000
USER_AGENT = "mambo-electricity-explorer/0.1 (local educational collector)"

Transport = Callable[[str, float], tuple[int, bytes]]


class EIAError(Exception):
    """Base error. Messages are always redacted before construction."""


class CredentialError(EIAError):
    pass


class SourceError(EIAError):
    pass


class ResponseValidationError(EIAError):
    pass


class PaginationError(ResponseValidationError):
    pass


class BudgetExceeded(EIAError):
    pass


def urllib_transport(url: str, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_BODY_BYTES + 1)


@dataclass
class RequestStats:
    requests: int = 0
    retries: int = 0
    pages: int = 0
    failures: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Page:
    offset: int
    body: bytes  # sanitized bytes, safe to archive
    sanitized: bool
    rows: list[dict]


class EIAClient:
    def __init__(
        self,
        api_key: str | None,
        *,
        transport: Transport = urllib_transport,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 2.0,
        max_requests: int = 20,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise CredentialError(
                "EIA_API_KEY is not set. Request a free key from EIA and set it in your "
                "environment or in a gitignored .env file (see README)."
            )
        self._key = api_key
        self._transport = transport
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.max_requests = max_requests
        self._sleep = sleep
        self.stats = RequestStats()

    def __repr__(self) -> str:
        return f"EIAClient(max_requests={self.max_requests}, timeout={self.timeout})"

    def _clean(self, text: str) -> str:
        return redact(text, [self._key])

    def _get(self, path: str, params: list[tuple[str, str]]) -> tuple[dict, bytes, bool]:
        query = urlencode([*params, ("api_key", self._key)])
        url = f"{BASE_URL}{path}?{query}"
        safe_path = self._clean(path)
        for attempt in range(self.max_retries + 1):
            if self.stats.requests >= self.max_requests:
                raise BudgetExceeded(
                    f"request budget of {self.max_requests} exhausted "
                    f"({self.stats.requests} requests, {self.stats.retries} retries)"
                )
            self.stats.requests += 1
            try:
                status, body = self._transport(url, self.timeout)
            except (OSError, urllib.error.URLError) as exc:  # includes timeouts
                reason = self._clean(f"{type(exc).__name__}: {exc}")
                retryable, message = True, f"network error on {safe_path}: {reason}"
            else:
                if len(body) > MAX_BODY_BYTES:
                    raise SourceError(f"response from {safe_path} exceeded {MAX_BODY_BYTES} bytes")
                if status == 200:
                    return self._parse(safe_path, body)
                snippet = self._clean(body[:300].decode("utf-8", "replace"))
                if status in (401, 403):
                    raise CredentialError(f"EIA rejected the API key (HTTP {status}): {snippet}")
                retryable = status == 429 or status >= 500
                message = f"HTTP {status} from {safe_path}: {snippet}"
            self.stats.failures.append(message)
            if not retryable or attempt == self.max_retries:
                raise SourceError(message)
            self.stats.retries += 1
            self._sleep(self.backoff_seconds * 2**attempt)
        raise AssertionError("unreachable")

    def _parse(self, safe_path: str, body: bytes) -> tuple[dict, bytes, bool]:
        try:
            clean_body, sanitized = redact_bytes(body, [self._key])
            payload = json.loads(clean_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            # from None: the original exception can hold the unredacted body bytes.
            raise ResponseValidationError(
                f"{safe_path}: response is not valid JSON ({type(exc).__name__})"
            ) from None
        if not isinstance(payload, dict):
            raise ResponseValidationError(f"{safe_path}: top-level JSON is not an object")
        if "error" in payload:
            raise SourceError(f"{safe_path}: EIA error: {self._clean(str(payload['error']))[:300]}")
        if not isinstance(payload.get("response"), dict):
            raise ResponseValidationError(f"{safe_path}: missing 'response' object")
        return payload, clean_body, sanitized

    # --- metadata discovery -------------------------------------------------------

    def route_metadata(self, route: str = ds.ROUTE) -> dict:
        payload, _, _ = self._get(f"{route}/", [])
        return payload["response"]

    def facet_values(self, facet: str, route: str = ds.ROUTE) -> list[dict]:
        payload, _, _ = self._get(f"{route}/facet/{facet}/", [])
        values = payload["response"].get("facets")
        if not isinstance(values, list):
            raise ResponseValidationError(f"facet {facet}: missing 'facets' list")
        return values

    # --- bounded data query ---------------------------------------------------------

    def fetch_region_data(
        self,
        respondent: str,
        types: list[str],
        start_period: str,
        end_period: str,
        *,
        page_size: int = ds.MAX_ROWS_PER_REQUEST,
        max_rows: int,
    ) -> list[Page]:
        """Fetch all rows for one respondent and the given types, in deterministic order.

        Raises if pagination is truncated or inconsistent, if rows fall outside the
        requested scope, or if the total exceeds max_rows (scope guard).
        """
        if not 1 <= page_size <= ds.MAX_ROWS_PER_REQUEST:
            raise ValueError(f"page_size must be 1..{ds.MAX_ROWS_PER_REQUEST}")
        base = [
            ("frequency", ds.FREQUENCY),
            ("data[0]", "value"),
            ("facets[respondent][]", respondent),
            *[("facets[type][]", t) for t in sorted(types)],
            ("start", start_period),
            ("end", end_period),
            *ds.SORT_PARAMS,
        ]
        pages: list[Page] = []
        offset, total = 0, None
        while True:
            params = [*base, ("offset", str(offset)), ("length", str(page_size))]
            payload, body, sanitized = self._get(f"{ds.ROUTE}/data/", params)
            self.stats.pages += 1
            response = payload["response"]
            page_total = _int(response.get("total"), "response.total")
            if total is None:
                total = page_total
                if total > max_rows:
                    raise ResponseValidationError(
                        f"source reports {total} rows, above the expected maximum {max_rows}"
                    )
            elif page_total != total:
                raise PaginationError(f"total changed during pagination ({total} -> {page_total})")
            rows = response.get("data")
            if not isinstance(rows, list):
                raise ResponseValidationError("response.data is not a list")
            for row in rows:
                validate_row(row, respondent, set(types), start_period, end_period)
            pages.append(Page(offset=offset, body=body, sanitized=sanitized, rows=rows))
            received = offset + len(rows)
            if received >= total:
                break
            if len(rows) < page_size:
                raise PaginationError(
                    f"page at offset {offset} returned {len(rows)} of {page_size} rows "
                    f"before reaching total {total}"
                )
            offset = received
        all_rows = [row for page in pages for row in page.rows]
        if len(all_rows) != total:
            raise PaginationError(f"received {len(all_rows)} rows but source reported {total}")
        keys = [(r["period"], r["respondent"], r["type"]) for r in all_rows]
        if keys != sorted(keys):
            raise ResponseValidationError("rows are not in the requested deterministic order")
        if len(set(keys)) != len(keys):
            raise ResponseValidationError("duplicate (period, respondent, type) rows in response")
        return pages


_PERIOD = re.compile(ds.PERIOD_PATTERN)


def validate_row(row: object, respondent: str, types: set[str], start: str, end: str) -> None:
    if not isinstance(row, dict):
        raise ResponseValidationError("data row is not an object")
    missing = [f for f in ds.REQUIRED_FIELDS if f not in row]
    if missing:
        raise ResponseValidationError(f"data row missing fields {missing}")
    period = row["period"]
    if not isinstance(period, str) or not _PERIOD.fullmatch(period):
        raise ResponseValidationError(f"unexpected period format {period!r}")
    if not start <= period <= end:
        raise ResponseValidationError(f"period {period} outside requested window {start}..{end}")
    if row["respondent"] != respondent:
        raise ResponseValidationError(f"unexpected respondent {row['respondent']!r}")
    if row["type"] not in types:
        raise ResponseValidationError(f"unexpected type {row['type']!r}")
    value = row["value"]
    if value is not None and not isinstance(value, (int, float, str)) or isinstance(value, bool):
        raise ResponseValidationError(f"unexpected value type {type(value).__name__}")
    if not isinstance(row[ds.UNITS_FIELD], str):
        raise ResponseValidationError("units field is not a string")


def _int(value: object, name: str) -> int:
    try:
        number = int(str(value))
    except ValueError:
        raise ResponseValidationError(f"{name} is not an integer: {value!r}") from None
    if number < 0:
        raise ResponseValidationError(f"{name} is negative")
    return number
