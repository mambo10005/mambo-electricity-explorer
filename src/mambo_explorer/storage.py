"""Local observation store: append-only Parquet + SQLite catalog + DuckDB queries.

Layout under <data_dir>/eia930/:
    catalog.sqlite                       runs, run_files (the commit record)
    raw/run=<run_id>/page-<offset>.json  archived (sanitized) response bodies
    observations/entity=<BA>/metric=<type>/run=<run_id>.parquet
    quarantine/                          orphans moved here only on request
    .writer.lock                         single-writer lock

Commit sequence (SQLite and Parquet do not share a transaction):
    1. take the writer lock
    2. insert run row, status 'started' (committed immediately)
    3. write raw pages and Parquet files: temp file, then os.replace
    4. one SQLite transaction registers every file (with sha256) and sets 'committed'
    5. release the lock
Readers see only files registered by committed runs. A crash before step 4 leaves
unregistered files (orphans) that queries ignore, and a run stuck at 'started'.
`validate` reports both; it never deletes anything.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

STORE_DIR = "eia930"

OBSERVATION_SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("dataset", pa.string()),
        ("route", pa.string()),
        ("frequency", pa.string()),
        ("entity", pa.string()),
        ("entity_name", pa.string()),
        ("metric", pa.string()),
        ("metric_name", pa.string()),
        ("period", pa.string()),
        ("interval_start_utc", pa.timestamp("us", tz="UTC")),
        ("interval_end_utc", pa.timestamp("us", tz="UTC")),
        ("value_raw", pa.string()),
        ("value", pa.float64()),
        ("unit", pa.string()),
        ("quality_flags", pa.string()),
        ("revision", pa.int32()),
        ("retrieved_at_utc", pa.timestamp("us", tz="UTC")),
        ("publication_time_utc", pa.timestamp("us", tz="UTC")),
        ("request_start", pa.string()),
        ("request_end", pa.string()),
        ("run_id", pa.string()),
        ("archive_path", pa.string()),
        ("archive_sha256", pa.string()),
    ]
)
# Observation identity: one value per source series and period. A changed value_raw
# or unit for the same identity is stored as a new revision, never overwritten.
IDENTITY = ("source", "dataset", "route", "frequency", "entity", "metric", "period")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('started','committed','failed','abandoned')),
    entity TEXT, metrics TEXT, request_start TEXT, request_end TEXT,
    lookback_days INTEGER,
    requests INTEGER, retries INTEGER, pages INTEGER,
    rows_received INTEGER, rows_new INTEGER, rows_revised INTEGER, rows_unchanged INTEGER,
    error TEXT
);
CREATE TABLE IF NOT EXISTS run_files (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    kind TEXT NOT NULL CHECK (kind IN ('raw','observations')),
    path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    rows INTEGER,
    sanitized INTEGER NOT NULL DEFAULT 0
);
"""


class WriterLockError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def now_utc() -> datetime:
    return datetime.now(UTC)


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


@dataclass(frozen=True)
class FileRecord:
    kind: str
    path: str  # relative to the store root, forward slashes
    sha256: str
    bytes: int
    rows: int | None = None
    sanitized: bool = False


class Store:
    def __init__(
        self,
        data_dir: Path,
        namespace: str = STORE_DIR,
        schema: pa.Schema = OBSERVATION_SCHEMA,
        identity: tuple[str, ...] = IDENTITY,
    ) -> None:
        """One store per source dataset. Namespaces keep sources physically separate:
        each has its own directory, catalog, writer lock, schema, and identity."""
        if not namespace or not all(c.isalnum() or c in "-_" for c in namespace):
            raise ValueError(f"invalid store namespace {namespace!r}")
        missing = [c for c in identity if c not in schema.names]
        if missing:
            raise ValueError(f"identity columns {missing} not in schema")
        self.namespace = namespace
        self.schema = schema
        self.identity = identity
        self.root = Path(data_dir) / namespace
        self.catalog = self.root / "catalog.sqlite"
        self.lock_path = self.root / ".writer.lock"

    # --- catalog ---------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.catalog)
        con.row_factory = sqlite3.Row
        con.executescript(SCHEMA_SQL)
        return con

    def exists(self) -> bool:
        return self.catalog.is_file()

    @contextmanager
    def writer_lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = self.lock_path.read_text("utf-8", "replace").strip()
            raise WriterLockError(
                f"another collection holds the writer lock ({holder}). If no collection "
                f"is running, the lock is stale: delete {self.lock_path} after checking."
            ) from None
        with os.fdopen(fd, "w") as handle:
            handle.write(f"pid={os.getpid()} since={now_utc().isoformat()}")
        try:
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)

    def start_run(self, **fields) -> str:
        run_id = now_utc().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        with self.connect() as con:
            con.execute(
                "INSERT INTO runs (run_id, started_at, status, entity, metrics, request_start, "
                "request_end, lookback_days) VALUES (?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    now_utc().isoformat(),
                    "started",
                    fields.get("entity"),
                    fields.get("metrics"),
                    fields.get("request_start"),
                    fields.get("request_end"),
                    fields.get("lookback_days"),
                ),
            )
        return run_id

    def commit_run(self, run_id: str, files: list[FileRecord], **counts) -> None:
        """Step 4: register files and mark committed in one SQLite transaction."""
        con = self.connect()
        try:
            with con:
                con.executemany(
                    "INSERT INTO run_files (run_id, kind, path, sha256, bytes, rows, sanitized) "
                    "VALUES (?,?,?,?,?,?,?)",
                    [
                        (run_id, f.kind, f.path, f.sha256, f.bytes, f.rows, int(f.sanitized))
                        for f in files
                    ],
                )
                con.execute(
                    "UPDATE runs SET status='committed', finished_at=?, requests=?, retries=?, "
                    "pages=?, rows_received=?, rows_new=?, rows_revised=?, rows_unchanged=? "
                    "WHERE run_id=? AND status='started'",
                    (
                        now_utc().isoformat(),
                        counts.get("requests"),
                        counts.get("retries"),
                        counts.get("pages"),
                        counts.get("rows_received"),
                        counts.get("rows_new"),
                        counts.get("rows_revised"),
                        counts.get("rows_unchanged"),
                        run_id,
                    ),
                )
        finally:
            con.close()

    def fail_run(self, run_id: str, error: str, **counts) -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE runs SET status='failed', finished_at=?, error=?, requests=?, retries=? "
                "WHERE run_id=? AND status='started'",
                (
                    now_utc().isoformat(),
                    error[:1000],
                    counts.get("requests"),
                    counts.get("retries"),
                    run_id,
                ),
            )

    def runs(self, limit: int = 20) -> list[dict]:
        if not self.exists():
            return []
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def last_committed_run(self) -> dict | None:
        if not self.exists():
            return None
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM runs WHERE status='committed' ORDER BY finished_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def committed_files(self, kind: str) -> list[dict]:
        if not self.exists():
            return []
        with self.connect() as con:
            rows = con.execute(
                "SELECT f.* FROM run_files f JOIN runs r USING (run_id) "
                "WHERE r.status='committed' AND f.kind=? ORDER BY f.path",
                (kind,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- files -----------------------------------------------------------------

    def write_raw(
        self, run_id: str, offset: int, body: bytes, sanitized: bool, name: str | None = None
    ) -> FileRecord:
        """Archive a source artifact. `name` (a plain file name) overrides the page name."""
        if name is not None and (not name or "/" in name or "\\" in name or name.startswith(".")):
            raise ValueError(f"invalid artifact name {name!r}")
        rel = f"raw/run={run_id}/{name or f'page-{offset:07d}.json'}"
        atomic_write(self.root / rel, body)
        return FileRecord("raw", rel, sha256_bytes(body), len(body), None, sanitized)

    def write_observations(self, run_id: str, rows: list[dict]) -> list[FileRecord]:
        records = []
        groups: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            groups.setdefault((row["entity"], row["metric"]), []).append(row)
        for (entity, metric), group in sorted(groups.items()):
            rel = f"observations/entity={entity}/metric={metric}/run={run_id}.parquet"
            # Deterministic order by identity (EIA: ends with period; ERCOT: day/hour/flag).
            group = sorted(
                group,
                key=lambda r: tuple("" if r[c] is None else str(r[c]) for c in self.identity),
            )
            table = pa.Table.from_pylist(group, schema=self.schema)
            sink = pa.BufferOutputStream()
            pq.write_table(table, sink)
            data = sink.getvalue().to_pybytes()
            atomic_write(self.root / rel, data)
            records.append(
                FileRecord("observations", rel, sha256_bytes(data), len(data), len(group))
            )
        return records

    # --- queries -----------------------------------------------------------------

    def query(self) -> duckdb.DuckDBPyConnection:
        """DuckDB connection with `observations` (all revisions) and `latest` views."""
        # UTC session (ICU is statically linked); never auto-install extensions (no downloads).
        con = duckdb.connect(config={"autoinstall_known_extensions": False})
        con.execute("SET TimeZone = 'UTC'")
        files = [str(self.root / f["path"]) for f in self.committed_files("observations")]
        if files:
            # Relation API: file paths are passed as values, never spliced into SQL.
            con.read_parquet(files, union_by_name=True).create_view("observations")
        else:
            columns = ", ".join(
                f"CAST(NULL AS {_duck_type(f.type)}) AS {f.name}" for f in self.schema
            )
            con.execute(f"CREATE VIEW observations AS SELECT {columns} WHERE false")
        partition = ", ".join(self.identity)
        con.execute(
            "CREATE VIEW latest AS SELECT * FROM observations QUALIFY row_number() OVER "
            f"(PARTITION BY {partition} ORDER BY revision DESC) = 1"
        )
        return con

    def latest_index(self, where_in: dict[str, list]) -> dict[tuple, tuple]:
        """Latest (value_raw, unit, revision) keyed by the full identity tuple.

        where_in restricts columns to value lists (column names must be in the schema).
        """
        bad = [c for c in where_in if c not in self.schema.names]
        if bad:
            raise ValueError(f"unknown columns {bad}")
        clauses = " AND ".join(f"list_contains(?, {c})" for c in where_in) or "true"
        columns = ", ".join(self.identity)
        with self.query() as con:
            rows = con.execute(
                f"SELECT {columns}, value_raw, unit, revision FROM latest WHERE {clauses}",
                [list(v) for v in where_in.values()],
            ).fetchall()
        n = len(self.identity)
        return {tuple(r[:n]): (r[n], r[n + 1], r[n + 2]) for r in rows}

    def latest_by_identity(self, entity: str, metrics: list[str], start: str, end: str) -> dict:
        with self.query() as con:
            rows = con.execute(
                "SELECT metric, period, value_raw, unit, revision FROM latest "
                "WHERE entity = ? AND list_contains(?, metric) AND period BETWEEN ? AND ?",
                [entity, metrics, start, end],
            ).fetchall()
        return {(m, p): (raw, unit, rev) for m, p, raw, unit, rev in rows}

    # --- validation / reconciliation ----------------------------------------------

    def validate(self, *, mark_interrupted: bool = False, quarantine_orphans: bool = False) -> dict:
        """Check committed files against checksums; report orphans and interrupted runs.

        Only reports by default. The two flags are the only mutating options:
        marking stale 'started' runs 'abandoned', and moving orphan files into
        quarantine/ (never deleting them).
        """
        report = {"missing": [], "checksum_mismatch": [], "orphans": [], "interrupted": []}
        registered = set()
        for kind in ("raw", "observations"):
            for f in self.committed_files(kind):
                registered.add(f["path"])
                path = self.root / f["path"]
                if not path.is_file():
                    report["missing"].append(f["path"])
                elif sha256_file(path) != f["sha256"]:
                    report["checksum_mismatch"].append(f["path"])
        if self.root.is_dir():
            for path in sorted(self.root.rglob("*")):
                rel = path.relative_to(self.root).as_posix()
                if path.is_file() and rel.split("/")[0] in ("raw", "observations"):
                    if rel not in registered:
                        report["orphans"].append(rel)
        lock_held = self.lock_path.exists()
        report["interrupted"] = [
            r["run_id"] for r in self.runs(limit=10_000) if r["status"] == "started"
        ]
        report["lock_held"] = lock_held
        if mark_interrupted and report["interrupted"] and not lock_held:
            with self.connect() as con:
                con.execute(
                    "UPDATE runs SET status='abandoned', finished_at=?, "
                    "error='marked abandoned by validate' WHERE status='started'",
                    (now_utc().isoformat(),),
                )
        if quarantine_orphans and not lock_held:
            stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
            for rel in report["orphans"]:
                target = self.root / "quarantine" / stamp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(self.root / rel, target)
        report["ok"] = not (report["missing"] or report["checksum_mismatch"])
        return report

    def diagnostics(self) -> dict:
        size = (
            sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
            if self.root.is_dir()
            else 0
        )
        info = {
            "store": str(self.root),
            "namespace": self.namespace,
            "bytes_on_disk": size,
            "runs": {},
        }
        for r in self.runs(limit=10_000):
            info["runs"][r["status"]] = info["runs"].get(r["status"], 0) + 1
        info["observation_files"] = len(self.committed_files("observations"))
        info["raw_files"] = len(self.committed_files("raw"))
        with self.query() as con:
            info["observation_rows_all_revisions"] = con.execute(
                "SELECT count(*) FROM observations"
            ).fetchone()[0]
            info["latest_observations"] = con.execute("SELECT count(*) FROM latest").fetchone()[0]
            info["revised_identities"] = con.execute(
                "SELECT count(*) FROM latest WHERE revision > 1"
            ).fetchone()[0]
            info["missing_values_latest"] = con.execute(
                "SELECT count(*) FROM latest WHERE value IS NULL"
            ).fetchone()[0]
            span = (
                con.execute("SELECT min(period), max(period) FROM latest").fetchone()
                if "period" in self.schema.names
                else (None, None)
            )
        info["period_range"] = list(span)
        return info


def _duck_type(arrow_type: pa.DataType) -> str:
    if pa.types.is_timestamp(arrow_type):
        return "TIMESTAMPTZ"
    if pa.types.is_floating(arrow_type):
        return "DOUBLE"
    if pa.types.is_integer(arrow_type):
        return "INTEGER"
    return "VARCHAR"
