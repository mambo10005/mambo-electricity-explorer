"""Archive safety. All archives here are SYNTHETIC, built in memory by the tests."""

import io
import zipfile

import pytest

from mambo_explorer.safe_zip import ArchiveError, Limits, _check_name, read_members


def make_zip(members: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_reads_valid_csv_member_in_memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    members = read_members(make_zip({"report.csv": b"a,b\n1,2\n"}))
    assert members == {"report.csv": b"a,b\n1,2\n"}
    assert list(tmp_path.iterdir()) == []  # nothing extracted to disk


@pytest.mark.parametrize(
    "name",
    ["../evil.csv", "/abs.csv", "dir/../../evil.csv", "C:evil.csv", "~/x.csv"],
)
def test_unsafe_member_paths_are_rejected(name):
    with pytest.raises(ArchiveError, match="unsafe member path"):
        read_members(make_zip({name: b"x"}))


def test_backslash_member_names_are_rejected():
    # zipfile on Windows rewrites backslashes to "/" when *writing*, so check the
    # validator directly; archives built elsewhere can carry raw backslashes.
    with pytest.raises(ArchiveError, match="unsafe member path"):
        _check_name("dir\\..\\evil.csv")


def test_non_csv_and_nested_archives_are_rejected():
    with pytest.raises(ArchiveError, match="unexpected member type"):
        read_members(make_zip({"run.exe": b"MZ"}))
    with pytest.raises(ArchiveError, match="unexpected member type"):
        read_members(make_zip({"inner.zip": make_zip({"a.csv": b"x"})}))


def test_directory_members_are_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo("folder/"), b"")
    with pytest.raises(ArchiveError, match="directory or link"):
        read_members(buffer.getvalue(), Limits(allowed_suffixes=(".csv", "/")))


def test_size_and_count_limits():
    with pytest.raises(ArchiveError, match="archive is"):
        read_members(b"x" * 101, Limits(max_archive_bytes=100))
    with pytest.raises(ArchiveError, match="members; limit"):
        read_members(make_zip({f"{i}.csv": b"x" for i in range(3)}), Limits(max_members=2))
    with pytest.raises(ArchiveError, match="declares"):
        read_members(make_zip({"big.csv": b"0" * 1000}), Limits(max_member_bytes=999))
    with pytest.raises(ArchiveError, match="decompresses beyond"):
        read_members(
            make_zip({"a.csv": b"0" * 600, "b.csv": b"0" * 600}), Limits(max_total_bytes=1000)
        )


def test_highly_compressed_bomb_is_bounded():
    bomb = make_zip({"bomb.csv": b"0" * 20_000_000})
    assert len(bomb) < 100_000  # tiny on the wire
    with pytest.raises(ArchiveError):
        read_members(bomb)


def test_lying_header_cannot_bypass_decompressed_limit():
    data = bytearray(make_zip({"a.csv": b"0" * 5000}))
    # Patch the central-directory uncompressed size to claim 10 bytes.
    cd = data.rfind(b"PK\x01\x02")
    data[cd + 24 : cd + 28] = (10).to_bytes(4, "little")
    with pytest.raises((ArchiveError, zipfile.BadZipFile)):
        read_members(bytes(data), Limits(max_member_bytes=100, max_total_bytes=100))


def test_garbage_and_empty_archives_are_rejected():
    with pytest.raises(ArchiveError, match="not a valid ZIP"):
        read_members(b"<html>error page</html>")
    with pytest.raises(ArchiveError, match="empty"):
        read_members(make_zip({}))
