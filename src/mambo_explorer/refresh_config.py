"""Load and validate the local refresh plan (content/refresh.yaml or --config; ADR 0013).

Every number is bounded so that one refresh can never become an unbounded crawl. Source
publication cadence (text from the source review) is kept apart from the collection
interval (the owner's schedule choice). Credentials are never part of the configuration.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import yaml

from mambo_explorer.collect import MAX_DAYS_PER_RUN
from mambo_explorer.ercot.collect import MAX_DOCUMENTS_PER_RUN
from mambo_explorer.ercot.prices import MAX_DOCUMENTS_PER_RUN as PRICE_DOCS_PER_RUN

SOURCES = ("eia", "ercot", "eia-generation", "ercot-dam-spp")
# Datasets a plan may leave out; a missing section means "disabled".
OPTIONAL_SOURCES = ("eia-generation", "ercot-dam-spp")
# Which host each dataset sends requests to (shared per-host budgets).
HOSTS = {
    "eia": "api.eia.gov",
    "eia-generation": "api.eia.gov",
    "ercot": "ercot.com",
    "ercot-dam-spp": "ercot.com",
}
ENV = "MAMBO_REFRESH_CONFIG"  # optional path to a local plan (outside the repository)
# Keys that look like secrets are rejected wherever they appear.
_SECRET_KEY = re.compile(r"(?i)(api[_-]?key|token|secret|password|credential)")


class RefreshConfigError(ValueError):
    pass


@dataclass(frozen=True)
class EiaSettings:
    enabled: bool
    title: str
    publication_cadence: str
    collection_interval_hours: int
    window_days: int
    revision_lookback_days: int
    max_catchup_days: int
    request_budget: int
    freshness_threshold_hours: int


@dataclass(frozen=True)
class ErcotSettings:
    enabled: bool
    title: str
    publication_cadence: str
    collection_interval_hours: int
    window_documents: int
    revision_lookback_documents: int
    max_catchup_documents: int
    request_budget: int
    freshness_threshold_hours: int


@dataclass(frozen=True)
class RefreshConfig:
    eia: EiaSettings
    ercot: ErcotSettings
    generation: EiaSettings  # same shape as demand; disabled unless a plan enables it
    prices: ErcotSettings  # ERCOT DAM settlement point price; opt-in
    host_budgets: dict  # host -> max requests per refresh across its datasets
    log_retention_days: int
    log_max_files: int
    origin: str  # "default" or the path that was loaded

    def source(self, name: str) -> EiaSettings | ErcotSettings:
        return {
            "eia": self.eia,
            "ercot": self.ercot,
            "eia-generation": self.generation,
            "ercot-dam-spp": self.prices,
        }[name]

    def host_budget(self, host: str) -> int | None:
        return self.host_budgets.get(host)

    def eia_api_budget(self, sources: list[str]) -> int:
        """Requests the EIA API may receive from one refresh of `sources` (demand + generation)."""
        return sum(self.source(s).request_budget for s in sources if s in ("eia", "eia-generation"))

    def enabled(self) -> list[str]:
        return [s for s in SOURCES if self.source(s).enabled]


def _int(section: dict, key: str, low: int, high: int, where: str) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RefreshConfigError(f"{where}.{key} must be an integer from {low} to {high}")
    return value


def _text(section: dict, key: str, where: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RefreshConfigError(f"{where}.{key} must be non-empty text")
    return " ".join(value.split())


def _check_keys(obj, path: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if _SECRET_KEY.search(str(key)):
                raise RefreshConfigError(
                    f"{path}{key}: credentials do not belong in the refresh configuration; "
                    "the EIA key is read from EIA_API_KEY at run time"
                )
            _check_keys(value, f"{path}{key}.")


def _eia_settings(e: dict, w: str) -> EiaSettings:
    settings = EiaSettings(
        enabled=e["enabled"],
        title=_text(e, "title", w),
        publication_cadence=_text(e, "publication_cadence", w),
        collection_interval_hours=_int(e, "collection_interval_hours", 1, 24 * 31, w),
        window_days=_int(e, "window_days", 1, MAX_DAYS_PER_RUN, w),
        revision_lookback_days=_int(e, "revision_lookback_days", 0, 30, w),
        max_catchup_days=_int(e, "max_catchup_days", 1, MAX_DAYS_PER_RUN, w),
        request_budget=_int(e, "request_budget", 1, 50, w),
        freshness_threshold_hours=_int(e, "freshness_threshold_hours", 1, 24 * 60, w),
    )
    for days in (settings.window_days, settings.max_catchup_days):
        if days + settings.revision_lookback_days > MAX_DAYS_PER_RUN:
            raise RefreshConfigError(
                f"{w}: a refresh of {days} days plus {settings.revision_lookback_days} lookback "
                f"days exceeds the collector's per-run maximum of {MAX_DAYS_PER_RUN}"
            )
    return settings


def _disabled_generation() -> EiaSettings:
    """A plan without the section: the packaged defaults, but disabled."""
    packaged = yaml.safe_load(default_text())["sources"]["eia-generation"]
    return _eia_settings({**packaged, "enabled": False}, "sources.eia-generation")


def validate(data: dict, origin: str = "default") -> RefreshConfig:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise RefreshConfigError("refresh configuration needs version: 1")
    _check_keys(data)
    sources = data.get("sources")
    required = set(SOURCES) - set(OPTIONAL_SOURCES)
    if not isinstance(sources, dict) or not required <= set(sources) <= set(SOURCES):
        raise RefreshConfigError(
            f"sources must define {sorted(required)} and may add {OPTIONAL_SOURCES}"
        )
    for name, section in sources.items():
        if not isinstance(section, dict) or not isinstance(section.get("enabled"), bool):
            raise RefreshConfigError(f"sources.{name}.enabled must be true or false")

    eia = _eia_settings(sources["eia"], "sources.eia")
    generation = (
        _eia_settings(sources["eia-generation"], "sources.eia-generation")
        if "eia-generation" in sources
        else _disabled_generation()
    )

    ercot = _ercot_settings(sources["ercot"], "sources.ercot", MAX_DOCUMENTS_PER_RUN)
    prices = (
        _ercot_settings(sources["ercot-dam-spp"], "sources.ercot-dam-spp", PRICE_DOCS_PER_RUN)
        if "ercot-dam-spp" in sources
        else _disabled_prices()
    )
    hosts = data.get("hosts", {})
    if not isinstance(hosts, dict):
        raise RefreshConfigError("hosts must be a mapping")
    host_budgets = {}
    for host, section in hosts.items():
        if host not in set(HOSTS.values()) or not isinstance(section, dict):
            raise RefreshConfigError(f"hosts.{host}: unknown host or not a mapping")
        host_budgets[host] = _int(section, "max_requests_per_refresh", 1, 100, f"hosts.{host}")
    for host, cap in host_budgets.items():
        for name in SOURCES:
            settings = {
                "eia": eia,
                "ercot": ercot,
                "eia-generation": generation,
                "ercot-dam-spp": prices,
            }[name]
            if HOSTS[name] == host and settings.enabled and settings.request_budget > cap:
                raise RefreshConfigError(
                    f"sources.{name}.request_budget exceeds hosts.{host}.max_requests_per_refresh"
                )

    logs = data.get("logs")
    if not isinstance(logs, dict):
        raise RefreshConfigError("logs section is required")
    return RefreshConfig(
        eia=eia,
        ercot=ercot,
        generation=generation,
        prices=prices,
        host_budgets=host_budgets,
        log_retention_days=_int(logs, "retention_days", 1, 365, "logs"),
        log_max_files=_int(logs, "max_files", 1, 10_000, "logs"),
        origin=origin,
    )


def _ercot_settings(r: dict, w: str, max_docs: int) -> ErcotSettings:
    settings = ErcotSettings(
        enabled=r["enabled"],
        title=_text(r, "title", w),
        publication_cadence=_text(r, "publication_cadence", w),
        collection_interval_hours=_int(r, "collection_interval_hours", 1, 24 * 31, w),
        window_documents=_int(r, "window_documents", 1, max_docs, w),
        revision_lookback_documents=_int(r, "revision_lookback_documents", 0, 3, w),
        max_catchup_documents=_int(r, "max_catchup_documents", 1, max_docs, w),
        request_budget=_int(r, "request_budget", 2, 30, w),
        freshness_threshold_hours=_int(r, "freshness_threshold_hours", 1, 24 * 60, w),
    )
    if settings.request_budget < 1 + settings.max_catchup_documents:
        raise RefreshConfigError(
            f"{w}.request_budget must cover 1 list request plus "
            f"{settings.max_catchup_documents} downloads"
        )
    return settings


def _disabled_prices() -> ErcotSettings:
    """A plan without the section: the packaged defaults, but disabled."""
    packaged = yaml.safe_load(default_text())["sources"]["ercot-dam-spp"]
    return _ercot_settings(
        {**packaged, "enabled": False}, "sources.ercot-dam-spp", PRICE_DOCS_PER_RUN
    )


def default_text() -> str:
    return files("mambo_explorer.content").joinpath("refresh.yaml").read_text("utf-8")


def load(path: Path | None = None) -> RefreshConfig:
    """`path`, else MAMBO_REFRESH_CONFIG, else the packaged default plan."""
    path = path or (Path(os.environ[ENV]) if os.environ.get(ENV) else None)
    if path is None:
        return validate(yaml.safe_load(default_text()), "default")
    try:
        text = Path(path).read_text("utf-8")
    except OSError as exc:
        raise RefreshConfigError(f"cannot read refresh configuration: {exc}") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RefreshConfigError(f"refresh configuration is not valid YAML: {exc}") from None
    return validate(data, str(path))
