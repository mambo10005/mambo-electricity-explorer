"""Optional backup-and-reset of local learning progress (`mambo learn-reset`).

Never runs on its own. Dry run by default: it only lists what would happen.

With --execute it:
1. asks for typed confirmation ("RESET");
2. copies <data_dir>/learn/progress.json to a new, timestamped file in a backup directory
   outside the Git repository, refusing to overwrite any existing backup;
3. verifies the backup byte-for-byte (SHA-256) and that the original did not change;
4. only then removes the original, so the app starts with empty progress;
5. prints how to restore.

It never prints the file's contents: only paths, sizes, modification times, and hashes.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mambo_explorer.config import find_repo_root

CONFIRM_WORD = "RESET"


class ResetError(RuntimeError):
    pass


def default_backup_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "mambo-electricity-explorer" / "progress-backups"


@dataclass(frozen=True)
class Plan:
    progress: Path
    exists: bool
    size: int | None
    modified_utc: str | None
    backup: Path


def tracking_repo(path: Path) -> Path | None:
    """The Git repository that would track `path` (it is inside it and not ignored), or None.

    Git decides, not a `.git` marker: a stray or broken `.git` folder above the path (as in
    some home directories) is not a repository. Without a usable git executable, any `.git`
    marker above the path is treated as a repository (the conservative answer).
    """
    anchor = next((a for a in (path, *path.parents) if a.exists()), None)
    if anchor is None:
        return None
    try:
        top = subprocess.run(
            ["git", "-C", str(anchor), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return find_repo_root(anchor)
    if top.returncode != 0:
        return None
    root = Path(top.stdout.strip())
    ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", str(path)])
    return None if ignored.returncode == 0 else root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan(data_dir: Path, backup_dir: Path | None = None, now: datetime | None = None) -> Plan:
    progress = Path(data_dir) / "learn" / "progress.json"
    backup_dir = Path(backup_dir or default_backup_dir()).expanduser().resolve()
    repo = tracking_repo(backup_dir / "probe.json")
    if repo is not None:
        raise ResetError(
            f"backup directory {backup_dir} is inside the Git repository {repo} and not ignored "
            "there; choose a directory outside any repository"
        )
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    exists = progress.is_file()
    stat = progress.stat() if exists else None
    return Plan(
        progress=progress,
        exists=exists,
        size=stat.st_size if stat else None,
        modified_utc=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat() if stat else None,
        backup=backup_dir / f"progress-{stamp}.json",
    )


def describe(p: Plan) -> list[str]:
    if not p.exists:
        return [f"No progress file at {p.progress}. Nothing to back up or reset."]
    return [
        f"Progress file: {p.progress} ({p.size} bytes, modified {p.modified_utc})",
        f"Backup would be written to: {p.backup}",
        "Contents are not shown.",
    ]


def restore_instructions(p: Plan) -> list[str]:
    return [
        "To restore, stop the app and copy the backup back (PowerShell):",
        f'  Copy-Item -LiteralPath "{p.backup}" -Destination "{p.progress}"',
        "Copy-Item refuses to overwrite an existing file without -Force; if the app has created "
        "a new progress file since the reset, decide which one to keep first.",
    ]


def execute(p: Plan, confirm: Callable[[str], str]) -> list[str]:
    """Back up, verify, then reset. Raises ResetError and leaves the original untouched on
    any problem before the final removal."""
    if not p.exists:
        return describe(p)
    answer = confirm(f"Type {CONFIRM_WORD} to back up and reset {p.progress}: ")
    if answer.strip() != CONFIRM_WORD:
        raise ResetError("not confirmed; nothing was changed")
    original_hash = _sha256(p.progress)
    p.backup.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(p.backup, "xb") as out:  # "x": refuse to overwrite an existing backup
            out.write(p.progress.read_bytes())
            out.flush()
            os.fsync(out.fileno())
    except FileExistsError:
        raise ResetError(f"backup {p.backup} already exists; nothing was changed") from None
    backup_hash = _sha256(p.backup)
    if backup_hash != original_hash:
        raise ResetError("backup does not match the original; the original was not changed")
    if _sha256(p.progress) != original_hash:
        raise ResetError("the progress file changed during the backup; it was not reset")
    p.progress.unlink()
    return [
        f"Backed up to {p.backup} (SHA-256 {backup_hash[:16]}…, verified).",
        f"Reset: removed {p.progress}. The app will start with empty progress.",
        *restore_instructions(p),
    ]
