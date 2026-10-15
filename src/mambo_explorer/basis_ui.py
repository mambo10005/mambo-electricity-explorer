"""Basis-exposure calculator (Finance page and lesson 9). Inputs are SYNTHETIC; the two
location prices may optionally come, together, from ONE verified economic-dispatch run and
are then labeled MODELED. The fixed price K is always synthetic. Nothing is stored except
the lesson's normal progress, and observation storage is never touched.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer import basis as bx
from mambo_explorer import settlement as sm
from mambo_explorer.opf_lab import md_dollars
from mambo_explorer.settlement_ui import _fmt, _key, verified_runs

DEFAULTS = {"q": 100.0, "h": 80.0, "p_l": 60.0, "p_h": 50.0, "k": 40.0}
UNITS = [
    {"Quantity": "Q physical energy, H hedge quantity", "Unit": "MWh", "Note": "nonnegative"},
    {"Quantity": "P_L, P_H, K prices", "Unit": "synthetic $/MWh", "Note": "may be negative"},
    {"Quantity": "Basis = P_L − P_H", "Unit": "synthetic $/MWh", "Note": "this app's sign"},
    {"Quantity": "Costs, receipts, components", "Unit": "synthetic $", "Note": "MWh × $/MWh"},
]
FERC_GLOSSARY = (
    "[FERC, market-assessment glossary: Basis, Swaps, Hedging]"
    "(https://www.ferc.gov/industries-data/market-assessments/overview/glossary)"
)


def _init(prefix: str) -> None:
    for name, value in DEFAULTS.items():
        st.session_state.setdefault(_key(prefix, name), value)


def _source(prefix: str, field: str, value: float) -> sm.PriceSource:
    stored = st.session_state.get(_key(prefix, f"src_{field}"))
    if stored and abs(stored[0] - value) < 1e-9:
        return stored[1]
    st.session_state.pop(_key(prefix, f"src_{field}"), None)  # edited: synthetic again
    return sm.PriceSource()


def _import_section(prefix: str, runs_store) -> None:
    with st.expander("Optional: use two verified prices from one teaching-model run (modeled)"):
        st.markdown(
            "Copy the modeled nodal prices of **two different buses** from **one** verified "
            "economic-dispatch run into P_L and P_H. Both come from the same modeled state, "
            "so their difference is a modeled basis. Buses A, B, and C are synthetic, not "
            "market hubs. The fixed price K is never taken from a run. Runs whose prices were "
            "withheld, or that failed or are out of date, are not offered."
        )
        runs = verified_runs(runs_store)
        if not runs:
            st.info(
                "No verified economic-dispatch runs are available. Run one in Model Labs or a "
                "market-mechanics lesson first. Manual synthetic prices always work."
            )
            return
        by_id = {r.run_id: r for r in runs}
        run_id = st.selectbox(
            "Verified run",
            list(by_id),
            format_func=lambda i: (
                f"{i[-8:]} · demand {by_id[i].inputs['load_c']:g} MW, AC rating "
                f"{by_id[i].inputs['rating_ac']:g} MW, offers {by_id[i].inputs['cost_g1']:g}/"
                f"{by_id[i].inputs['cost_g2']:g}"
            ),
            key=_key(prefix, "imp_run"),
        )
        delivery = st.radio(
            "Delivery bus (P_L)",
            ["A", "B", "C"],
            index=2,
            horizontal=True,
            key=_key(prefix, "imp_l"),
        )
        reference = st.radio(
            "Hedge reference bus (P_H)", ["A", "B", "C"], horizontal=True, key=_key(prefix, "imp_h")
        )
        if st.button("Use these two modeled prices", key=_key(prefix, "imp_go")):
            try:
                (p_l, src_l), (p_h, src_h) = bx.modeled_pair(by_id[run_id], delivery, reference)
            except sm.SettlementError as exc:
                st.error(str(exc))
                return
            for field, price, src in (("p_l", p_l, src_l), ("p_h", p_h, src_h)):
                st.session_state[_key(prefix, f"src_{field}")] = (price, src)
                st.session_state[_key(prefix, f"pending_{field}")] = price
            st.rerun()


def render_basis_calculator(prefix: str, runs_store=None) -> bx.Result | None:
    _init(prefix)
    for field in ("p_l", "p_h"):
        pending = st.session_state.pop(_key(prefix, f"pending_{field}"), None)
        if pending is not None:
            st.session_state[_key(prefix, field)] = pending
    st.markdown(
        md_dollars(
            "**Teaching transactions** (synthetic; one interval):\n\n"
            "- physical purchase cost = Q × P_L (energy bought at delivery location L)\n"
            "- hedge receipt = H × (P_H − K) (the buyer pays fixed K and receives the floating "
            "reference price P_H on H MWh; negative = the buyer pays)\n"
            "- net buyer cost = Q × P_L − H × (P_H − K) (negative = a credit to the buyer)\n\n"
            "The hedge is financial and delivers no electricity."
        )
    )
    lo, hi = bx.QUANTITY_BOUNDS_MWH
    plo, phi = bx.PRICE_BOUNDS
    # Draw every widget before calculating, so an invalid input never resets the others.
    q = st.number_input(
        "Q: physical energy bought at L (MWh)", lo, hi, step=10.0, key=_key(prefix, "q")
    )
    h = st.number_input("H: hedge quantity (MWh)", lo, hi, step=10.0, key=_key(prefix, "h"))
    p_l = st.number_input(
        "P_L: delivery-location price (synthetic $/MWh)",
        plo,
        phi,
        step=1.0,
        key=_key(prefix, "p_l"),
    )
    p_h = st.number_input(
        "P_H: hedge-reference price (synthetic $/MWh)", plo, phi, step=1.0, key=_key(prefix, "p_h")
    )
    k = st.number_input(
        "K: fixed hedge price, a synthetic assumption ($/MWh)",
        plo,
        phi,
        step=1.0,
        key=_key(prefix, "k"),
    )
    _import_section(prefix, runs_store)
    try:
        result = bx.evaluate(
            bx.Inputs(
                physical_mwh=q,
                hedge_mwh=h,
                delivery_price=p_l,
                reference_price=p_h,
                fixed_price=k,
                delivery_source=_source(prefix, "p_l", p_l),
                reference_source=_source(prefix, "p_h", p_h),
            )
        )
    except sm.SettlementError as exc:
        st.error(f"Cannot calculate: {exc}. No result is shown.")
        return None
    _show(result)
    return result


def _label(src: dict) -> str:
    return (
        f"modeled (run {src['run_id'][-8:]}, bus {src['bus']})"
        if src["kind"] == "modeled"
        else "synthetic"
    )


def _show(r: bx.Result) -> None:
    i = r.inputs
    st.subheader("Cash flows (synthetic teaching calculation)")
    st.markdown(
        md_dollars(
            f"Basis = P_L − P_H = **{_fmt(r.basis)} synthetic $/MWh**. Position: {r.position}."
        )
    )
    st.table(
        [
            {
                "Item": "Physical purchase cost",
                "Formula": "Q × P_L",
                "Amount ($)": _fmt(r.physical_cost),
            },
            {
                "Item": "Hedge receipt",
                "Formula": "H × (P_H − K)",
                "Amount ($)": _fmt(r.hedge_receipt),
            },
            {"Item": "Net buyer cost", "Formula": "cost − receipt", "Amount ($)": _fmt(r.net_cost)},
        ],
        hide_index=True,
    )
    st.table(
        [
            {"Item": "Hedge receipt", "Reading": r.hedge_reading()},
            {"Item": "Net buyer cost", "Reading": r.net_reading()},
        ],
        hide_index=True,
    )
    st.markdown("**Where the net cost comes from**")
    st.table(
        [
            {"Component": "Fixed price", "Formula": "Q × K", "Amount ($)": _fmt(r.fixed_component)},
            {
                "Component": "Location basis",
                "Formula": "Q × (P_L − P_H)",
                "Amount ($)": _fmt(r.basis_component),
            },
            {
                "Component": "Quantity mismatch",
                "Formula": "(Q − H) × (P_H − K)",
                "Amount ($)": _fmt(r.mismatch_component),
            },
            {"Component": "Sum = net buyer cost", "Formula": "—", "Amount ($)": _fmt(r.net_cost)},
        ],
        hide_index=True,
    )
    unhedged = i["physical_mwh"] * i["delivery_price"]
    change = r.net_cost - unhedged
    if change > 0:
        effect = (
            f"In this scenario the hedge **raised** the buyer's cost by {_fmt(change)} synthetic $."
        )
    elif change < 0:
        effect = (
            f"In this scenario the hedge **lowered** the buyer's cost by {_fmt(-change)} "
            "synthetic $."
        )
    else:
        effect = "In this scenario the hedge did not change the buyer's cost."
    st.markdown(
        md_dollars(
            f"Without the hedge the cost would be Q × P_L = {_fmt(unhedged)} synthetic $. "
            f"{effect} A hedge changes exposure; it does not guarantee savings."
        )
    )
    with st.expander("Units, assumptions, sources, and provenance"):
        st.table(UNITS, hide_index=True)
        prov = (
            f"Formula v{r.formula_version}; calculation id `{r.snapshot_id}`. P_L: "
            f"{_label(i['delivery_source'])}. P_H: {_label(i['reference_source'])}. K: synthetic."
        )
        for name, src in (("P_L", i["delivery_source"]), ("P_H", i["reference_source"])):
            if src["kind"] == "modeled":
                prov += (
                    f"\n\n{name}: run `{src['run_id']}`, {src['scenario']}, bus {src['bus']}, "
                    f"{src['package']}, checks v{src['checks_version']}, price "
                    f"{src['verification']} "
                    "by the per-run check. A synthetic teaching-network bus, not a market hub."
                )
        st.markdown(md_dollars(prov))
        st.markdown(md_dollars("\n".join(f"- {a}" for a in r.assumptions)))
        st.markdown(f"- {FERC_GLOSSARY} (supports the concepts only)")
