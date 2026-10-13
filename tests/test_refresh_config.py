"""Refresh plan configuration: defaults, bounds, credentials, override (offline)."""

import pytest
import yaml
from refresh_helpers import config

from mambo_explorer import refresh_config as rc
from mambo_explorer.collect import MAX_DAYS_PER_RUN
from mambo_explorer.ercot.collect import MAX_DOCUMENTS_PER_RUN


def test_default_plan_is_valid_bounded_and_keeps_cadence_apart_from_schedule():
    c = rc.load()
    assert c.origin == "default" and c.enabled() == ["eia", "ercot"]
    assert c.eia.max_catchup_days + c.eia.revision_lookback_days <= MAX_DAYS_PER_RUN
    assert c.ercot.max_catchup_documents <= MAX_DOCUMENTS_PER_RUN
    assert c.ercot.request_budget >= 1 + c.ercot.max_catchup_documents
    for s in (c.eia, c.ercot):
        assert s.collection_interval_hours == 24
        assert "real-time" not in s.publication_cadence.lower()
    assert "31 days" in c.ercot.publication_cadence and "3 days" in c.eia.publication_cadence


@pytest.mark.parametrize(
    "change, message",
    [
        ({"sources__eia__window_days": 0}, "window_days"),
        ({"sources__eia__max_catchup_days": 30}, "exceeds the collector's per-run maximum"),
        ({"sources__eia__request_budget": 500}, "request_budget"),
        ({"sources__eia__enabled": "yes"}, "enabled"),
        ({"sources__ercot__max_catchup_documents": 8}, "max_catchup_documents"),
        ({"sources__ercot__request_budget": 5}, "1 list request"),
        ({"sources__ercot__freshness_threshold_hours": 0}, "freshness_threshold_hours"),
        ({"logs__retention_days": 0}, "retention_days"),
        ({"sources__eia__publication_cadence": "  "}, "publication_cadence"),
    ],
)
def test_out_of_bounds_values_are_rejected(change, message):
    with pytest.raises(rc.RefreshConfigError, match=message):
        config(**change)


@pytest.mark.parametrize("key", ["api_key", "EIA_API_KEY", "token", "password"])
def test_credentials_are_refused_anywhere_in_the_plan(key):
    data = yaml.safe_load(rc.default_text())
    data["sources"]["eia"][key] = "anything"
    with pytest.raises(rc.RefreshConfigError, match="credentials do not belong"):
        rc.validate(data)


def test_unknown_or_missing_sources_are_rejected():
    data = yaml.safe_load(rc.default_text())
    data["sources"]["caiso"] = data["sources"]["eia"]
    with pytest.raises(rc.RefreshConfigError, match="exactly"):
        rc.validate(data)


def test_override_by_path_and_environment(tmp_path, monkeypatch):
    data = yaml.safe_load(rc.default_text())
    data["sources"]["ercot"]["enabled"] = False
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(data), "utf-8")
    assert rc.load(path).enabled() == ["eia"]
    monkeypatch.setenv(rc.ENV, str(path))
    assert rc.load().origin == str(path)
    path.write_text("version: [", "utf-8")
    with pytest.raises(rc.RefreshConfigError, match="not valid YAML"):
        rc.load(path)
    with pytest.raises(rc.RefreshConfigError, match="cannot read"):
        rc.load(tmp_path / "missing.yaml")
