"""Energy-settlement calculator (shared by the Finance page and the settlement lesson).

Inputs are SYNTHETIC unless the learner explicitly imports one verified teaching-model
price, which is then labeled MODELED with its run provenance. Nothing is stored except
the lesson's own progress; nothing touches observation storage. Every rerun recomputes
from the current inputs, so an invalid input shows an error and no numbers at all.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer import settlement as sm
from mambo_explorer.opf_lab import md_dollars

CUR = sm.CURRENCY
DEFAULTS = {
    "q_da": 100.0,
    "q_rt": 120.0,
    "p_da": 40.0,
    "p_rt": 55.0,
    "mw_da": 100.0,
    "mw_rt": 120.0,
}
UNITS = [
    {"Quantity": "Scheduled and actual energy", "Unit": "MWh", "Note": "energy, not power"},
    {"Quantity": "Average power (optional entry)", "Unit": "MW", "Note": "× duration (h) = MWh"},
    {
        "Quantity": "Day-ahead and real-time prices",
        "Unit": "synthetic $/MWh",
        "Note": "may be negative",
    },
    {"Quantity": "Components and total", "Unit": "synthetic $", "Note": "MWh × $/MWh"},
    {"Quantity": "Deviation", "Unit": "MWh", "Note": "actual − scheduled"},
]
SOURCE_LABELS = {
    "iso-ne-da-rt-markets": "[ISO New England, Day-Ahead and Real-Time Energy Markets]"
    "(https://www.iso-ne.com/markets-operations/markets/da-rt-energy-markets)",
    "iso-ne-da-energy-bill": "[ISO New England, bill item: Day-Ahead (DA) Energy]"
    "(https://www.iso-ne.com/markets-operations/settlements/understand-bill/item-descriptions/da-energy)",
    "iso-ne-rt-energy-bill": "[ISO New England, bill item: Real-Time (RT) Energy]"
    "(https://www.iso-ne.com/markets-operations/settlements/understand-bill/item-descriptions/rt-energy)",
}


def _fmt(x: float) -> str:
    x = round(x, 2) + 0.0
    return f"{x:,.2f}".replace("-", "−")


def _signed_mwh(x: float) -> str:
    x = round(x, 3) + 0.0
    return ("+" if x > 0 else "") + f"{x:,.3f}".rstrip("0").rstrip(".").replace("-", "−")


def _key(prefix: str, name: str) -> str:
    return f"{prefix}_{name}"


def _init(prefix: str) -> None:
    for name, value in DEFAULTS.items():
        st.session_state.setdefault(_key(prefix, name), value)


# --- modeled-price import ------------------------------------------------------------------


def verified_runs(runs_store) -> list:
    """Economic-dispatch runs whose prices can be imported (verified, current, pinned)."""
    candidates = list(st.session_state.get("model_runs", {}).values())
    if runs_store is not None:
        try:
            candidates += runs_store.recent(30, kind="opf.dc")
        except Exception:  # an unreadable saved run never blocks the calculator
            pass
    seen, out = set(), []
    for record in candidates:
        if record.run_id in seen:
            continue
        seen.add(record.run_id)
        try:
            sm.modeled_price(record, "A")
        except sm.SettlementError:
            continue
        out.append(record)
    return out


def _import_section(prefix: str, runs_store) -> None:
    with st.expander("Optional: use a verified teaching-model price (modeled input)"):
        st.markdown(
            "You can copy **one** modeled nodal price from a verified economic-dispatch run into "
            "**one** price field. It stays labeled **modeled** with its run id. It is a scenario "
            "input from a synthetic teaching network, not an ISO price, and one run is never "
            "used for both the day-ahead and the real-time price. Runs whose prices were "
            "withheld, or that failed or are out of date, are not offered."
        )
        runs = verified_runs(runs_store)
        if not runs:
            st.info(
                "No verified economic-dispatch runs are available yet. Run one in Model Labs or "
                "in a market-mechanics lesson first. Manual synthetic prices always work."
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
        bus = st.radio("Bus", ["A", "B", "C"], horizontal=True, key=_key(prefix, "imp_bus"))
        stage = st.radio(
            "Use it as",
            ["day-ahead price", "real-time price"],
            horizontal=True,
            key=_key(prefix, "imp_stage"),
        )
        if st.button("Use this modeled price", key=_key(prefix, "imp_go")):
            try:
                price, source = sm.modeled_price(by_id[run_id], bus)
            except sm.SettlementError as exc:
                st.error(str(exc))
                return
            field = "p_da" if stage.startswith("day") else "p_rt"
            st.session_state[_key(prefix, f"src_{field}")] = (price, source)
            st.session_state[_key(prefix, f"pending_{field}")] = price
            st.rerun()


def _source(prefix: str, field: str, value: float) -> sm.PriceSource:
    """The modeled provenance only while the field still holds the imported value."""
    stored = st.session_state.get(_key(prefix, f"src_{field}"))
    if stored and abs(stored[0] - value) < 1e-9:
        return stored[1]
    st.session_state.pop(_key(prefix, f"src_{field}"), None)
    return sm.PriceSource()


# --- calculator -----------------------------------------------------------------------------


def render_calculator(prefix: str, runs_store=None) -> sm.Result | None:
    _init(prefix)
    for field in ("p_da", "p_rt"):  # apply an import before the widget is drawn
        pending = st.session_state.pop(_key(prefix, f"pending_{field}"), None)
        if pending is not None:
            st.session_state[_key(prefix, field)] = pending

    st.markdown(
        md_dollars(
            "**Teaching formula** (one location, one interval, energy only):\n\n"
            "- day-ahead component = scheduled energy (MWh) × day-ahead price ($/MWh)\n"
            "- deviation component = (actual − scheduled energy) (MWh) × real-time price ($/MWh)\n"
            "- energy settlement = day-ahead component + deviation component\n\n"
            "The total is one **signed** amount: a **buyer pays** it and a **seller receives** "
            "it. A negative amount is a credit to a buyer (or a payment by a seller) under "
            "these teaching assumptions."
        )
    )
    mode = st.radio(
        "Enter quantities as",
        ["energy (MWh)", "average power (MW) × duration"],
        horizontal=True,
        key=_key(prefix, "mode"),
    )
    # Draw every widget before calculating: a widget skipped by an early error would lose
    # its value (Streamlit drops state for widgets not drawn in a run).
    lo, hi = sm.ENERGY_BOUNDS_MWH
    hours = mw_da = mw_rt = q_da = q_rt = None
    if mode.startswith("energy"):
        q_da = st.number_input(
            "Day-ahead scheduled energy (MWh)", lo, hi, step=10.0, key=_key(prefix, "q_da")
        )
        q_rt = st.number_input("Actual energy (MWh)", lo, hi, step=10.0, key=_key(prefix, "q_rt"))
    else:
        plo, phi = sm.POWER_BOUNDS_MW
        hours = st.number_input(
            "Duration (hours) — required to turn MW into MWh",
            0.0,
            sm.DURATION_BOUNDS_H[1],
            value=None,
            step=0.25,
            key=_key(prefix, "hours"),
            placeholder="enter hours",
        )
        mw_da = st.number_input(
            "Day-ahead scheduled average power (MW)", plo, phi, step=10.0, key=_key(prefix, "mw_da")
        )
        mw_rt = st.number_input(
            "Actual average power (MW)", plo, phi, step=10.0, key=_key(prefix, "mw_rt")
        )
    plo, phi = sm.PRICE_BOUNDS
    p_da = st.number_input(
        "Day-ahead price (synthetic $/MWh)", plo, phi, step=1.0, key=_key(prefix, "p_da")
    )
    p_rt = st.number_input(
        "Real-time price (synthetic $/MWh)", plo, phi, step=1.0, key=_key(prefix, "p_rt")
    )
    _import_section(prefix, runs_store)
    try:
        if not mode.startswith("energy"):
            q_da, q_rt = sm.energy_from_power(mw_da, hours), sm.energy_from_power(mw_rt, hours)
            st.caption(f"Energy: {q_da:,.3f} MWh scheduled, {q_rt:,.3f} MWh actual.")
        inputs = sm.Inputs(
            scheduled_energy_mwh=q_da,
            actual_energy_mwh=q_rt,
            day_ahead_price=p_da,
            real_time_price=p_rt,
            day_ahead_source=_source(prefix, "p_da", p_da),
            real_time_source=_source(prefix, "p_rt", p_rt),
        )
        result = sm.settle(inputs)
    except sm.SettlementError as exc:
        st.error(f"Cannot calculate: {exc}. No result is shown.")
        return None
    _show(result)
    return result


def _price_label(source: dict) -> str:
    if source["kind"] == "modeled":
        return f"modeled (run {source['run_id'][-8:]}, bus {source['bus']})"
    return "synthetic"


def _show(r: sm.Result) -> None:
    i = r.inputs
    st.subheader("Result (synthetic teaching calculation)")
    st.table(
        [
            {
                "Component": "Day-ahead",
                "Energy (MWh)": _signed_mwh(i["scheduled_energy_mwh"]),
                "Price ($/MWh)": _fmt(i["day_ahead_price"]),
                "Amount ($)": _fmt(r.day_ahead_component),
            },
            {
                "Component": "Deviation",
                "Energy (MWh)": _signed_mwh(r.deviation_mwh),
                "Price ($/MWh)": _fmt(i["real_time_price"]),
                "Amount ($)": _fmt(r.deviation_component),
            },
            {
                "Component": "Total",
                "Energy (MWh)": "—",
                "Price ($/MWh)": "—",
                "Amount ($)": _fmt(r.total),
            },
        ],
        hide_index=True,
    )
    st.table(
        [
            {"Role": "Buyer", "Reading of the total": r.buyer_reading()},
            {"Role": "Seller", "Reading of the total": r.seller_reading()},
        ],
        hide_index=True,
    )
    with st.expander("Units, assumptions, sources, and provenance"):
        st.table(UNITS, hide_index=True)
        prov = (
            f"Formula v{r.formula_version}; calculation id `{r.snapshot_id}`. Day-ahead price: "
            f"{_price_label(i['day_ahead_source'])}. Real-time price: "
            f"{_price_label(i['real_time_source'])}."
        )
        for stage, src in (
            ("Day-ahead", i["day_ahead_source"]),
            ("Real-time", i["real_time_source"]),
        ):
            if src["kind"] == "modeled":
                prov += (
                    f"\n\n{stage} modeled price: run `{src['run_id']}`, {src['scenario']}, bus "
                    f"{src['bus']}, {src['package']}, checks v{src['checks_version']}, price "
                    f"{src['verification']} by the per-run check. A synthetic teaching-network "
                    "price, not an ISO price."
                )
        st.markdown(md_dollars(prov))
        st.markdown(md_dollars("\n".join(f"- {a}" for a in r.assumptions)))
        st.markdown(
            "\n".join(
                f"- {SOURCE_LABELS[s]} (supports the two-settlement idea only)" for s in r.sources
            )
        )
