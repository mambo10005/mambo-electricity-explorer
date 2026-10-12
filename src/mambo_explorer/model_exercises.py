"""Model-backed exercises. Every answer is built from verified model records, never typed in.

A generator receives the lesson's *current* records (see modeling/cases.is_current) and
returns an Exercise, or Unavailable when a required run is missing, failed its checks, or
does not show what the question needs. The exercise's snapshot covers the scenario inputs,
the package pin, the check and generator versions, and each run's validation status. Its
result references are the run ids. A different scenario, pin, or status gives a different
snapshot, so an answer to an older question is never marked against new results.

Option strings hold at most one "$": Streamlit renders radio options as Markdown, and a
pair of "$" would open a LaTeX span.
"""

from __future__ import annotations

import hashlib
import json

from mambo_explorer.exercises import Exercise, Unavailable, _order
from mambo_explorer.modeling import adapter
from mambo_explorer.modeling import cases as mc

VERSION = "1.0.0"
CUR = "synthetic $"
TOL = 1e-6


def _n(value: float) -> str:
    """Number for display: integers without decimals, otherwise up to 3 decimals."""
    value = round(value, 6) + 0.0
    if float(value).is_integer():
        return f"{value:,.0f}".replace("-", "−")
    return f"{value:,.3f}".rstrip("0").rstrip(".").replace("-", "−")


def _signed(value: float) -> str:
    return ("+" if round(value, 6) > 0 else "") + _n(value)


def snapshot(keys: tuple[str, ...], records: dict) -> tuple[str, tuple[str, ...]]:
    """(snapshot id, result references) for the runs an exercise depends on."""
    runs = []
    for key in keys:
        r = records[key]
        runs.append(
            {
                "run": key,
                "kind": r.kind,
                "scenario": [r.scenario_id, r.scenario_version],
                "input_fingerprint": r.input_fingerprint,
                "status": r.status,
                "price_status": getattr(r, "price_status", None),
                "dispatch_unique": getattr(r, "dispatch_unique", None),
                "package": [
                    r.package.get("version"),
                    r.package.get("installed_commit"),
                    r.package.get("highspy"),
                ],
            }
        )
    payload = {
        "generator_version": VERSION,
        "checks_version": adapter.CHECKS_VERSION,
        "price_check": [adapter.PRICE_STEP_MW, adapter.PRICE_FD_TOL],
        "runs": runs,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"model-{digest}", tuple(records[k].run_id for k in keys)


def _exercise(ex_id, keys, records, question, correct, decoys, explanation, calc_id="dc_opf"):
    sid, refs = snapshot(keys, records)
    options, answer = _order(sid, correct, decoys)
    return Exercise(ex_id, sid, question, options, answer, explanation, calc_id, True, refs)


# --- record helpers -------------------------------------------------------------------------


def _inputs(key: str):
    return mc.run_inputs(key)


def _dispatch(record) -> dict[str, float]:
    if record.kind == "opf.dc":
        return {d["generator"]: d["dispatch_mw"] for d in record.dispatch}
    return {g["generator"]: g["output_mw"] for g in record.generators}


def _ratings(inputs) -> dict[str, float]:
    return {"AB": inputs.rating_ab_bc, "BC": inputs.rating_ab_bc, "AC": inputs.rating_ac}


def _flows(record) -> dict[str, float]:
    if record.kind == "opf.dc":
        return {b["branch"]: b["flow_mw"] for b in record.branches}
    return {b["branch"]: b["flow_from_to_mw"] for b in record.branches}


def _binding(record) -> tuple[str, ...]:
    return tuple(b["branch"] for b in record.branches if b["binding"])


def _price(record, bus: str) -> float:
    return next(p["price_per_mwh"] for p in record.prices if p["bus"] == bus)


def _ends(branch: str) -> str:
    f, t, _ = mc.on.LINES[branch]
    return f"{f} → {t}"


# --- generators -------------------------------------------------------------------------------
# Each generator lists the lesson runs it needs in REQUIRES. The caller passes only current
# records. A failed run (no outputs) always makes the exercise unavailable.

REQUIRES: dict[str, tuple[str, ...]] = {}


def requires(*keys: str):
    def wrap(fn):
        REQUIRES[fn.__name__] = keys
        return fn

    return wrap


@requires("uncongested", "pf-no-limit-cheapest")
def pf_reports_violation(ex_id, records):
    pf = records["pf-no-limit-cheapest"]
    if pf.status == "failed":
        return Unavailable(ex_id, "the power-flow run failed its checks")
    inputs, out = _inputs("pf-no-limit-cheapest"), _dispatch(pf)
    ratings, flows = _ratings(inputs), _flows(pf)
    over = [k for k in flows if abs(flows[k]) > ratings[k] + TOL]
    if not over:
        return Unavailable(ex_id, "this dispatch breaks no rating, so the question does not apply")
    k = max(over, key=lambda b: abs(flows[b]) - ratings[b])
    flow, rating = abs(flows[k]), ratings[k]
    return _exercise(
        ex_id,
        REQUIRES["pf_reports_violation"],
        records,
        f"Power flow is given the dispatch G1 = {_n(out['G1'])} MW and G2 = {_n(out['G2'])} MW. "
        "That is the cheapest dispatch if lines had no limits (from the verified uncongested "
        f"run). Here line AC is rated {_n(inputs.rating_ac)} MW. What does the power flow report?",
        f"Line {k} would carry {_n(flow)} MW, above its {_n(rating)} MW rating. Power flow "
        "reports the violation; it does not change the dispatch.",
        [
            f"Line {k} carries {_n(rating)} MW: power flow lowers the flow to the rating.",
            "Nothing: power flow cannot solve a dispatch that breaks a rating.",
            f"Line {k} carries {_n(flow)} MW, and that is within limits because power flow "
            "has no ratings.",
        ],
        f"Power flow takes the dispatch as given and computes where the power goes. Line {k} "
        f"({_ends(k)}) would carry {_n(flow)} MW against a {_n(rating)} MW rating, so the run is "
        "marked *solved, with limits exceeded*. Choosing a dispatch that respects the ratings is "
        "the optimal power flow's job, not the power flow's.",
        "dc_power_flow",
    )


@requires("congested", "pf-chosen")
def feasible_not_cheapest(ex_id, records):
    pf, opf = records["pf-chosen"], records["congested"]
    if pf.status == "failed" or opf.status != "optimal":
        return Unavailable(ex_id, "a required run did not pass its checks")
    if pf.status != "ok":
        return Unavailable(
            ex_id, "the chosen dispatch breaks a limit, so the question does not apply"
        )
    inputs, out = _inputs("pf-chosen"), _dispatch(pf)
    cost_pf = adapter.linear_cost_rate(inputs, out)
    gap = cost_pf - opf.cost_rate_per_h
    if gap <= TOL:
        return Unavailable(
            ex_id, "the chosen dispatch is not more expensive, so the question does not apply"
        )
    o = _dispatch(opf)
    return _exercise(
        ex_id,
        REQUIRES["feasible_not_cheapest"],
        records,
        f"A dispatch chosen by hand, G1 = {_n(out['G1'])} MW and G2 = {_n(out['G2'])} MW, passes "
        "every power-flow check on the congested network: every flow is within its rating. "
        "Compared with the optimal dispatch, which statement is true?",
        f"It respects every limit, but costs {_n(gap)} {CUR}/h more than the optimal dispatch.",
        [
            "It respects every limit, so it must be the cheapest dispatch.",
            "It breaks line AC's rating, so it cannot be used.",
            f"It costs {_n(gap)} {CUR}/h less than the optimal dispatch.",
        ],
        f"Cost rate = Σ offer × output = {_n(inputs.cost_g1)} × {_n(out['G1'])} + "
        f"{_n(inputs.cost_g2)} × {_n(out['G2'])} = {_n(cost_pf)} {CUR}/h. The verified optimal "
        f"dispatch (G1 {_n(o['G1'])} MW, G2 {_n(o['G2'])} MW) costs {_n(opf.cost_rate_per_h)} "
        f"{CUR}/h. **Feasible** (within every limit) does not mean **cheapest**.",
    )


@requires("congested")
def binding_constraint(ex_id, records):
    r = records["congested"]
    if r.status != "optimal":
        return Unavailable(ex_id, "the congested run did not pass its checks")
    bound = _binding(r)
    if len(bound) != 1:
        return Unavailable(ex_id, "the question needs exactly one binding line")
    k = bound[0]
    rows = {b["branch"]: b for b in r.branches}
    others = [b for b in rows if b != k]
    caps = [d for d in r.dispatch if d["at_capacity"]]
    return _exercise(
        ex_id,
        REQUIRES["binding_constraint"],
        records,
        "In the verified congested run, which limit is binding (the flow sits exactly at it)?",
        f"Line {k} ({_ends(k)}), at its {_n(rows[k]['rating_mw'])} MW rating",
        [
            *(
                f"Line {b} ({_ends(b)}), carrying {_n(abs(rows[b]['flow_mw']))} MW of "
                f"{_n(rows[b]['rating_mw'])} MW"
                for b in others
            ),
            "No limit binds; the prices differ only because the offers differ",
        ],
        f"Line {k} carries {_n(abs(rows[k]['flow_mw']))} MW with a {_n(rows[k]['rating_mw'])} MW "
        "rating, and its line-limit sensitivity is "
        f"{_n(rows[k]['limit_sensitivity_per_mw'])} {CUR}/h per MW. The other lines have room "
        f"to spare. {'No generator is at its capacity.' if not caps else ''}",
    )


def _deltas(base, more) -> tuple[float, dict[str, float]]:
    load = _inputs_of(more).load_c - _inputs_of(base).load_c
    b, m = _dispatch(base), _dispatch(more)
    return load, {g: m[g] - b[g] for g in b}


def _inputs_of(record):
    return mc.on.OpfInputs(**{k: record.inputs[k] for k in mc.on.BOUNDS})


def _delta_text(d: dict[str, float]) -> str:
    return f"G1 {_signed(d['G1'])} MW and G2 {_signed(d['G2'])} MW"


@requires("uncongested", "uncongested-plus10")
def next_increment(ex_id, records):
    base, more = records["uncongested"], records["uncongested-plus10"]
    if base.status != "optimal" or more.status != "optimal":
        return Unavailable(ex_id, "a required run did not pass its checks")
    if _binding(base) != _binding(more):
        return Unavailable(ex_id, "the extra demand changed which limits bind")
    step, d = _deltas(base, more)
    inputs = _inputs("uncongested")
    return _exercise(
        ex_id,
        REQUIRES["next_increment"],
        records,
        f"In the uncongested case, demand at bus C rises by {_n(step)} MW. G1 offers "
        f"{_n(inputs.cost_g1)} and G2 offers {_n(inputs.cost_g2)} (synthetic dollars per MWh). "
        "How does the optimal dispatch change?",
        _delta_text(d),
        [
            _delta_text({"G1": d["G2"], "G2": d["G1"]}),
            _delta_text({"G1": step / 2, "G2": step / 2}),
            _delta_text({"G1": -step, "G2": 2 * step}),
        ],
        f"Both verified runs were compared: {_delta_text(d)}. With no line at its limit, the "
        "extra demand comes from the cheapest generator that still has spare capacity.",
    )


@requires("congested", "congested-plus10")
def positive_sensitivity(ex_id, records):
    base, more = records["congested"], records["congested-plus10"]
    if base.status != "optimal" or more.status != "optimal":
        return Unavailable(ex_id, "a required run did not pass its checks")
    if base.price_status != "verified":
        return Unavailable(ex_id, "prices were not verified for this run, so they are not used")
    if _binding(base) != _binding(more):
        return Unavailable(ex_id, "the extra demand changed which limits bind")
    step, d = _deltas(base, more)
    inputs = _inputs("congested")
    per = {g: v / step for g, v in d.items()}
    implied = per["G1"] * inputs.cost_g1 + per["G2"] * inputs.cost_g2
    price_c = _price(base, "C")
    if abs(implied - price_c) > 1e-4:
        return Unavailable(ex_id, "the re-dispatch does not reproduce the verified price")
    average = base.cost_rate_per_h / inputs.load_c
    return _exercise(
        ex_id,
        REQUIRES["positive_sensitivity"],
        records,
        f"In the congested case, the verified modeled price at bus C is {_n(price_c)} synthetic "
        f"dollars per MWh, although the offers are only {_n(inputs.cost_g1)} and "
        f"{_n(inputs.cost_g2)}. What does that price mean?",
        f"One more MW at C for the hour adds about {_n(price_c)} {CUR}: the model changes "
        f"G1 by {_signed(per['G1'])} MW and G2 by {_signed(per['G2'])} MW to keep line "
        f"{'/'.join(_binding(base))} within its rating.",
        [
            f"A generator at bus C offers {_n(price_c)} {CUR}/MWh.",
            f"It is the average cost of all energy served ({_n(average)} per MWh).",
            "It is the price a real ISO would pay at a node like C.",
        ],
        f"Compare the verified runs at {_n(inputs.load_c)} MW and "
        f"{_n(inputs.load_c + step)} MW of demand: {_delta_text(d)}, the same binding line. Per "
        f"MW of extra demand: ({_signed(per['G1'])}) × {_n(inputs.cost_g1)} + "
        f"({_signed(per['G2'])}) × {_n(inputs.cost_g2)} = {_n(implied)} {CUR} per MWh, which "
        "matches the verified modeled price at C. There is no generator at C, and the price "
        "is a marginal cost, not an average. These are synthetic numbers from a lossless "
        "teaching model, not ISO prices.",
    )


@requires("congested", "relaxed")
def relaxation_cost(ex_id, records):
    base, relaxed = records["congested"], records["relaxed"]
    if base.status != "optimal" or relaxed.status != "optimal":
        return Unavailable(ex_id, "a required run did not pass its checks")
    bound = _binding(base)
    if len(bound) != 1 or _binding(relaxed) != bound:
        return Unavailable(ex_id, "the relaxation changed which limits bind")
    k = bound[0]
    r0, r1 = _ratings(_inputs("congested"))[k], _ratings(_inputs("relaxed"))[k]
    sens = next(b["limit_sensitivity_per_mw"] for b in base.branches if b["branch"] == k)
    change = relaxed.cost_rate_per_h - base.cost_rate_per_h
    predicted = sens * (r1 - r0)
    if abs(change - predicted) > 1e-4 or abs(change) <= TOL:
        return Unavailable(ex_id, "the cost change does not match the verified sensitivity")
    word = "falls" if change < 0 else "rises"
    other = "rises" if change < 0 else "falls"
    return _exercise(
        ex_id,
        REQUIRES["relaxation_cost"],
        records,
        f"In the congested case, line {k}'s rating is raised from {_n(r0)} MW to {_n(r1)} MW. "
        f"The verified run reports a line-limit sensitivity of {_n(sens)} synthetic dollars "
        "per hour per MW of rating. How does the cost rate change?",
        f"It {word} by {_n(abs(change))} {CUR}/h ({_n(sens)} × {_n(r1 - r0)} MW).",
        [
            f"It {other} by {_n(abs(change))} {CUR}/h.",
            f"It {word} by {_n(abs(sens))} {CUR}/h in total.",
            "It does not change, because the modeled prices stay the same.",
        ],
        f"Verified runs: {_n(base.cost_rate_per_h)} {CUR}/h before and "
        f"{_n(relaxed.cost_rate_per_h)} after, a change of {_signed(change)} per hour. The "
        f"sensitivity predicts {_n(sens)} × {_n(r1 - r0)} = {_signed(predicted)}. They match "
        f"because line {k} still binds after the change (the same regime). The modeled prices "
        "can stay the same while the cost changes: prices describe the *next* MW, not the total.",
    )


@requires("congested")
def cost_units(ex_id, records):
    r = records["congested"]
    if r.status != "optimal":
        return Unavailable(ex_id, "the congested run did not pass its checks")
    if r.price_status != "verified" or len(_binding(r)) != 1:
        return Unavailable(ex_id, "the question needs verified prices and one binding line")
    k = _binding(r)[0]
    sens = next(b["limit_sensitivity_per_mw"] for b in r.branches if b["branch"] == k)
    price_c = _price(r, "C")
    return _exercise(
        ex_id,
        REQUIRES["cost_units"],
        records,
        "The verified congested run reports these four numbers. Which one is the cost over "
        f"the {_n(r.interval_hours)}-hour teaching interval?",
        f"{_n(r.interval_cost)} {CUR}",
        [
            f"{_n(r.cost_rate_per_h)} {CUR}/h",
            f"{_n(price_c)} {CUR}/MWh",
            f"{_n(sens)} {CUR}/h per MW of rating",
        ],
        f"- **{_n(r.cost_rate_per_h)} {CUR}/h** is the *cost rate* (Σ offer × MW).\n"
        f"- **{_n(r.interval_cost)} {CUR}** is the *interval cost*: rate × "
        f"{_n(r.interval_hours)} h. The numbers match only because the interval is one hour.\n"
        f"- **{_n(price_c)} {CUR}/MWh** is the verified modeled *price* at bus C.\n"
        f"- **{_n(sens)} {CUR}/h per MW** is line {k}'s *limit sensitivity*.",
    )


def _two_sided(record):
    """(bus, up, down) for a bus whose one-sided rates differ or are missing (C, the demand
    bus, first)."""
    for s in sorted(record.sensitivities, key=lambda s: s["bus"] != "C"):
        up, down = s["up_per_mwh"], s["down_per_mwh"]
        if up is None or down is None or abs(up - down) > adapter.PRICE_FD_TOL:
            return s["bus"], up, down
    return None


@requires("breakpoint")
def withheld_reason(ex_id, records):
    r = records["breakpoint"]
    if r.status != "optimal" or r.price_status != "withheld":
        return Unavailable(ex_id, "this run's prices were not withheld")
    found = _two_sided(r)
    if found is None or found[1] is None or found[2] is None:
        return Unavailable(ex_id, "this run has no bus with two different finite rates")
    bus, up, down = found
    return _exercise(
        ex_id,
        REQUIRES["withheld_reason"],
        records,
        f"In the breakpoint case the run is optimal, but no prices are shown. What did the "
        f"±{_n(adapter.PRICE_STEP_MW)} MW check find at bus {bus}?",
        f"Adding demand costs {_n(up)} per MWh but removing it saves {_n(down)} per MWh, so a "
        "unique two-sided marginal price was not verified for this run.",
        [
            "The solver failed, so none of the run's results can be trusted.",
            "The solver's numbers are meaningless at every breakpoint.",
            f"The price is exactly {_n((up + down) / 2)}, the average of the two rates.",
        ],
        f"The check re-solved with {_n(adapter.PRICE_STEP_MW)} MW more and less demand at "
        f"each bus. At {bus}: {_n(up)} up, {_n(down)} down (synthetic dollars per MWh). One "
        "number cannot match both, so prices are withheld and both one-sided rates are shown. "
        "The dispatch and cost still passed every check. The solver's own number is not "
        "meaningless, and nothing says it is the average; it just cannot describe both "
        "directions at once.",
    )


@requires("capacity-edge")
def infeasible_direction(ex_id, records):
    r = records["capacity-edge"]
    if r.status != "optimal" or r.price_status != "withheld":
        return Unavailable(ex_id, "this run's prices were not withheld")
    side = next(
        (
            s
            for s in sorted(r.sensitivities, key=lambda s: s["bus"] != "C")
            if (s["up_per_mwh"] is None) != (s["down_per_mwh"] is None)
        ),
        None,
    )
    if side is None:
        return Unavailable(ex_id, "no bus has exactly one infeasible direction")
    bus = side["bus"]
    up_bad = side["up_per_mwh"] is None
    finite = side["down_per_mwh"] if up_bad else side["up_per_mwh"]
    bad, good = ("Adding", "removing") if up_bad else ("Removing", "adding")
    step = _n(adapter.PRICE_STEP_MW)
    return _exercise(
        ex_id,
        REQUIRES["infeasible_direction"],
        records,
        f"In the edge-of-capacity case the run is optimal, but no prices are shown. What did "
        f"the ±{step} MW check find at bus {bus}?",
        f"{bad} {step} MW is infeasible, while {good} it changes the cost at {_n(finite)} per MWh.",
        [
            "Both directions are infeasible, so the run itself failed.",
            f"{good.capitalize()} {step} MW is infeasible, while {bad.lower()} it changes the "
            f"cost at {_n(finite)} per MWh.",
            "The run is infeasible, so no dispatch is shown.",
        ],
        f"Demand equals total capacity, so the run is optimal but has no spare capacity. "
        f"{bad} {step} MW cannot be served or balanced within the limits; {good} it is feasible "
        f"and changes the cost at {_n(finite)} synthetic dollars per MWh. With one side "
        "missing, a unique two-sided marginal price was not verified for this run.",
    )


def _status_phrase(record) -> str:
    if record.status == "infeasible":
        return "infeasible (no dispatch meets demand within the limits)"
    if record.status != "optimal":
        return "failed its checks"
    if record.dispatch_unique is False:
        return "optimal, but more than one dispatch is equally cheap"
    return "optimal, with one cheapest dispatch"


@requires("equal", "infeasible")
def nonunique_vs_infeasible(ex_id, records):
    eq, inf = records["equal"], records["infeasible"]
    if eq.status == "failed" or inf.status == "failed":
        return Unavailable(ex_id, "a required run failed its checks")
    a, b = _status_phrase(eq), _status_phrase(inf)
    if a == b:
        return Unavailable(ex_id, "the two runs have the same status")
    phrases = [
        "optimal, but more than one dispatch is equally cheap",
        "infeasible (no dispatch meets demand within the limits)",
        "optimal, with one cheapest dispatch",
    ]
    decoys = [f"Equal offers: {x}. Not enough capacity: {y}." for x in phrases for y in phrases]
    return _exercise(
        ex_id,
        REQUIRES["nonunique_vs_infeasible"],
        records,
        "Compare the verified equal-offers run with the not-enough-capacity run. Which "
        "statement describes both correctly?",
        f"Equal offers: {a}. Not enough capacity: {b}.",
        _pick_decoys(f"Equal offers: {a}. Not enough capacity: {b}.", decoys),
        "A **non-unique** dispatch is still a valid optimum: the cost is known, and only the "
        "split between equally priced generators is not. An **infeasible** run has no valid "
        "dispatch at all, so it shows no numbers, and this model never sheds load to make it "
        "feasible.",
    )


def _pick_decoys(correct: str, candidates: list[str]) -> list[str]:
    """Three wrong statements, chosen deterministically."""
    wrong = [c for c in candidates if c != correct]
    wrong.sort(key=lambda c: hashlib.sha256(c.encode()).hexdigest())
    return wrong[:3]


@requires("equal")
def uniqueness_vs_price(ex_id, records):
    r = records["equal"]
    if r.status != "optimal" or r.dispatch_unique is None:
        return Unavailable(ex_id, "the equal-offers run did not pass its checks")
    unique = "unique" if r.dispatch_unique else "not unique"
    priced = (
        "the tested two-sided price check passed"
        if r.price_status == "verified"
        else "a unique two-sided marginal price was not verified"
    )
    combos = [
        f"The dispatch is {u}, and {p}."
        for u in ("unique", "not unique")
        for p in (
            "the tested two-sided price check passed",
            "a unique two-sided marginal price was not verified",
        )
    ]
    correct = f"The dispatch is {unique}, and {priced}."
    return _exercise(
        ex_id,
        REQUIRES["uniqueness_vs_price"],
        records,
        "In the equal-offers case, what do the run's two separate checks say?",
        correct,
        [c for c in combos if c != correct],
        f"Uniqueness asks whether another dispatch is equally cheap; here it is {unique}. Price "
        "verification asks whether adding and removing a little demand at each bus change the "
        f"cost at the same rate as the reported price; here {priced}. They are separate "
        "questions. The price check concerns only the tested ±"
        f"{_n(adapter.PRICE_STEP_MW)} MW perturbations: it does not prove that the dispatch or "
        "the dual is unique, or that the price holds for larger changes.",
    )


GENERATORS = {
    fn.__name__: fn
    for fn in (
        pf_reports_violation,
        feasible_not_cheapest,
        binding_constraint,
        next_increment,
        positive_sensitivity,
        relaxation_cost,
        cost_units,
        withheld_reason,
        infeasible_direction,
        nonunique_vs_infeasible,
        uniqueness_vs_price,
    )
}


def generate(spec: dict, records: dict):
    """Build a model exercise from current records only (stale ones must be filtered out)."""
    name = spec["generator"]
    missing = [k for k in REQUIRES[name] if k not in records]
    if missing:
        return Unavailable(
            spec["exercise_id"], "run this lesson's model cases first (results are not current)"
        )
    return GENERATORS[name](spec["exercise_id"], records)
