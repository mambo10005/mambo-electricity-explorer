"""Runtime configuration: data directory and EIA credential, with safety checks.

- MAMBO_DATA_DIR sets the observation store location. The default is ./data, which
  is gitignored.
- EIA_API_KEY is read from the environment. It is only needed for collection, never
  for tests or app startup.
- An optional .env in the working directory is loaded by the CLI. It never
  overrides variables already set, and it is refused if git does not ignore it.
- MAMBO_FORBIDDEN_DATA_DIRS (os.pathsep-separated) lists protected directories that the
  data directory must never be, or be inside. Tests, the quality gate, and browser
  harnesses set it to the developer's real ./data, so a mistaken configuration fails loudly
  instead of writing there. Comparison survives casing differences, relative paths,
  symlinks/junctions (resolved), and other aliases of existing directories (samefile).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Directory names that are (or may become) published or tracked content.
PUBLICATION_DIR_NAMES = {"public", "publish", "site", "www", "static", "dist", "docs"}
DOTENV_KEYS = {"EIA_API_KEY", "MAMBO_DATA_DIR"}
FORBIDDEN_ENV = "MAMBO_FORBIDDEN_DATA_DIRS"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_key: str | None = field(default=None, repr=False)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


def find_repo_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def same_or_inside(path: Path, protected: Path) -> bool:
    """True if `path` is `protected` or inside it, after resolving links and ignoring case.

    Both are resolved first (symlinks and Windows junctions are followed). For directories
    that exist, os.path.samefile also catches aliases such as 8.3 short names.
    """
    a, b = Path(path).expanduser().resolve(), Path(protected).expanduser().resolve()
    na, nb = _norm(a), _norm(b)
    if na == nb or na.startswith(nb.rstrip("\\/") + os.sep):
        return True
    if not b.exists():
        return False
    for candidate in (a, *a.parents):
        try:
            if candidate.exists() and os.path.samefile(candidate, b):
                return True
        except OSError:
            continue
    return False


def forbidden_dirs() -> list[Path]:
    raw = os.environ.get(FORBIDDEN_ENV, "")
    return [Path(p) for p in raw.split(os.pathsep) if p.strip()]


def validate_data_dir(data_dir: Path, repo_root: Path | None) -> Path:
    """Return the resolved data dir, or raise ConfigError if it is unsafe."""
    path = data_dir.expanduser().resolve()
    for protected in forbidden_dirs():
        if same_or_inside(path, protected):
            raise ConfigError(
                f"data directory {path} is a protected location ({FORBIDDEN_ENV}); "
                "tests and harnesses must use a scratch directory"
            )
    if any(part.lower() in PUBLICATION_DIR_NAMES for part in path.parts):
        raise ConfigError(f"data directory {path} is inside a publication-style directory")
    if repo_root is not None:
        root = repo_root.resolve()
        if path == root or root.is_relative_to(path):
            raise ConfigError(f"data directory {path} would contain the repository")
        if path.is_relative_to(root) and not path.is_relative_to(root / "data"):
            raise ConfigError(
                f"data directory {path} is inside the repository but not under its "
                "gitignored data/ directory; use data/ or a path outside the repository"
            )
    return path


def _git_ignores(path: Path, repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(path)], cwd=repo_root, capture_output=True
    )
    return result.returncode == 0


def load_dotenv(path: Path, repo_root: Path | None) -> list[str]:
    """Load allowed keys from a .env file without overriding the environment.

    Returns the names (never values) of variables that were set.
    """
    if not path.is_file():
        return []
    if repo_root is not None and path.resolve().is_relative_to(repo_root.resolve()):
        if not _git_ignores(path, repo_root):
            raise ConfigError(
                f"{path.name} is not ignored by git; refusing to load secrets from it"
            )
    loaded = []
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        value = value.strip("'\"")
        if key in DOTENV_KEYS and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def load_settings(cwd: Path | None = None) -> Settings:
    cwd = cwd or Path.cwd()
    repo_root = find_repo_root(cwd)
    data_dir = Path(os.environ.get("MAMBO_DATA_DIR") or cwd / "data")
    if not data_dir.is_absolute():
        data_dir = cwd / data_dir
    return Settings(
        data_dir=validate_data_dir(data_dir, repo_root),
        api_key=os.environ.get("EIA_API_KEY") or None,
    )
