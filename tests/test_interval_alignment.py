"""Stage 22 interval alignment: service, evidence, guards, diagnostic (offline, SYNTHETIC).

Fixtures are hand-written labels (tests/alignment_fixtures.py), never ERCOT behavior. No test
needs a credential or the network.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from datetime import date
from pathlib import Path

import alignment_fixtures as fx
import pytest
from guards import data_elements
from price_fixtures import FakePrices, day_doc
from rt_price_fixtures import FakeRt, day_docs, interval_doc
from streamlit.testing.v1 import AppTest

from mambo_explorer import alignment_view, routes
from mambo_explorer.ercot import alignment as al
from mambo_explorer.ercot import prices as px
from mambo_explorer.ercot import rt_prices as rt
from mambo_explorer.ercot.client import ErcotClient

SRC = Path(__file__).resolve().parents[1] / "src" / "mambo_explorer"
EXPLORE = "from mambo_explorer.pages import render_page\nrender_page('explore')\n"
D9 = date(2026, 3, 9)  # synthetic store date (the fixtures' own date; not ERCOT data)
LATEST, FIRST = al.LATEST_RETRIEVED, al.FIRST_RETRIEVED


def m1(case, policy=LATEST, **kw):
    dam, rts = case
    return al.check_candidate("M1", dam, rts, revision_policy=policy, **kw)


# --- the decision: no mapping is accepted ------------------------------------------------------


def test_no_candidate_is_accepted_and_align_returns_unsupported_semantics():
    assert al.accepted() is None
    res = al.align(*fx.ORDINARY, revision_policy=LATEST)
    assert res.status == al.UNSUPPORTED_SEMANTICS and not res.asserted
    assert res.matched == () and res.expected_interval_count is None
    assert "do not define" in res.reasons[0]


def test_inputs_and_policies_are_still_validated_before_semantics():
    bad = al.align(fx.dam(hour="25:00"), [], revision_policy=LATEST)
    assert bad.status == al.INVALID_INPUT
    assert al.align(*fx.ORDINARY, revision_policy="newest").status == al.INVALID_INPUT
    assert (
        al.align(*fx.ORDINARY, revision_policy=LATEST, completeness_policy="lenient").status
        == al.INVALID_INPUT
    )
    for policy in (al.LATEST_KNOWN_BEFORE, al.FINAL):
        res = al.align(*fx.ORDINARY, revision_policy=policy)
        assert res.status == al.UNAVAILABLE_REVISION
        assert res.reasons == (al.REVISION_POLICIES[policy],)


def test_rejected_candidate_is_never_evaluated():
    res = al.check_candidate("M2", *fx.ORDINARY, revision_policy=LATEST)
    assert res.status == al.UNSUPPORTED_SEMANTICS and "rejected" in res.reasons[0]


# --- candidate check (M1, not asserted) --------------------------------------------------------

EXPECTED = {
    "ORDINARY": al.ALIGNED_COMPLETE,
    "MISSING_ONE": al.ALIGNED_INCOMPLETE,
    "DUPLICATE": al.ALIGNED_INCOMPLETE,
    "CONFLICTING_REVISIONS": al.ALIGNED_COMPLETE,
    "MISMATCHED_TYPE": al.INCOMPATIBLE_IDENTITY,
    "MISMATCHED_POINT": al.INCOMPATIBLE_IDENTITY,
    "MISMATCHED_DATE": al.INCOMPATIBLE_IDENTITY,
    "HOUR_24": al.ALIGNED_COMPLETE,
    "SPRING_MISSING_HOUR": al.MISSING_REAL_TIME,
    "SPRING_NEIGHBOURS": al.ALIGNED_COMPLETE,
    "FALL_REPEATED_N": al.ALIGNED_COMPLETE,
    "FALL_REPEATED_Y": al.ALIGNED_COMPLETE,
    "DIFFERENT_FLAGS": al.AMBIGUOUS_DST,
    "UNKNOWN_FLAG": al.AMBIGUOUS_DST,
    "UNKNOWN_RT_FLAG": al.AMBIGUOUS_DST,
    "MISSING_DAM_PRICE": al.MISSING_DAY_AHEAD,
    "MISSING_ALL_RT": al.MISSING_REAL_TIME,
    "BLANK_RT_PRICE": al.ALIGNED_INCOMPLETE,
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_candidate_check_statuses_and_never_asserted(name):
    res = m1(getattr(fx, name))
    assert res.status == EXPECTED[name], (name, res.reasons)
    assert res.status in al.STATUSES
    assert res.asserted is False and res.mapping == "M1"
    assert res.mapping_status == "partially-supported"
    assert res.expected_interval_count is None  # never "verified" under a candidate
    assert res.limitations[0].startswith("Candidate check only")


def test_missing_and_blank_intervals_are_listed_never_filled():
    res = m1(fx.MISSING_ONE)
    assert res.missing_intervals == ("3",) and res.observed_interval_count == 3
    assert res.candidate_expected_count == 4
    blank = m1(fx.BLANK_RT_PRICE)
    assert any("blank" in r for r in blank.reasons) and blank.observed_interval_count == 4


def test_duplicate_with_equal_revision_is_not_harmless():
    res = m1(fx.DUPLICATE)
    assert res.duplicate_intervals and "H5 I3" in res.duplicate_intervals[0]
    assert "3" in res.missing_intervals  # the unresolved interval does not count as present


def test_conflicting_revisions_resolve_only_through_the_named_policy():
    latest, first = m1(fx.CONFLICTING_REVISIONS), m1(fx.CONFLICTING_REVISIONS, FIRST)
    for res, chosen in ((latest, 2), (first, 1)):
        (conflict,) = res.revision_conflicts
        assert conflict["revisions"] == [1, 2] and conflict["selected"] == chosen
        i2 = next(m for m in res.matched if m["DeliveryInterval"] == "2")
        assert i2["revision"] == chosen
        assert res.dst["real_time_same_flag"] == 4  # distinct intervals, not revisions
    known = al.check_candidate(
        "M1", *fx.CONFLICTING_REVISIONS, revision_policy=al.LATEST_KNOWN_BEFORE
    )
    assert known.status == al.UNAVAILABLE_REVISION


def test_day_ahead_revisions_follow_the_policy():
    dam1, dam2 = fx.dam(rev=1), fx.dam(rev=2, present=False)
    rts = fx.hour_of()
    latest = al.check_candidate("M1", dam1, rts, revision_policy=LATEST, dam_revisions=[dam2])
    first = al.check_candidate("M1", dam1, rts, revision_policy=FIRST, dam_revisions=[dam2])
    assert latest.status == al.MISSING_DAY_AHEAD and latest.dam_revision["revision"] == 2
    assert first.status == al.ALIGNED_COMPLETE and first.dam_revision["revision"] == 1
    bare = al.check_candidate("M1", fx.dam().hour, rts, revision_policy=LATEST)
    assert bare.status == al.MISSING_DAY_AHEAD


def test_source_native_identities_are_preserved():
    res = m1(fx.HOUR_24)
    assert res.dam_identity == {
        "DeliveryDate": fx.DAY,
        "HourEnding": "24:00",
        "SettlementPoint": "HB_NORTH",
        "LocationType": "hub",
        "DSTFlag": "N",
    }
    assert {m["DeliveryHour"] for m in res.matched} == {"24"}  # never rewritten as hour 00
    assert {m["DeliveryDate"] for m in res.matched} == {fx.DAY}  # never moved to the next date
    assert [m["DeliveryInterval"] for m in res.matched] == ["1", "2", "3", "4"]


def test_repeated_fall_hour_stays_two_distinct_hours():
    n, y = m1(fx.FALL_REPEATED_N), m1(fx.FALL_REPEATED_Y)
    assert {m["DSTFlag"] for m in n.matched} == {"N"} and {m["DSTFlag"] for m in y.matched} == {"Y"}
    assert len(n.excluded) == 4 and {x["reason"] for x in n.excluded} == {"other DSTFlag"}
    assert n.dst == {"day_ahead": "N", "real_time_same_flag": 4, "real_time_other_flag": ["Y"]}


def test_dst_flag_is_never_rewritten_to_force_a_match():
    res = m1(fx.DIFFERENT_FLAGS)
    assert res.matched == () and "never rewritten" in res.reasons[0]
    assert {x["DSTFlag"] for x in res.excluded} == {"Y"} and len(res.excluded) == 4  # kept visible
    assert "undocumented" in m1(fx.UNKNOWN_RT_FLAG).reasons[0]


def test_unexpected_interval_label_is_not_absorbed():
    res = m1((fx.dam(), fx.hour_of() + [fx.rt("5", "5")]))
    assert res.status == al.ALIGNED_INCOMPLETE and "outside the verified set" in res.reasons[-1]


def test_select_revision_rejects_unsupported_policies():
    with pytest.raises(ValueError):
        al.select_revision([fx.rt()], al.FINAL)
    assert al.select_revision([], LATEST) == (None, [])


# --- evidence record -------------------------------------------------------------------------


def test_evidence_record_is_complete_and_classified():
    ids = {e.id for e in al.EVIDENCE}
    assert len(ids) == len(al.EVIDENCE)
    assert {e.kind for e in al.EVIDENCE} <= {"official", "actual-file", "inaccessible"}
    for e in al.EVIDENCE:
        assert e.title and e.location.startswith("https://") and e.retrieved
        assert e.proposition and e.ambiguity
    for c in al.CANDIDATES:
        assert set(c.supporting) | set(c.contradicting) <= ids
        assert c.status in ("accepted", "partially-supported", "rejected", "not-supported")
        assert c.review == "AI-authored; not human-reviewed"
    m1c = al.candidate("M1")
    kinds = {al.evidence(e).kind for e in m1c.supporting}
    assert kinds == {"official", "actual-file"}  # never synthetic
    assert any("not defined officially" in a for a in m1c.assumptions)


def test_no_synthetic_fixture_is_cited_as_evidence():
    text = " ".join(dataclasses.astuple(e).__repr__() for e in al.EVIDENCE)
    assert "SYN-" not in text and "2030" not in text


# --- no price, spread, aggregate, or clock time leaks ------------------------------------------


def test_result_carries_no_price_value():
    names = {f.name for f in dataclasses.fields(al.AlignmentResult)}
    assert not names & {"price", "value", "spread", "dart", "mean", "average", "hourly_price"}
    res = m1(fx.CONFLICTING_REVISIONS)

    def walk(x):
        if isinstance(x, float):
            raise AssertionError(f"float in result: {x}")
        if isinstance(x, dict):
            for k, v in x.items():
                assert not re.search(r"spread|dart|avg|mean|utc", str(k), re.I), k
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    walk(dataclasses.asdict(res))
    for cls in (al.DamObservation, al.RtObservation):
        assert "value" not in {f.name for f in dataclasses.fields(cls)}


ALIGN_MODULES = ("ercot/alignment.py", "alignment_view.py")


def _code_without_docstrings(path: Path) -> ast.Module:
    return ast.parse(path.read_text("utf-8"))


def test_guard_no_dart_spread_or_hourly_rt_aggregate_in_production_code():
    pattern = re.compile(r"\bdart_|spread\s*=|def\s+\w*(spread|dart)|hourly_rt|rt_hourly", re.I)
    sql_agg = re.compile(r"\b(AVG|MEAN|SUM)\s*\(\s*value\b", re.I)
    for path in SRC.rglob("*.py"):
        text = path.read_text("utf-8")
        assert not pattern.search(text), path
        assert not sql_agg.search(text), path


def test_guard_alignment_modules_derive_no_clock_time_or_utc():
    banned = re.compile(r"astimezone|zoneinfo|ZoneInfo|timedelta|tz_convert|pytz|datetime")
    for rel in ALIGN_MODULES:
        code = "\n".join(
            line for line in (SRC / rel).read_text("utf-8").splitlines() if "import" in line
        )
        assert not banned.search(code), rel
        tree = _code_without_docstrings(SRC / rel)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not names & {"astimezone", "ZoneInfo", "timedelta", "datetime", "UTC"}, rel


def test_guard_no_hardcoded_four_interval_rule():
    """The only source of '4 intervals' is a candidate's evidence-backed expected_intervals."""
    for rel in ALIGN_MODULES:
        tree = _code_without_docstrings(SRC / rel)
        allowed = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "expected_intervals":
                allowed |= {id(n) for n in ast.walk(node.value)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and id(node) not in allowed:
                assert node.value not in (4, 4.0, 0.25, "4"), (rel, node.lineno)
    m1c = al.candidate("M1")
    assert m1c.expected_intervals == ("1", "2", "3", "4")
    assert {"OFF-2", "OFF-3"} <= set(m1c.supporting)  # 15-minute intervals, a quarter of an hour


def test_existing_collectors_keep_their_identities():
    assert px.IDENTITY == (
        "source", "dataset", "market_stage", "location", "delivery_date_raw", "hour_ending",
        "dst_flag",
    )  # fmt: skip
    assert rt.IDENTITY == (
        "source", "dataset", "market_stage", "location", "delivery_date_raw", "delivery_hour",
        "delivery_interval", "dst_flag",
    )  # fmt: skip


# --- diagnostic page (synthetic stores) -------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("MAMBO_DATA_DIR", str(path))
    monkeypatch.setattr(routes, "PAGES", {})
    return path


def fill_dam(data_dir):
    docs = dict([day_doc(D9, "501")])
    c = ErcotClient(transport=FakePrices(docs), sleep=lambda s: None, max_requests=6)
    px.collect(px.Selection(latest=1), c, px.store(data_dir))


def fill_rt(data_dir, docs):
    c = ErcotClient(transport=FakeRt(docs), sleep=lambda s: None, max_requests=16)
    rt.collect(rt.Selection(12, False), c, rt.store(data_dir))


def _texts(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    for group in (at.info, at.success, at.warning, at.error):
        parts += [x.value for x in group]
    return "\n".join(parts)


def _page(**state):
    at = AppTest.from_string(EXPLORE)
    at.session_state["explore_source"] = "ercot-alignment"
    for k, v in state.items():
        at.session_state[k] = v
    return at.run(timeout=30)


def test_diagnostic_empty_state_reads_nothing_and_creates_nothing(data_dir):
    at = _page()
    assert not at.exception and not data_elements(at)
    text = _texts(at)
    assert "No DART spread" in text and "No day-ahead or real-time prices" in text
    assert "Accepted mapping: **none**" in text
    assert not data_dir.exists() or not any(data_dir.rglob("*.parquet"))


def test_diagnostic_default_is_unsupported_and_candidate_check_is_labelled(data_dir):
    fill_dam(data_dir)
    fill_rt(data_dir, day_docs(D9, hours=(3,)))
    at = _page()
    assert not at.exception and not data_elements(at)
    assert at.selectbox(key="align_day").value == "03/09/2026"
    assert at.selectbox(key="align_hour").value.hour_ending == "01:00"
    text = _texts(at)
    assert "unsupported_semantics" in text and "Not asserted" in text
    assert "No DART spread" in text
    assert "M1" in text and "partially-supported" in text


def test_diagnostic_candidate_states(data_dir):
    fill_dam(data_dir)
    docs = day_docs(D9, hours=(3,))
    docs.update(dict([interval_doc(D9, 4, 1, "7100"), interval_doc(D9, 4, 2, "7101")]))
    fill_rt(data_dir, docs)
    dam, rtl = alignment_view.load_day(data_dir, "03/09/2026")
    assert len(dam) == 24 and len(rtl) == 6
    assert all(not hasattr(o, "value") for o in dam + rtl)
    h3 = next(o.hour for o in dam if o.hour.hour_ending == "03:00")
    h4 = next(o.hour for o in dam if o.hour.hour_ending == "04:00")
    h5 = next(o.hour for o in dam if o.hour.hour_ending == "05:00")
    for hour, status in (
        (h3, "aligned_complete"),
        (h4, "aligned_incomplete"),
        (h5, "missing_real_time"),
    ):
        at = _page(align_hour=hour, align_candidate=True)
        assert not at.exception and not data_elements(at)
        text = _texts(at)
        assert f"Not asserted — **{status}**" in text, status
        assert "unsupported_semantics" in text  # the asserted result stays unsupported
        tables = [t.value for t in at.table]
        assert any("DeliveryInterval" in t.columns for t in tables) or status == "missing_real_time"
    at = _page(align_hour=h3, align_policy=al.FINAL, align_candidate=True)
    assert "unavailable_revision" in _texts(at)


def test_changing_the_hour_offers_that_hours_intervals_not_a_stale_selection(data_dir):
    """Browser regression (Stage 22): the real-time picker kept the previous hour's selection."""
    fill_dam(data_dir)
    fill_rt(data_dir, day_docs(D9, hours=(3,)))
    at = _page(align_candidate=True)  # first render: hour 01:00, no real-time intervals
    assert "Not asserted — **missing_real_time**" in _texts(at)
    dam, _ = alignment_view.load_day(data_dir, "03/09/2026")
    at.selectbox(key="align_hour").set_value(
        next(o.hour for o in dam if o.hour.hour_ending == "03:00")
    )
    at.run(timeout=30)
    assert "Not asserted — **aligned_complete**" in _texts(at)
