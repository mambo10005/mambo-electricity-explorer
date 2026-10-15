import json
import logging
import urllib.error
from datetime import date
from urllib.parse import parse_qsl, quote, quote_plus, urlsplit

import pytest
from eia_fixtures import FAKE_KEY, FakeEIA, response_body, synthetic_rows

from mambo_explorer.eia.client import (
    BudgetExceeded,
    CredentialError,
    EIAClient,
    PaginationError,
    ResponseValidationError,
    SourceError,
)
from mambo_explorer.eia.redact import MARK, redact

START, END = "2026-10-01T00", "2026-10-01T23"


def client(transport, **kw) -> EIAClient:
    return EIAClient(FAKE_KEY, transport=transport, sleep=lambda s: None, **kw)


def fetch(c, page_size=5000, max_rows=48):
    return c.fetch_region_data(
        "ERCO", ["D", "DF"], START, END, page_size=page_size, max_rows=max_rows
    )


def leaks(text: str) -> bool:
    return any(form in text for form in (FAKE_KEY, quote(FAKE_KEY, safe=""), quote_plus(FAKE_KEY)))


def test_missing_key_is_a_clear_error():
    with pytest.raises(CredentialError, match="EIA_API_KEY is not set"):
        EIAClient(None)


def test_paginates_with_small_page_size_and_deterministic_sort():
    fake = FakeEIA(synthetic_rows(date(2026, 10, 1), 1))
    c = client(fake)
    pages = fetch(c, page_size=10)
    assert [p.offset for p in pages] == [0, 10, 20, 30, 40]
    assert sum(len(p.rows) for p in pages) == 48
    assert c.stats.requests == 5 and c.stats.pages == 5 and c.stats.retries == 0
    params = parse_qsl(urlsplit(fake.urls[0]).query)
    assert ("sort[0][column]", "period") in params
    assert ("sort[1][column]", "respondent") in params
    assert ("sort[2][column]", "type") in params
    assert ("facets[respondent][]", "ERCO") in params


def test_truncated_page_is_rejected():
    rows = synthetic_rows(date(2026, 10, 1), 1)
    short = response_body(rows[:5], total=48)  # 5 rows returned for a 10-row page
    fake = FakeEIA(rows, script=[(200, response_body(rows[:10], total=48)), (200, short)])
    with pytest.raises(PaginationError, match="before reaching total"):
        fetch(client(fake), page_size=10)


def test_total_changing_during_pagination_is_rejected():
    rows = synthetic_rows(date(2026, 10, 1), 1)
    fake = FakeEIA(
        rows,
        script=[
            (200, response_body(rows[:10], total=48)),
            (200, response_body(rows[10:20], total=50)),
        ],
    )
    with pytest.raises(PaginationError, match="total changed"):
        fetch(client(fake), page_size=10)


def test_unsorted_rows_are_rejected():
    rows = synthetic_rows(date(2026, 10, 1), 1)
    rows[0], rows[2] = rows[2], rows[0]
    with pytest.raises(ResponseValidationError, match="deterministic order"):
        fetch(client(FakeEIA(rows)))


def test_duplicate_rows_are_rejected():
    rows = synthetic_rows(date(2026, 10, 1), 1)
    rows.insert(1, dict(rows[0]))
    with pytest.raises(ResponseValidationError, match="duplicate"):
        fetch(client(FakeEIA(rows)), max_rows=60)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: r.pop("value-units"), "missing fields"),
        (lambda r: r.update(period="2026/10/01 00"), "period format"),
        (lambda r: r.update(period="2026-09-30T23"), "outside requested window"),
        (lambda r: r.update(respondent="CISO"), "unexpected respondent"),
        (lambda r: r.update(type="NG"), "unexpected type"),
        (lambda r: r.update(value={"x": 1}), "unexpected value type"),
    ],
)
def test_malformed_rows_are_rejected(mutate, message):
    rows = synthetic_rows(date(2026, 10, 1), 1)
    mutate(rows[0])
    with pytest.raises(ResponseValidationError, match=message):
        fetch(client(FakeEIA(rows)))


@pytest.mark.parametrize(
    "body, error",
    [
        (b"<html>not json</html>", "not valid JSON"),
        (b"[1, 2]", "not an object"),
        (b'{"data": []}', "missing 'response'"),
        (json.dumps({"error": "invalid facet"}).encode(), "EIA error"),
        (json.dumps({"response": {"total": "x", "data": []}}).encode(), "not an integer"),
        (json.dumps({"response": {"total": "2", "data": "nope"}}).encode(), "not a list"),
    ],
)
def test_successful_status_with_invalid_payload_is_rejected(body, error):
    with pytest.raises((ResponseValidationError, SourceError), match=error):
        fetch(client(FakeEIA([], script=[(200, body)])))


def test_scope_guard_rejects_more_rows_than_expected():
    rows = synthetic_rows(date(2026, 10, 1), 1)
    with pytest.raises(ResponseValidationError, match="above the expected maximum"):
        fetch(client(FakeEIA(rows)), max_rows=47)


def test_retries_are_bounded_and_counted():
    rows = synthetic_rows(date(2026, 10, 1), 1)
    fake = FakeEIA(rows, script=[(503, b"busy"), TimeoutError("timed out"), (429, b"slow down")])
    c = client(fake, max_retries=3)
    fetch(c)
    assert c.stats.requests == 4 and c.stats.retries == 3
    assert len(c.stats.failures) == 3


def test_retries_exhausted_raises_source_error():
    fake = FakeEIA([], script=[(500, b"x")] * 3)
    c = client(fake, max_retries=2)
    with pytest.raises(SourceError, match="HTTP 500"):
        fetch(c)
    assert c.stats.requests == 3


def test_non_retryable_status_fails_immediately():
    c = client(FakeEIA([], script=[(400, b"bad request")]))
    with pytest.raises(SourceError, match="HTTP 400"):
        fetch(c)
    assert c.stats.requests == 1


def test_request_budget_is_enforced():
    rows = synthetic_rows(date(2026, 10, 1), 1)
    c = client(FakeEIA(rows), max_requests=2)
    with pytest.raises(BudgetExceeded, match="budget of 2"):
        fetch(c, page_size=10)


# --- credential leakage ----------------------------------------------------------------


def test_redact_covers_raw_encoded_query_and_json_forms():
    text = (
        f"raw={FAKE_KEY} enc={quote(FAKE_KEY, safe='')} plus={quote_plus(FAKE_KEY)} "
        f"https://x/?a=1&api_key=other123&b=2 {json.dumps({'api_key': 'echoed-value'})}"
    )
    out = redact(text, [FAKE_KEY])
    assert not leaks(out)
    assert "other123" not in out and "echoed-value" not in out
    assert out.count(MARK) == 5


def test_credential_rejection_message_is_sanitized():
    body = f"Invalid api_key {FAKE_KEY} for url ?api_key={quote_plus(FAKE_KEY)}".encode()
    with pytest.raises(CredentialError) as info:
        fetch(client(FakeEIA([], script=[(403, body)])))
    assert not leaks(str(info.value))


def test_network_exception_message_is_sanitized():
    url_error = urllib.error.URLError(
        f"failed https://api.eia.gov/v2/x?api_key={quote_plus(FAKE_KEY)}"
    )
    with pytest.raises(SourceError) as info:
        fetch(client(FakeEIA([], script=[url_error]), max_retries=0))
    assert not leaks(str(info.value))


def test_response_echoing_key_is_sanitized_before_archiving():
    rows = synthetic_rows(date(2026, 10, 1), 1)
    pages = fetch(client(FakeEIA(rows, echo_key=True)))
    assert pages[0].sanitized is True
    assert not leaks(pages[0].body.decode())
    assert MARK in pages[0].body.decode()


def test_key_never_in_repr_stats_or_logs(caplog):
    rows = synthetic_rows(date(2026, 10, 1), 1)
    fake = FakeEIA(rows, script=[(503, f"echo {FAKE_KEY}".encode())])
    with caplog.at_level(logging.DEBUG):
        c = client(fake)
        fetch(c)
    assert not leaks(repr(c)) and not leaks(str(c.stats)) and not leaks(caplog.text)


def test_invalid_utf8_body_with_key_does_not_chain_raw_bytes():
    body = b"\xff\xfe" + FAKE_KEY.encode()
    with pytest.raises(ResponseValidationError) as info:
        fetch(client(FakeEIA([], script=[(200, body)])))
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert not leaks(str(info.value))
