"""Time-shape calculator (Finance page and lesson 10). SYNTHETIC intervals only.

Editing uses ordinary, keyboard-accessible widgets (pick an interval, edit its numbers)
rather than a canvas data grid, and results are HTML tables. A narrow one-interval viewer
is provided because the full interval table is wide. Nothing is stored except the lesson's
normal progress; observation storage is never touched, and no model run is imported.
"""

from __future__ import annotations

import streamlit as st

from mambo_explorer import settlement as sm
from mambo_explorer import shape as sh
from mambo_explorer.opf_lab import md_dollars
from mambo_explorer.settlement_ui import _fmt

UNITS = [
    {"Quantity": "Duration d_t", "Unit": "h", "Note": "elapsed hours, not clock times"},
    {"Quantity": "Physical energy q_t, hedge energy h_t", "Unit": "MWh", "Note": "h_t = B × d_t"},
    {
        "Quantity": "Hedge power B, average physical power",
        "Unit": "MW",
        "Note": "power, not energy",
    },
    {
        "Quantity": "Spot price p_t, fixed price K, p̄",
        "Unit": "synthetic $/MWh",
        "Note": "may be negative",
    },
    {"Quantity": "Costs, receipts, components", "Unit": "synthetic $", "Note": "MWh × $/MWh"},
]
EIA_ARTICLE = (
    "[EIA, Today in Energy: Texas Heat Wave, August 2011 (2011-09-09)]"
    "(https://www.eia.gov/todayinenergy/detail.php?id=3010)"
)


def _k(prefix: str, name: str) -> str:
    return f"{prefix}_{name}"


def _rows(prefix: str) -> list[dict]:
    return st.session_state[_k(prefix, "rows")]


def _load(prefix: str, key: str) -> None:
    _, intervals, b, k = sh.SCENARIOS[key]
    st.session_state[_k(prefix, "rows")] = [
        {"id": iv.interval_id, "d": iv.duration_h, "q": iv.energy_mwh, "p": iv.price}
        for iv in intervals
    ]
    st.session_state[_k(prefix, "b")] = b
    st.session_state[_k(prefix, "kk")] = k
    st.session_state[_k(prefix, "label")] = key
    st.session_state[_k(prefix, "rev")] = st.session_state.get(_k(prefix, "rev"), 0) + 1
    st.session_state[_k(prefix, "edit")] = 0


def _on_scenario(prefix: str) -> None:
    _load(prefix, st.session_state[_k(prefix, "scenario")])


def _mark_edited(prefix: str) -> None:
    label = st.session_state[_k(prefix, "label")]
    if not label.startswith("edited:"):
        st.session_state[_k(prefix, "label")] = f"edited:{label}"


def _on_field(prefix: str, idx: int, field: str, widget_key: str) -> None:
    rows = _rows(prefix)
    value = st.session_state[widget_key]
    if value is None:
        return
    if field == "mw":  # average power over the interval's explicit duration → MWh
        try:
            rows[idx]["q"] = sh.energy_from_power(value, rows[idx]["d"])
        except sm.SettlementError:
            rows[idx]["q"] = float("nan")  # refused by validation: no result is shown
    elif field == "d" and st.session_state.get(_k(prefix, "mode"), "").startswith("average"):
        old = rows[idx]["d"]
        mw = rows[idx]["q"] / old if old else 0.0
        rows[idx]["d"] = value
        rows[idx]["q"] = mw * value  # keep the entered MW; energy follows the duration
    else:
        rows[idx][field] = value
    _mark_edited(prefix)


def _on_hedge(prefix: str) -> None:
    _mark_edited(prefix)


def _add(prefix: str) -> None:
    rows = _rows(prefix)
    if len(rows) < sh.MAX_INTERVALS:
        used = {r["id"] for r in rows}
        n = len(rows) + 1
        while f"t{n}" in used:
            n += 1
        rows.append({**rows[-1], "id": f"t{n}"})
        st.session_state[_k(prefix, "edit")] = len(rows) - 1
        st.session_state[_k(prefix, "rev")] += 1
        _mark_edited(prefix)


def _remove(prefix: str) -> None:
    rows = _rows(prefix)
    if len(rows) > 1:
        rows.pop(st.session_state[_k(prefix, "edit")])
        st.session_state[_k(prefix, "edit")] = 0
        st.session_state[_k(prefix, "rev")] += 1
        _mark_edited(prefix)


def _editor(prefix: str) -> None:
    rows = _rows(prefix)
    rev = st.session_state[_k(prefix, "rev")]
    ids = [r["id"] for r in rows]
    idx = st.selectbox(
        "Interval to edit",
        range(len(rows)),
        format_func=lambda i: ids[i],
        key=_k(prefix, "edit"),
    )
    row = rows[idx]
    mode = st.session_state.get(_k(prefix, "mode"), "energy (MWh)")

    def number(label, field, low, high, step, value):
        key = _k(prefix, f"iv_{field}_{idx}_{rev}")
        st.session_state.setdefault(key, value)
        st.number_input(
            label, low, high, step=step, key=key,
            on_change=_on_field, args=(prefix, idx, field, key),
        )  # fmt: skip

    number(f"Duration of {row['id']} (h)", "d", 0.0, sh.DURATION_BOUNDS_H[1], 0.25, row["d"])
    if mode.startswith("energy"):
        number(f"Physical energy in {row['id']} (MWh)", "q", *sh.ENERGY_BOUNDS_MWH, 10.0, row["q"])
    else:
        mw = row["q"] / row["d"] if row["d"] else 0.0
        number(f"Average physical power in {row['id']} (MW)", "mw", *sh.POWER_BOUNDS_MW, 10.0, mw)
    number(f"Spot price in {row['id']} (synthetic $/MWh)", "p", *sh.PRICE_BOUNDS, 1.0, row["p"])
    c1, c2 = st.columns(2)
    c1.button("Add an interval", key=_k(prefix, "add"), on_click=_add, args=(prefix,),
              disabled=len(rows) >= sh.MAX_INTERVALS)  # fmt: skip
    c2.button("Remove this interval", key=_k(prefix, "remove"), on_click=_remove, args=(prefix,),
              disabled=len(rows) <= 1)  # fmt: skip


def render_shape_calculator(prefix: str) -> sh.Result | None:
    if _k(prefix, "rows") not in st.session_state:
        _load(prefix, "peaky")
    st.markdown(
        md_dollars(
            "**Teaching contract** (synthetic; one location): a flat-block financial hedge of "
            "constant power **B** (MW) at a fixed price **K**. In each interval the hedge energy "
            "is h_t = B × d_t (MWh); the buyer pays K and receives the spot price p_t on it.\n\n"
            "- physical cost_t = q_t × p_t\n"
            "- hedge receipt_t = h_t × (p_t − K) (negative = the buyer pays)\n"
            "- net cost_t = physical cost_t − hedge receipt_t (negative = a credit)\n\n"
            "The hedge moves money, not electricity, and is not an exchange product."
        )
    )
    st.selectbox(
        "Start from a synthetic scenario",
        list(sh.SCENARIOS),
        index=list(sh.SCENARIOS).index("peaky"),
        format_func=lambda key: sh.SCENARIOS[key][0],
        key=_k(prefix, "scenario"),
        on_change=_on_scenario,
        args=(prefix,),
    )
    st.number_input("B: flat hedge power (MW)", *sh.POWER_BOUNDS_MW, step=10.0,
                    key=_k(prefix, "b"), on_change=_on_hedge, args=(prefix,))  # fmt: skip
    st.number_input("K: fixed price, a synthetic assumption ($/MWh)", *sh.PRICE_BOUNDS, step=1.0,
                    key=_k(prefix, "kk"), on_change=_on_hedge, args=(prefix,))  # fmt: skip
    st.radio(
        "Enter physical quantities as",
        ["energy (MWh)", "average power (MW) × the interval's duration"],
        horizontal=True,
        key=_k(prefix, "mode"),
    )
    _editor(prefix)
    rows = _rows(prefix)
    try:
        inputs = sh.Inputs(
            intervals=tuple(sh.Interval(r["id"], r["d"], r["q"], r["p"]) for r in rows),
            hedge_mw=st.session_state[_k(prefix, "b")],
            fixed_price=st.session_state[_k(prefix, "kk")],
            scenario=st.session_state[_k(prefix, "label")],
        )
        result = sh.evaluate(inputs)
        reversed_result = sh.evaluate(sh.reversed_profile(inputs))
    except sm.SettlementError as exc:
        st.error(f"Cannot calculate: {exc}. No result is shown.")
        return None
    _show(prefix, result, reversed_result)
    return result


def _show(prefix: str, r: sh.Result, rev: sh.Result) -> None:
    st.subheader("Interval cash flows (synthetic)")
    st.table(
        [
            {
                "Interval": x.interval_id,
                "q (MWh)": _fmt(x.energy_mwh),
                "h (MWh)": _fmt(x.hedge_mwh),
                "p ($/MWh)": _fmt(x.price),
                "Net ($)": _fmt(x.net_cost),
            }
            for x in r.rows
        ],
        hide_index=True,
    )
    ids = [x.interval_id for x in r.rows]
    if st.session_state.get(_k(prefix, "view"), 0) >= len(ids):
        st.session_state[_k(prefix, "view")] = 0  # an interval was removed
    pick = st.selectbox(
        "Show one interval in detail (narrow view)",
        range(len(ids)),
        format_func=lambda i: ids[i],
        key=_k(prefix, "view"),
    )
    x = r.rows[min(pick, len(r.rows) - 1)]
    receipt_reading = (
        "the buyer receives it"
        if x.hedge_receipt > 0
        else "negative: the buyer pays it"
        if x.hedge_receipt < 0
        else "no hedge cash flow"
    )
    st.table(
        [
            {"Quantity": "Duration", "Value": f"{_fmt(x.duration_h)} h"},
            {"Quantity": "Physical energy q", "Value": f"{_fmt(x.energy_mwh)} MWh"},
            {"Quantity": "Hedge energy h = B × d", "Value": f"{_fmt(x.hedge_mwh)} MWh"},
            {"Quantity": "Mismatch q − h", "Value": f"{_fmt(x.residual_mwh)} MWh ({x.status})"},
            {"Quantity": "Spot price p", "Value": f"{_fmt(x.price)} $/MWh"},
            {"Quantity": "Physical cost q × p", "Value": f"{_fmt(x.physical_cost)} $"},
            {
                "Quantity": "Hedge receipt h × (p − K)",
                "Value": f"{_fmt(x.hedge_receipt)} $ ({receipt_reading})",
            },
            {"Quantity": "Net cost", "Value": f"{_fmt(x.net_cost)} $"},
        ],
        hide_index=True,
    )
    with st.expander("All intervals, all columns (wide table; scrolls sideways)"):
        st.table(
            [
                {
                    "Interval": y.interval_id,
                    "d (h)": _fmt(y.duration_h),
                    "q (MWh)": _fmt(y.energy_mwh),
                    "h (MWh)": _fmt(y.hedge_mwh),
                    "q − h (MWh)": _fmt(y.residual_mwh),
                    "Status": y.status,
                    "p ($/MWh)": _fmt(y.price),
                    "Physical ($)": _fmt(y.physical_cost),
                    "Hedge receipt ($)": _fmt(y.hedge_receipt),
                    "Net ($)": _fmt(y.net_cost),
                }
                for y in r.rows
            ],
            hide_index=True,
        )

    st.subheader("Totals")
    st.table(
        [
            {"Quantity": "Total duration D", "Value": f"{_fmt(r.total_duration_h)} h"},
            {"Quantity": "Physical energy Q", "Value": f"{_fmt(r.total_energy_mwh)} MWh"},
            {"Quantity": "Hedge energy B × D", "Value": f"{_fmt(r.total_hedge_mwh)} MWh"},
            {
                "Quantity": "Aggregate mismatch R = Q − B × D",
                "Value": f"{_fmt(r.residual_mwh)} MWh",
            },
            {"Quantity": "Duration-weighted price p̄", "Value": f"{_fmt(r.average_price)} $/MWh"},
            {"Quantity": "Physical cost", "Value": f"{_fmt(r.physical_cost)} $"},
            {"Quantity": "Hedge receipt", "Value": f"{_fmt(r.hedge_receipt)} $"},
            {"Quantity": "Net cost", "Value": f"{_fmt(r.net_cost)} $"},
        ],
        hide_index=True,
    )
    st.markdown("**Decomposition 1:** net = Σ h × K + Σ (q − h) × p")
    st.table(
        [
            {"Component": "Fixed price on hedge energy", "Amount ($)": _fmt(r.fixed_hedge_total)},
            {"Component": "Residual energy at spot prices", "Amount ($)": _fmt(r.residual_cost)},
            {"Component": "Sum = net cost", "Amount ($)": _fmt(r.net_cost)},
        ],
        hide_index=True,
    )
    st.markdown("**Decomposition 2:** net = B × D × K + R × p̄ + Σ (q − h)(p − p̄)")
    st.table(
        [
            {"Component": "Fixed hedge component", "Amount ($)": _fmt(r.fixed_hedge_total)},
            {"Component": "Aggregate energy mismatch", "Amount ($)": _fmt(r.aggregate_mismatch)},
            {"Component": "Time-shape component", "Amount ($)": _fmt(r.time_shape)},
            {"Component": "Sum = net cost", "Amount ($)": _fmt(r.net_cost)},
        ],
        hide_index=True,
    )
    st.caption(
        md_dollars(
            "The time-shape component is an accounting split under this decomposition (with p̄ "
            "the duration-weighted average price), not a universal industry risk metric."
        )
    )
    st.markdown("**Same total energy, reversed load shape**")
    st.table(
        [
            {
                "Profile": "As entered",
                "Q (MWh)": _fmt(r.total_energy_mwh),
                "Net ($)": _fmt(r.net_cost),
                "Time-shape ($)": _fmt(r.time_shape),
            },
            {
                "Profile": "Energies in reverse order",
                "Q (MWh)": _fmt(rev.total_energy_mwh),
                "Net ($)": _fmt(rev.net_cost),
                "Time-shape ($)": _fmt(rev.time_shape),
            },
        ],
        hide_index=True,
    )
    unhedged = r.physical_cost
    change = r.net_cost - unhedged
    effect = (
        f"raised the buyer's cost by {_fmt(change)}"
        if change > 0
        else f"lowered the buyer's cost by {_fmt(-change)}"
        if change < 0
        else "did not change the buyer's cost"
    )
    st.markdown(
        md_dollars(
            f"Without the hedge the cost would be Σ q × p = {_fmt(unhedged)} synthetic $. In this "
            f"scenario the hedge **{effect}** synthetic $. A hedge changes exposure; it does not "
            "guarantee savings."
        )
    )
    with st.expander("Units, assumptions, sources, and provenance"):
        st.table(UNITS, hide_index=True)
        label = r.inputs["scenario"]
        base = label.split(":", 1)[-1]
        origin = (
            f"edited from synthetic scenario `{base}` v{r.scenario_version}"
            if label.startswith("edited:")
            else f"synthetic scenario `{label}` v{r.scenario_version}"
        )
        st.markdown(
            md_dollars(
                f"Inputs: {origin}. Formula v{r.formula_version}; calculation id "
                f"`{r.snapshot_id}`. No model prices are used.\n\n"
                + "\n".join(f"- {a}" for a in r.assumptions)
            )
        )
        st.markdown(f"- {EIA_ARTICLE} (real-market context only; its numbers are not used)")
