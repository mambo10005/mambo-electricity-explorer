"""Published-document inventory for ERCOT NP6-905-CD real-time prices (Stage 21, ADR 0018).

ERCOT publishes one document per 15-minute Settlement Interval and its public list keeps about
7 days. The inventory records every document this computer has seen in a listing, by ERCOT's
own DocID, so collection can be planned and reported per document:

- discovered:  seen in a listing, never requested
- collected:   its HB_NORTH value is in committed observations (derived from the store, so
               the inventory can never claim more than the store holds)
- failed:      the last request or parse failed; requested again after never-attempted ones
- deferred:    eligible but left by the run's document or request bound
- interval-row-absent: downloaded and valid, but without an HB_NORTH/HU row (the interval
               is missing inside a downloaded document; the archive is kept)
- superseded:  collected, but a later document re-posted the same interval with another value
- not listed:  no longer visible in the most recent listing. That is not proof that ERCOT or
               any other authorized archive lost it, only that this access method no longer
               reaches it.

A PublishDate "date" here is the first ten characters of ERCOT's PublishDate exactly as written
(e.g. 2026-10-06 from 2026-10-06T00:02:01-05:00); nothing is converted to UTC.

The inventory lives beside the real-time store (its own SQLite file in the same namespace).
Writes happen only inside a collection, under the store's writer lock; readers open it
read-only and never create it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from datetime import datetime
from pathlib import Path

from mambo_explorer.ercot.client import Document
from mambo_explorer.storage import Store

FILE_NAME = "inventory.sqlite"

DISCOVERED = "discovered"
COLLECTED = "collected"
FAILED = "failed"
DEFERRED = "deferred"
ROW_ABSENT = "interval-row-absent"
SUPERSEDED = "superseded"
STATUSES = (DISCOVERED, COLLECTED, FAILED, DEFERRED, ROW_ABSENT, SUPERSEDED)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    friendly_name TEXT NOT NULL,
    publish_time_raw TEXT NOT NULL,
    publish_date TEXT NOT NULL,
    first_listed_utc TEXT NOT NULL,
    last_listed_utc TEXT NOT NULL,
    listed INTEGER NOT NULL,
    outcome TEXT,
    outcome_utc TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    downloads INTEGER NOT NULL DEFAULT 0,
    last_downloaded_utc TEXT
);
CREATE TABLE IF NOT EXISTS listings (
    listed_at_utc TEXT NOT NULL,
    documents INTEGER NOT NULL,
    oldest_publish_raw TEXT,
    newest_publish_raw TEXT,
    new_documents INTEGER NOT NULL,
    no_longer_listed INTEGER NOT NULL
);
"""


def publish_date(publish_time_raw: str) -> str:
    """The PublishDate's date label as ERCOT writes it (no conversion)."""
    return publish_time_raw[:10]


class Inventory:
    def __init__(self, target: Store) -> None:
        self.path: Path = target.root / FILE_NAME

    # --- writes (inside a collection, under the store's writer lock) ----------------------

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.executescript(SCHEMA_SQL)
        return con

    def record_listing(self, documents: list[Document], now: datetime) -> dict:
        """Upsert every listed document; flag known documents the listing no longer shows."""
        stamp = now.isoformat()
        listed_ids = {d.doc_id for d in documents}
        with closing(self._connect()) as con, con:
            known = {r[0] for r in con.execute("SELECT doc_id FROM documents")}
            for d in documents:
                if d.doc_id in known:
                    con.execute(
                        "UPDATE documents SET last_listed_utc=?, listed=1, friendly_name=?, "
                        "publish_time_raw=?, publish_date=? WHERE doc_id=?",
                        (
                            stamp,
                            d.friendly_name,
                            d.publish_time_raw,
                            publish_date(d.publish_time_raw),
                            d.doc_id,
                        ),
                    )
                else:
                    con.execute(
                        "INSERT INTO documents (doc_id, friendly_name, publish_time_raw, "
                        "publish_date, first_listed_utc, last_listed_utc, listed) "
                        "VALUES (?,?,?,?,?,?,1)",
                        (
                            d.doc_id,
                            d.friendly_name,
                            d.publish_time_raw,
                            publish_date(d.publish_time_raw),
                            stamp,
                            stamp,
                        ),
                    )
            dropped = [doc_id for doc_id in known - listed_ids]
            newly_dropped = 0
            for doc_id in dropped:
                newly_dropped += con.execute(
                    "UPDATE documents SET listed=0 WHERE doc_id=? AND listed=1", (doc_id,)
                ).rowcount
            summary = {
                "listed_at_utc": stamp,
                "documents": len(documents),
                "oldest_publish_raw": documents[0].publish_time_raw if documents else None,
                "newest_publish_raw": documents[-1].publish_time_raw if documents else None,
                "new_documents": len(listed_ids - known),
                "no_longer_listed": newly_dropped,
            }
            con.execute(
                "INSERT INTO listings VALUES (?,?,?,?,?,?)",
                tuple(summary.values()),
            )
        return summary

    def record_outcomes(self, outcomes: Iterable[tuple[str, str, str | None]], now: datetime):
        """(doc_id, outcome, error) after the run's commit. Outcomes are informational: whether
        a document is collected is always derived from committed observations."""
        stamp = now.isoformat()
        with closing(self._connect()) as con, con:
            for doc_id, outcome, error in outcomes:
                attempted = outcome != DEFERRED
                downloaded = outcome in (COLLECTED, ROW_ABSENT)
                con.execute(
                    "UPDATE documents SET outcome=?, outcome_utc=?, error=?, "
                    "attempts=attempts+?, downloads=downloads+?, "
                    "last_downloaded_utc=CASE WHEN ? THEN ? ELSE last_downloaded_utc END "
                    "WHERE doc_id=?",
                    (
                        outcome,
                        stamp,
                        error,
                        int(attempted),
                        int(downloaded),
                        int(downloaded),
                        stamp,
                        doc_id,
                    ),
                )

    # --- reads (never create the file) ---------------------------------------------------

    def _read(self, sql: str, params=()) -> list[dict]:
        if not self.path.is_file():
            return []
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute(sql, params).fetchall()]

    def documents(self) -> list[dict]:
        return self._read("SELECT * FROM documents ORDER BY publish_time_raw, doc_id")

    def last_listing(self) -> dict | None:
        rows = self._read("SELECT * FROM listings ORDER BY listed_at_utc DESC LIMIT 1")
        return rows[0] if rows else None


def collected_doc_ids(target: Store) -> set[str]:
    """DocIDs whose HB_NORTH row is in committed observations (any revision)."""
    if not target.committed_files("observations"):
        return set()
    with target.query() as con:
        return {r[0] for r in con.execute("SELECT DISTINCT doc_id FROM observations").fetchall()}


def superseded_doc_ids(target: Store) -> set[str]:
    """Collected documents whose interval now has a later revision from another document."""
    if not target.committed_files("observations"):
        return set()
    with target.query() as con:
        rows = con.execute(
            "SELECT o.doc_id FROM observations o JOIN latest l USING "
            "(source, dataset, market_stage, location, delivery_date_raw, delivery_hour, "
            "delivery_interval, dst_flag) WHERE o.doc_id <> l.doc_id AND o.revision < l.revision"
        ).fetchall()
    return {r[0] for r in rows}


def classify(rows: list[dict], collected: set[str], superseded: set[str]) -> list[dict]:
    """Each inventory row with its derived `status` (see the module docstring)."""
    out = []
    for row in rows:
        doc_id = row["doc_id"]
        if doc_id in superseded:
            status = SUPERSEDED
        elif doc_id in collected:
            status = COLLECTED
        elif row["outcome"] in (FAILED, DEFERRED, ROW_ABSENT):
            status = row["outcome"]
        else:
            status = DISCOVERED  # includes a crash between download and commit
        out.append({**row, "status": status})
    return out


def in_range(row: dict, start: str | None, end: str | None) -> bool:
    day = row["publish_date"]
    return (start is None or day >= start) and (end is None or day <= end)
