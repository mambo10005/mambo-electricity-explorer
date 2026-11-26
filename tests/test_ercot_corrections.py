"""ERCOT NP4-196-M / NP4-197-M SPP price corrections at HB_NORTH (ADR 0024).

Offline and credential-free. Every value is SYNTHETIC; the layout follows the 2026-11-26
review (header, listing JSON with several document kinds, one CSV member per ZIP).
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from mambo_explorer import cli, refresh_config
from mambo_explorer.ercot import corrections as cx
from mambo_explorer.ercot.client import ErcotClient, ResponseError, UnavailableError

STAMP = "11/18/2026 10:00:00"


def dam_line(point="HB_NORTH", hour="1", original="56.81", corrected="56.83", stamp=STAMP, dst="N"):
    return ["11/16/2026", hour, point, original, corrected, stamp, dst]


def rt_line(point="HB_NORTH", hour="10", interval="1", original="15.66", corrected="15.68", **kw):
    stamp, dst = kw.get("stamp", STAMP), kw.get("dst", "N")
    kind = "HU" if point.startswith("HB_") else "RN"
    return ["08/30/2026", hour, interval, point, kind, original, corrected, stamp, dst]


def csv_bytes(kind, lines) -> bytes:
    text = ",".join(kind.header) + "\n" + "\n".join(",".join(r) for r in lines) + "\n"
    return text.encode()


def zip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cdr.synthetic.csv", data)
    return buffer.getvalue()


def entry(kind, doc_id, published, friendly, size=2000):
    return {
        "Document": {
            "SecurityStatus": "P",
            "ContentSize": str(size),
            "ReportTypeID": kind.report_type_id,
            "FriendlyName": friendly,
            "ConstructedName": f"cdr.{friendly}.zip",
            "DocID": doc_id,
            "PublishDate": published,
        }
    }


class FakeCorrections:
    """docs: doc_id -> (publish time, CSV bytes). Also lists the report's other document kinds."""

    def __init__(self, kind, docs):
        self.kind, self.docs, self.urls = kind, docs, []
        self.zips = {i: zip_bytes(data) for i, (_, data) in docs.items()}

    def __call__(self, url, timeout):
        self.urls.append(url)
        if "IceDocListJsonWS" in url:
            assert url.endswith(self.kind.report_type_id)
            tail = self.kind.name_tag
            entries = []
            for i, (pub, _) in self.docs.items():
                day = pub[:10].replace("-", "")
                name = f"pricecorrection_{self.kind.document_kind}_{day}_to_{day}_{tail}"
                entries += [
                    entry(self.kind, i, pub, f"{name}_csv", len(self.zips[i])),
                    entry(self.kind, f"x{i}", pub, f"{name}_xml"),
                    entry(
                        self.kind,
                        f"e{i}",
                        pub,
                        f"pricecorrection_X_EBLMP_{day}_to_{day}_{tail}_csv",
                    ),
                ]
            body = json.dumps({"ListDocsByRptTypeRes": {"DocumentList": entries}}).encode()
            return 200, "application/json", body
        doc_id = url.rsplit("=", 1)[1]
        if doc_id not in self.zips:
            return 404, "text/html", b"<html>not found</html>"
        return 200, "application/zip", self.zips[doc_id]


def client(fake, budget=6):
    return ErcotClient(transport=fake, sleep=lambda s: None, max_requests=budget)


def run(kind, data_dir, docs, selection=None):
    fake = FakeCorrections(kind, docs)
    return cx.collect(
        kind,
        selection or cx.Selection(latest=len(docs)),
        client(fake),
        cx.store(data_dir, kind),
    ), fake


def stored(kind, data_dir):
    columns = "delivery_date_raw, delivery_hour, delivery_interval, correction_time_raw, "
    columns += (
        "original_raw, corrected_raw, original_value, corrected_value, revision, location_type"
    )
    with cx.store(data_dir, kind).query() as con:
        return con.execute(
            f"SELECT {columns} FROM latest ORDER BY correction_time_raw, revision"
        ).fetchall()


# --- contract ---------------------------------------------------------------------------------


def test_reviewed_identifiers_and_separate_stores():
    assert (cx.DAM.dataset, cx.DAM.report_type_id) == ("NP4-196-M", "13044")
    assert (cx.RTM.dataset, cx.RTM.report_type_id) == ("NP4-197-M", "13045")
    assert cx.DAM.namespace != cx.RTM.namespace
    assert {cx.DAM.namespace, cx.RTM.namespace}.isdisjoint(
        {"eia930", "ercot-np6-345-cd", "ercot-np4-190-cd", "ercot-np6-905-cd", "eia930-fuel-type"}
    )
    for kind in cx.KINDS.values():
        assert "correction_time_raw" in kind.identity and "dst_flag" in kind.identity
    assert "delivery_interval" in cx.RTM.identity
    assert "nothing is converted to UTC" in cx.TIME_TEXT and "HourEnding" in cx.TIME_TEXT


def test_corrections_are_never_part_of_the_refresh_plan():
    assert not set(cx.KINDS) & set(refresh_config.SOURCES)
    assert not set(cx.KINDS) & set(cli.REFRESH_SOURCES)
    assert set(cx.KINDS) <= set(cli.SOURCES)


def test_listing_patterns_match_the_live_file_names_exactly():
    live = {
        cx.DAM: "pricecorrection_DAM_SPP_20261118_to_20261118_NP4196_csv",
        cx.RTM: "pricecorrection_RTM_SPP_20260901_to_20260901_NP4197_csv",
    }
    for kind, name in live.items():
        assert kind.report.is_csv(name) and not kind.report.is_csv(name.replace("_csv", "_xml"))
        assert not kind.report.is_csv(name.replace("SPP", "EBLMP"))
        assert not kind.report.is_csv(name.replace("SPP", "MCPC_SPP"))


def test_an_empty_listing_fails_the_run_instead_of_committing_nothing(tmp_path):
    with pytest.raises(UnavailableError, match="naming may have changed"):
        run(cx.DAM, tmp_path, {}, cx.Selection(latest=1))
    assert cx.store(tmp_path, cx.DAM).runs()[0]["status"] == "failed"


def test_only_the_spp_csv_family_is_listed(tmp_path):
    docs = {"101": ("2026-11-18T08:46:49-06:00", csv_bytes(cx.DAM, [dam_line()]))}
    listed = client(FakeCorrections(cx.DAM, docs)).list_documents(cx.DAM.report)
    assert [d.doc_id for d in listed] == ["101"]
    assert "DAM_SPP" in listed[0].friendly_name and listed[0].friendly_name.endswith("_csv")


# --- parsing ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind, line, message",
    [
        (cx.DAM, ["11/16/2026", "1", "HB_NORTH", "1", "2", STAMP], "fields"),
        (cx.DAM, dam_line(hour="0"), "DeliveryHour"),
        (cx.DAM, dam_line(hour="25"), "DeliveryHour"),
        (cx.DAM, dam_line(dst="X"), "DSTFlag"),
        (cx.DAM, dam_line(stamp="2026-11-18"), "PriceCorrectionTime"),
        (cx.DAM, ["2026-11-16", *dam_line()[1:]], "DeliveryDate"),
        (cx.RTM, rt_line(interval="5"), "DeliveryInterval"),
        (cx.RTM, rt_line(interval=""), "DeliveryInterval"),
    ],
)
def test_format_errors_are_rejected(kind, line, message):
    with pytest.raises(cx.CorrectionFormatError, match=message):
        cx.parse_csv(csv_bytes(kind, [line]), kind)


def test_header_mismatch_and_empty_files_are_rejected():
    with pytest.raises(cx.CorrectionFormatError, match="unexpected header"):
        cx.parse_csv(csv_bytes(cx.RTM, [rt_line()]), cx.DAM)
    with pytest.raises(cx.CorrectionFormatError, match="no data rows"):
        cx.parse_csv(csv_bytes(cx.DAM, []), cx.DAM)


def test_a_document_without_the_hub_is_valid_and_has_no_rows():
    parsed = cx.parse_csv(csv_bytes(cx.DAM, [dam_line("HB_WEST"), dam_line("LZ_X")]), cx.DAM)
    assert parsed.rows == [] and parsed.downloaded_rows == 2
    assert parsed.downloaded_settlement_points == 2


def test_duplicate_hub_events_are_refused_but_different_correction_times_are_distinct():
    with pytest.raises(cx.CorrectionFormatError, match="duplicate"):
        cx.parse_csv(csv_bytes(cx.DAM, [dam_line(), dam_line()]), cx.DAM)
    later = dam_line(stamp="11/19/2026 10:00:00")
    assert len(cx.parse_csv(csv_bytes(cx.DAM, [dam_line(), later]), cx.DAM).rows) == 2


# --- collection -------------------------------------------------------------------------------


def test_dam_keeps_only_the_hub_with_raw_labels_and_no_interval(tmp_path):
    data = csv_bytes(cx.DAM, [dam_line("HB_WEST"), dam_line(original="-1.50", corrected="")])
    summary, fake = run(cx.DAM, tmp_path, {"101": ("2026-11-18T08:46:49-06:00", data)})
    assert summary["stored_scope_rows"] == 1 and summary["downloaded_rows"] == 2
    assert summary["requests"] == 2 and summary["rows_new"] == 1
    [row] = stored(cx.DAM, tmp_path)
    assert row[:6] == ("11/16/2026", "1", None, STAMP, "-1.50", None)
    assert row[6] == -1.5 and row[7] is None and row[8] == 1 and row[9] is None


def test_rt_keeps_interval_and_the_files_own_location_type(tmp_path):
    data = csv_bytes(cx.RTM, [rt_line("A4_DGR1_RN"), rt_line(interval="3")])
    run(cx.RTM, tmp_path, {"201": ("2026-09-01T15:20:40-06:00", data)})
    [row] = stored(cx.RTM, tmp_path)
    assert (row[1], row[2], row[9]) == ("10", "3", "HU")


def test_a_hubless_document_commits_a_run_with_zero_rows(tmp_path):
    data = csv_bytes(cx.RTM, [rt_line("A4_DGR1_RN")])
    summary, _ = run(cx.RTM, tmp_path, {"201": ("2026-09-01T15:20:40-06:00", data)})
    assert summary["stored_scope_rows"] == 0 and summary["rows_new"] == 0
    assert stored(cx.RTM, tmp_path) == []
    assert cx.store(tmp_path, cx.RTM).last_committed_run()["status"] == "committed"


def test_repeat_is_idempotent_and_a_changed_repost_is_a_revision(tmp_path):
    docs = {"101": ("2026-11-18T08:46:49-06:00", csv_bytes(cx.DAM, [dam_line()]))}
    run(cx.DAM, tmp_path, docs)
    again, _ = run(cx.DAM, tmp_path, docs)
    assert again["rows_unchanged"] == 1 and again["rows_new"] == 0
    changed = {
        "102": ("2026-11-18T09:46:49-06:00", csv_bytes(cx.DAM, [dam_line(corrected="9.99")]))
    }
    third, _ = run(cx.DAM, tmp_path, changed)
    assert third["rows_revised"] == 1
    [row] = stored(cx.DAM, tmp_path)
    assert row[5] == "9.99" and row[8] == 2


def test_a_later_correction_of_the_same_interval_is_a_separate_observation(tmp_path):
    first = csv_bytes(cx.DAM, [dam_line()])
    second = csv_bytes(cx.DAM, [dam_line(corrected="60.00", stamp="11/19/2026 10:00:00")])
    run(cx.DAM, tmp_path, {"101": ("2026-11-18T08:46:49-06:00", first)})
    summary, _ = run(cx.DAM, tmp_path, {"102": ("2026-11-19T08:46:49-06:00", second)})
    assert summary["rows_new"] == 1 and summary["rows_revised"] == 0
    assert [(r[3], r[8]) for r in stored(cx.DAM, tmp_path)] == [
        (STAMP, 1),
        ("11/19/2026 10:00:00", 1),
    ]


def test_corrections_never_touch_the_price_stores(tmp_path):
    run(cx.DAM, tmp_path, {"101": ("2026-11-18T08:46:49-06:00", csv_bytes(cx.DAM, [dam_line()]))})
    assert not (tmp_path / "ercot-np4-190-cd").exists()
    assert (tmp_path / cx.DAM.namespace).is_dir()


def test_a_bad_document_fails_the_run_and_stores_nothing(tmp_path):
    bad = csv_bytes(cx.DAM, [dam_line(dst="X")])
    with pytest.raises(cx.CorrectionFormatError):
        run(cx.DAM, tmp_path, {"101": ("2026-11-18T08:46:49-06:00", bad)})
    assert stored(cx.DAM, tmp_path) == []
    assert cx.store(tmp_path, cx.DAM).runs()[0]["status"] == "failed"


def test_oversized_declared_documents_are_refused(tmp_path):
    fake = FakeCorrections(cx.DAM, {"101": ("2026-11-18T08:46:49-06:00", b"")})
    fake.zips["101"] = b"PK\x03\x04" + b"0" * (cx.ZIP_LIMITS.max_archive_bytes + 1)
    with pytest.raises(ResponseError):
        cx.collect(cx.DAM, cx.Selection(latest=1), client(fake), cx.store(tmp_path, cx.DAM))


# --- selection and CLI ------------------------------------------------------------------------


def test_selection_bounds():
    with pytest.raises(cx.SelectionError):
        cx.Selection(latest=cx.MAX_DOCUMENTS_PER_RUN + 1)
    with pytest.raises(cx.SelectionError):
        cx.Selection(latest=1, publish_dates=("2026-11-18",))
    with pytest.raises(cx.SelectionError):
        cx.Selection(latest=None, publish_dates=("a", "b", "c", "d"))


def test_publish_date_matching_too_many_documents_is_refused():
    docs = [
        type("D", (), {"publish_time_raw": f"2026-07-14T14:{m}:00-06:00"})() for m in range(10, 14)
    ]
    with pytest.raises(cx.SelectionError, match="per-run limit"):
        cx.Selection(latest=None, publish_dates=("2026-07-14",)).apply(docs, cx.RTM)


@pytest.mark.parametrize("source", ["ercot-dam-corrections", "ercot-rt-corrections"])
def test_cli_dry_run_sends_nothing_and_describes_the_scope(source, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("MAMBO_DATA_DIR", str(tmp_path))
    assert cli.main(["--no-dotenv", "collect", "--source", source, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Dry run: no requests sent" in out and "HB_NORTH" in out and "never downloaded" in out
    assert cli.main(["--no-dotenv", "sources", "--source", source]) == 0
    assert "never written into the stored price series" in capsys.readouterr().out


def test_refresh_rejects_a_correction_source():
    with pytest.raises(SystemExit):
        cli.main(["--no-dotenv", "refresh", "--source", "ercot-dam-corrections", "--dry-run"])
