"""Navigation sections. Pure data so it can be tested without Streamlit."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    icon: str
    summary: str
    scope: tuple[str, ...]


SECTIONS: tuple[Section, ...] = (
    Section(
        key="learn",
        title="Learn",
        icon=":material/school:",
        summary="Guided lessons that follow the learning sequence, from fundamentals "
        "to integrated analysis.",
        scope=(
            "Fuel, generation, transmission, distribution, storage, and demand",
            "Weather, forecasting, reliability, planning, and interconnection",
            "Industry participants and institutional responsibilities",
            "Effective-dated lessons that record when the described rules applied",
        ),
    ),
    Section(
        key="explore",
        title="Explore",
        icon=":material/query_stats:",
        summary="Browse actual observations by region, market, and time.",
        scope=(
            "ERCOT, CAISO, PJM, MISO, SPP, NYISO, ISO-NE, and non-ISO regions",
            "Observed, derived, modeled, and synthetic labels on every value",
            "Provenance and revision history for each series",
        ),
    ),
    Section(
        key="replay",
        title="Replay",
        icon=":material/replay:",
        summary="Step through an actual operating day as it unfolded.",
        scope=(
            "Load, generation mix, prices, and constraints for a chosen day",
            "Forecast-versus-actual comparison",
            "Only recorded observations; no simulated days presented as actual",
        ),
    ),
    Section(
        key="model-labs",
        title="Model Labs",
        icon=":material/science:",
        summary="Reproducible modeling with mambo-power through a separately validated adapter.",
        scope=(
            "Adapter to mambo-power, validated independently of this application",
            "Reproducible runs with recorded inputs, versions, and parameters",
            "Model outputs labeled as modeled, never as observed",
        ),
    ),
    Section(
        key="finance",
        title="Finance",
        icon=":material/account_balance:",
        summary="Financial contracts, risk, and settlement.",
        scope=(
            "Futures, forwards, swaps, and options",
            "PPAs, tolling, capacity, storage-service, and other long-term contracts",
            "Hedging, basis and shape risk",
            "Settlement, credit, and collateral",
        ),
    ),
    Section(
        key="compliance",
        title="Compliance",
        icon=":material/gavel:",
        summary="Regulatory authorities, rules, and obligations.",
        scope=(
            "FERC, NERC and regional entities, DOE, and state PUCs/PSCs",
            "ISO/RTO rules, CFTC, and other relevant authorities",
            "Effective-dated rules with source citations",
        ),
    ),
    Section(
        key="sources",
        title="Sources",
        icon=":material/source:",
        summary="Data source register: provenance, licensing, and freshness.",
        scope=(
            "EIA as the first planned connector; operator and regulatory sources follow",
            "Access and redistribution review per source",
            "Revisions, update cadence, and known limitations",
        ),
    ),
    Section(
        key="system-health",
        title="System Health",
        icon=":material/monitor_heart:",
        summary="Local collection, storage, and model-run status.",
        scope=(
            "Collection job status and data freshness",
            "Local storage usage (DuckDB/Parquet observations, SQLite metadata)",
            "Component versions for reproducibility",
        ),
    ),
)


def section_by_key(key: str) -> Section:
    for section in SECTIONS:
        if section.key == key:
            return section
    raise KeyError(key)
