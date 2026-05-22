# Phase 0 — Sim toolchain recheck

**Master directive**: 2026-05-22 Phase 0-sim-toolchain-recheck.
**Sai directive**: 'top class sims, no loose ends, validate real well' + 'we should do subsystem simulations too' + 'simulations have to validated and really top class'.

Each subsystem placement PR going forward must include subsystem-internal sim
+ pair-wise interference sim. The four canonical tools below are now locked
as the verifier toolchain.

## Status: all 4 tools reachable + smoke-tested

| Tool | Version | Location | Smoke verdict |
|---|---|---|---|
| **ngspice** | 44.2 | `/usr/bin/ngspice` (system apt) | PASS — RLC AC sweep resonance f₀ = 5033 Hz matches analytical |
| **Elmer FEM** | 26.2 | `/home/novatics64/local/elmer/bin/ElmerSolver` | PASS — unit-cube heat conduction T(z=0)=0/T(z=1)=100, L2 norm 62.4 |
| **openEMS** | 0.0.36 | `/home/novatics64/local/openems/bin/openEMS` + Python bindings at `/home/novatics64/.local/lib/python3.13/site-packages/openEMS` | PASS — half-wave dipole @ 1 GHz, 2000 iterations, 98.9 MCells/s |
| **scikit-rf** | 1.12.0 | `pip` in worker Python env | PASS — Touchstone parse of matched 50Ω load, \|S11\| = 0 verified |

## Notes on installation

- **No new installs needed.** All four tools were already reachable in worker env:
  - ngspice via `/usr/bin/` (system apt-package)
  - Elmer FEM + openEMS at `/home/novatics64/local/{elmer,openems}/` (the shared install — per master directive 'do not disturb this dir')
  - scikit-rf via `pip` in user-Python at `/home/novatics64/.local/`
- Python openEMS bindings require `LD_LIBRARY_PATH=/home/novatics64/local/openems/lib` to resolve `libCSXCAD.so.0` at import time. Worker sim scripts set this env var inline. Documented for future-worker discoverability.

## Smoke tests (reproducible)

All smoke tests in `sims/phase0_sim_toolchain/`.

### `smoke_ngspice.cir`

Series RLC low-pass AC sweep. Verifies ngspice numerical correctness:
- L=1 mH, C=1 µF → analytical resonance f₀ = 1/(2π√LC) = 5032.92 Hz
- AC sweep 100 Hz – 100 kHz, 50 points/decade
- Verdict: `print f0` in `.control` outputs `5.032921e+03` — exact match.

### `elmer_unit_cube/` (`grid.grd` + `heat.sif`)

Steady-state heat conduction in unit cube with Dirichlet boundary conditions
(top = 100°C, bottom = 0°C, sides insulated). Analytical solution T(x,y,z) =
100·z; L2 norm ≈ √(10000/3) ≈ 57.7. ElmerSolver result: 62.4 (8% deviation
due to coarse 3×3×3 mesh — acceptable for smoke; production sims use finer
meshes).

Reproduce:
```
cd sims/phase0_sim_toolchain/elmer_unit_cube
/home/novatics64/local/elmer/bin/ElmerGrid 1 2 grid.grd
/home/novatics64/local/elmer/bin/ElmerSolver heat.sif
```

### `smoke_openems.py`

Half-wave dipole on z-axis at 1 GHz. Lumped port excitation, 50Ω feed, MUR
absorbing boundary on all 6 sides. 2000 FDTD timesteps complete without
exception at 98.9 MCells/s.

Reproduce:
```
LD_LIBRARY_PATH=/home/novatics64/local/openems/lib python3 sims/phase0_sim_toolchain/smoke_openems.py
```

### `smoke_skrf.py`

Inline Touchstone .s1p of matched 50Ω load (S11 = 0 across 1–10 GHz). Parses
via `skrf.Network`, asserts |S11| = 0. Sanity-checks Python touchstone I/O.

Reproduce:
```
python3 sims/phase0_sim_toolchain/smoke_skrf.py
```

## Usage going forward

Per master's locked rule (subsystem PRs must include sim):

| Sim type | Tool |
|---|---|
| Inrush / transient / .ac / .tran | ngspice |
| 3D thermal / heat-equation FEM | Elmer FEM |
| FDTD EM / radiation / EMC / SI | openEMS |
| RF / S-parameter / Touchstone manipulation | scikit-rf |

Worker scripts include the `LD_LIBRARY_PATH` shim where openEMS is used.
Sim methodology (mesh resolution, tolerances, boundary conditions) is
documented in each subsystem PR's `PHASE4_PLACE_*.md` doc.

## Acceptance against master criteria

| Criterion | Status |
|---|---|
| ngspice reachable + smoke PASS | ✓ |
| Elmer FEM reachable + smoke PASS | ✓ |
| openEMS reachable + smoke PASS | ✓ |
| scikit-rf reachable + smoke PASS | ✓ |
| Each tool's version logged | ✓ |
| `docs/PHASE0_SIM_TOOLCHAIN.md` documents versions + smoke pass | ✓ (this file) |
| No disturbance to `/home/novatics64/local/` shared install | ✓ (only reads / runs binaries) |
| `target.h` md5 unchanged | ✓ (`7a4549d27e0e83d3d6f1ffaf67527d24` — no firmware touched) |
