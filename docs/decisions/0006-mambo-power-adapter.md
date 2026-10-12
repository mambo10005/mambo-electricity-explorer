# 0006 — mambo-power dependency, adapter, and the first teaching lab

- **Status:** Accepted
- **Date:** 2026-10-11

## Context

PRD R-9 requires modeling through mambo-power behind a separately validated adapter
(U-2). The package is public and MIT-licensed. Its v0.2.0 tag is commit
`26be8c18b7efb865419054bec7b0b171478bc37a`; `main` adds only release-config and lock
changes on top.

## Decision

1. **Dependency:** `mambo-power @ git+https://github.com/mambo10005/mambo-power@26be8c18…`
   - Pinned to a full commit, never a branch. `uv.lock` records the same revision.
   - Hatch's `allow-direct-references` is enabled. This package is never published
     (classifier "Private :: Do Not Upload"), which is when hatch would refuse a direct
     reference.
   - At runtime, `adapter.package_info()` reads the installed distribution's PEP 610
     `direct_url.json` and reports whether the installed commit matches the pin. A
     test asserts that it does.
2. **Offline tests:** after the one-time `uv sync --locked` (which needs network to
   clone at the pin), every test runs offline. No test uses the network.
3. **Scope:** DC power flow only, called only from `modeling/adapter.py`. It uses the
   package's own `Network`/`Bus`/`Branch`/`Generator`/`Load` pydantic schema, not an
   invented generic interface.
   - DC OPF is inspected but **not exposed**, because its dual scaling and signs were
     not independently verified.
   - Nothing else in the package is used.
4. **Validation layer:** the adapter re-checks every result with its own arithmetic:
   - power balance, bus KCL, flow = Δθ/x, reference angle exactly 0, and finiteness,
     at 1e-6 MW
   - branch ratings and generator limits, reported as violations because DC power flow
     doesn't enforce them

   A consistency failure, a solver error, invalid input, or a non-converged result
   gives `status = "failed"` with **no outputs**.
5. **Teaching network:** synthetic three-bus triangle, 100 MVA base, bounded controls:
   - G2: 0–200 MW
   - load at C: 0–300 MW
   - x_AC: 0.05–0.50 pu
   - AC in service: yes/no

   It makes no real-network claim and uses no ERCOT or EIA inputs.
6. **Runs:** stored as JSON in `<MAMBO_DATA_DIR>/model-runs/` (gitignored). Atomic,
   never overwritten; failed runs are kept. Each run records:
   - the input snapshot and fingerprint, and the scenario version
   - the package version and installed commit, solver, and scipy version
   - the checks, status, and outputs
7. **UI invalidation:** a result is shown only while its input fingerprint matches the
   current inputs. A failed run replaces the displayed result.

## Alternatives considered

- **Depend on `main`:** rejected, because it moves.
- **Install from PyPI:** not verified to be published at the same commit; the Git pin
  is exact.
- **Expose DC OPF and its LMPs now:** rejected until objective units and dual
  sign/scaling are verified independently.
- **Generic modeling interface:** rejected as speculative abstraction.

## Consequences

- Upgrading mambo-power is a deliberate commit: new pin, `uv lock`, license inventory,
  and a capability-register update.
- New labs need their own independent benchmarks before they are exposed.
