"""Select, download, normalize, and store NP6-345-CD documents (bounded)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mambo_explorer.ercot import dataset as ds
from mambo_explorer.ercot.client import Document, ErcotClient, ErcotError, UnavailableError
from mambo_explorer.storage import Store, now_utc

MAX_DOCUMENTS_PER_RUN = 7
DEFAULT_LATEST = 3


class SelectionError(ValueError):
    pass


def store(data_dir: Path) -> Store:
    return Store(data_dir, namespace=ds.STORE_NAMESPACE, schema=ds.SCHEMA, identity=ds.IDENTITY)


@dataclass(frozen=True)
class Selection:
    latest: int | None = DEFAULT_LATEST
    publish_dates: tuple[str, ...] = ()  # local dates as written in PublishDate (YYYY-MM-DD)

    def __post_init__(self) -> None:
        if self.publish_dates and self.latest is not None:
            raise SelectionError("use either --latest or --publish-date, not both")
        if self.latest is not None and not 1 <= self.latest <= MAX_DOCUMENTS_PER_RUN:
            raise SelectionError(f"--latest must be 1..{MAX_DOCUMENTS_PER_RUN}")
        if len(self.publish_dates) > MAX_DOCUMENTS_PER_RUN:
            raise SelectionError(f"at most {MAX_DOCUMENTS_PER_RUN} publish dates per run")

    def apply(self, documents: list[Document]) -> list[Document]:
        if self.publish_dates:
            chosen = [d for d in documents if d.publish_time_raw[:10] in self.publish_dates]
            found = {d.publish_time_raw[:10] for d in chosen}
            missing = sorted(set(self.publish_dates) - found)
            if missing:
                raise UnavailableError(
                    f"no public NP6-345-CD CSV published on {missing}; ERCOT keeps about "
                    f"{ds.PUBLIC_RETENTION_DAYS} days in the public list"
                )
            if len(chosen) > MAX_DOCUMENTS_PER_RUN:
                raise SelectionError("selection matches more documents than the per-run limit")
            return chosen
        return documents[-self.latest :]

    def describe(self) -> dict:
        return {
            "source": f"ERCOT {ds.DATASET} '{ds.REPORT_NAME}' (report type {ds.REPORT_TYPE_ID})",
            "access": "ercot.com public report listing + document download (no login)",
            "selection": (
                f"documents published on {list(self.publish_dates)}"
                if self.publish_dates
                else f"latest {self.latest} CSV document(s) in the public list"
            ),
            "request_budget": f"1 list request + up to {self.latest or len(self.publish_dates)} "
            "downloads, plus at most 2 retries each; 1 s pause between requests",
            "credential": "none (public download); EIA_API_KEY is never used",
        }


def normalize(
    document: Document,
    rows: list[ds.ParsedRow],
    *,
    run_id: str,
    archive: tuple[str, str],
    retrieved_at,
) -> list[dict]:
    published = ds.parse_publish_time(document.publish_time_raw)
    records = []
    for row in rows:
        diff = ds.zone_sum_minus_total(row.values)
        for column, raw in row.values.items():
            value, flags = ds.parse_value(raw)
            records.append(
                {
                    "source": ds.SOURCE,
                    "dataset": ds.DATASET,
                    "report_type_id": ds.REPORT_TYPE_ID,
                    "doc_id": document.doc_id,
                    "doc_name": document.name,
                    "publish_time_raw": document.publish_time_raw,
                    "publication_time_utc": published,
                    "oper_day": row.oper_day,
                    "oper_date": row.oper_date,
                    "hour_ending": row.hour_ending,
                    "dst_flag": row.dst_flag,
                    "row_order": row.row_order,
                    "entity": column,
                    "metric": ds.METRIC,
                    "value_raw": raw if raw != "" else None,
                    "value": value,
                    "unit": ds.UNIT,
                    "quality_flags": ",".join(flags),
                    "zone_sum_minus_total": diff if column == ds.TOTAL else None,
                    "revision": 0,
                    "retrieved_at_utc": retrieved_at,
                    "run_id": run_id,
                    "archive_path": archive[0],
                    "archive_sha256": archive[1],
                }
            )
    return records


def assign_revisions(target: Store, records: list[dict]) -> tuple[list[dict], dict]:
    latest = target.latest_index({"oper_day": sorted({r["oper_day"] for r in records})})
    keep, counts = [], {"rows_new": 0, "rows_revised": 0, "rows_unchanged": 0}
    for record in records:
        key = tuple(record[c] for c in ds.IDENTITY)
        previous = latest.get(key)
        if previous is None:
            record["revision"] = 1
            counts["rows_new"] += 1
        elif (previous[0], previous[1]) == (record["value_raw"], record["unit"]):
            counts["rows_unchanged"] += 1
            continue
        else:
            record["revision"] = previous[2] + 1
            counts["rows_revised"] += 1
        latest[key] = (record["value_raw"], record["unit"], record["revision"])
        keep.append(record)
    return keep, counts


def collect(selection: Selection, client: ErcotClient, target: Store) -> dict:
    """One bounded collection under the shared writer lock of the ERCOT namespace."""
    with target.writer_lock():
        run_id = target.start_run(
            entity="ERCOT zones+TOTAL",
            metrics=ds.METRIC,
            request_start=",".join(selection.publish_dates) or f"latest {selection.latest}",
            request_end=None,
            lookback_days=0,
        )
        try:
            chosen = selection.apply(client.list_documents())
            files, records, days = [], [], []
            for document in chosen:  # oldest first, so a repost becomes the later revision
                body, csv_bytes, member = client.download_csv(document)
                rows = ds.parse_csv(csv_bytes)
                record = target.write_raw(run_id, 0, body, False, name=f"{document.doc_id}.zip")
                files.append(record)
                retrieved = now_utc()
                records += normalize(
                    document,
                    rows,
                    run_id=run_id,
                    archive=(record.path, record.sha256),
                    retrieved_at=retrieved,
                )
                days.append(
                    {
                        "doc_id": document.doc_id,
                        "published": document.publish_time_raw,
                        "oper_day": rows[0].oper_day,
                        "rows": len(rows),
                        "member": member,
                    }
                )
            keep, counts = assign_revisions(target, records)
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
        except (ErcotError, ds.ReportFormatError, SelectionError) as exc:
            target.fail_run(
                run_id, str(exc), requests=client.stats.requests, retries=client.stats.retries
            )
            raise
    return {
        "run_id": run_id,
        "requests": client.stats.requests,
        "retries": client.stats.retries,
        "documents": days,
        "values_received": len(records),
        **counts,
    }
