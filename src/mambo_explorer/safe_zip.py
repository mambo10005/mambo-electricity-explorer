"""Read members of an untrusted ZIP archive in memory, with strict limits.

Nothing is extracted to disk and nothing is executed. Rejected:
- member paths that are absolute, contain '..', or carry a drive or UNC prefix
- directory and symlink members, and nested archives
- more members than allowed
- compressed or decompressed sizes above the limits (enforced while reading,
  not just from the header, so a lying header cannot cause a zip bomb)
"""

from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath


class ArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    max_archive_bytes: int = 2_000_000
    max_members: int = 4
    max_member_bytes: int = 5_000_000
    max_total_bytes: int = 10_000_000
    allowed_suffixes: tuple[str, ...] = (".csv",)


def _check_name(name: str) -> None:
    if not name or "\\" in name or ":" in name or name.startswith("/"):
        raise ArchiveError(f"unsafe member path {name!r}")
    parts = PurePosixPath(name).parts
    if ".." in parts or any(p.startswith("~") for p in parts):
        raise ArchiveError(f"unsafe member path {name!r}")


DEFAULT_LIMITS = Limits()


def read_members(data: bytes, limits: Limits = DEFAULT_LIMITS) -> dict[str, bytes]:
    if len(data) > limits.max_archive_bytes:
        raise ArchiveError(f"archive is {len(data)} bytes; limit {limits.max_archive_bytes}")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"not a valid ZIP archive ({exc})") from None
    infos = archive.infolist()
    if not infos:
        raise ArchiveError("archive is empty")
    if len(infos) > limits.max_members:
        raise ArchiveError(f"archive has {len(infos)} members; limit {limits.max_members}")
    members: dict[str, bytes] = {}
    total = 0
    for info in infos:
        _check_name(info.filename)
        mode = info.external_attr >> 16
        if info.is_dir() or stat.S_ISLNK(mode):
            raise ArchiveError(f"directory or link member {info.filename!r} not allowed")
        if not info.filename.lower().endswith(limits.allowed_suffixes):
            raise ArchiveError(f"unexpected member type {info.filename!r}")
        if info.file_size > limits.max_member_bytes:
            raise ArchiveError(f"member {info.filename!r} declares {info.file_size} bytes")
        with archive.open(info) as handle:
            content = handle.read(limits.max_member_bytes + 1)
        if len(content) > limits.max_member_bytes:
            raise ArchiveError(f"member {info.filename!r} exceeds {limits.max_member_bytes} bytes")
        total += len(content)
        if total > limits.max_total_bytes:
            raise ArchiveError(f"archive decompresses beyond {limits.max_total_bytes} bytes")
        if info.filename in members:
            raise ArchiveError(f"duplicate member {info.filename!r}")
        members[info.filename] = content
    return members
