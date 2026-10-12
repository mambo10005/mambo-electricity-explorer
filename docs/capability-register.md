# mambo-power capability register

Package: `mambo10005/mambo-power`, MIT. **Pinned to v0.2.0, commit
`26be8c18b7efb865419054bec7b0b171478bc37a`** (ADR 0006). The package source at this
commit is identical to `main` on 2026-10-11; only release config and `uv.lock` changed
after it. Inspected on 2026-10-11 from a read-only clone. The package repository was not
modified.

How to read the columns:
- **Documented:** what the README or docstrings claim.
- **Inspected:** source this project actually read.
- **Executed:** what was actually run, and where.
- **Exposed:** whether the app uses the capability.

Only one row is verified end to end.

| Capability | Documented | Inspected implementation | Executed verification | Limitations | Exposed in app |
|---|---|---|---|---|---|
| **DC power flow** `mambo_power.pf.solve_dc(Network) -> DcPowerFlowResult` | README "Solvers: DC power flow"; module docstring cites MATPOWER `rundcpf` | `pf/__init__.py::solve_dc`, `pf/dc.py::solve` (B′θ = P − p_shift with slack at 0; flows Bf·θ + pf_shift; slack generator absorbs the balance); `numerics/bbus.py` (b = 1/(x·tap); r and line charging ignored); result models in `results/tables.py`, `results/power_flow.py`; provenance in `results/provenance.py` | (1) The package's own unit tests at the pin (`test_pf_dc`, `test_effective_roles`, `test_islands`, `test_model_invariants`, `test_numerics_guards`, `test_results_models`): **99 passed on 3.11.16 and 99 on 3.14.2**. (2) This project's **independent** benchmarks: closed-form 3-bus solution, a hand-worked case, a radial case, monotonicity and sign tests, agreement ≤ 1e-9 MW (`tests/test_modeling.py`). (3) Per-run checks in the app (balance, KCL, Δθ/x, reference angle, finiteness) at 1e-6 MW. | Lossless; no voltage magnitudes or reactive power; limits not enforced (reported as violations); one snapshot | **Yes** — Model Labs, through `modeling/adapter.py` only |
| Network model and validation (`model.Network`, `validate_network`) | README "JSON-native network model (pydantic v2)" | `model/entities.py`, `model/network.py`: field names and units (MW, MVAr, kV; r/x/b in pu on `base_mva`); `validate_network` | Used for every lab run; `validate_network` returns no issues for the teaching network (test); package `test_model_invariants` passed | Only the fields the teaching network uses are exercised | Indirectly (inputs) |
| **DC OPF, linear costs, single period** `opf.solve_dc_opf` | README "DC optimal power flow … with duals on HiGHS" | Full formulation traced (ADR 0007): MW variables, Σc1·p objective ($/h), one balance row, PTDF flow rows, raw HiGHS duals, `lmp = λ + μ·PTDF` | **Stage 7:** 5 hand-derived benchmark families (uncongested, capacity, congested, infeasible, breakpoints and equal offers). Two-sided demand perturbations at every bus at 0.01, 0.1, and 1 MW equal the reported prices within 1e-6 $/MWh. The rating-relaxation sensitivity equals the flow dual. Per-run KKT and price-decomposition checks (`tests/test_opf_benchmarks.py`, 46 tests). | Linear offers only; one period; lossless; no unit commitment; prices withheld at breakpoints | **Yes** — economic-dispatch lab, via `modeling/adapter.run_dc_opf` |
| DC OPF, other cost forms (quadratic c2, piecewise-linear, elastic demand bids), phase shifters, AC check | README | Code paths read | Not executed | — | No |
| AC Newton power flow `pf.solve_ac` | README | Entry point read (`pf/__init__.py`) | Not executed | — | No |
| PTDF / LODF, N-1 screening | README M1/M3 | Module list only | Not executed | — | No |
| Nodal, zonal, multiperiod markets; redispatch; agent bidding | README M4–M7 | Module list only | Not executed | — | No |
| Importers and exporters (MATPOWER, PSS/E RAW, pandapower JSON, PyPSA, CSV); bundled IEEE cases | README M8; ADR-014 | Module and data file list only | Not executed | — | No |
| Jobs API (`jobs/`) | README "stateless job surface" | Module list only | Not executed | — | No |

## Dependencies brought in (all MIT or BSD; see `docs/dependency-licenses.md`)

- mambo-power 0.2.0 (MIT; shipped license file read)
- numpy (already present)
- scipy: 1.17.1 on Python 3.11 and 1.18.1 on 3.14; bare "BSD License" classifier,
  flagged for review
- highspy 1.15.1 (MIT): installed as a package requirement but **not used** by DC power flow
- pydantic 2.14.1 and pydantic-core 2.50.1 (MIT)
- annotated-types and typing-inspection (MIT)

All have wheels for CPython 3.11 and 3.14 on Windows; installation and import were
verified on both.

## Smallest first experiment

**DC power flow** on a synthetic three-bus network (Stage 6). Linear-cost DC OPF followed
in Stage 7 after its formulation audit and independent price verification (ADR 0007).
