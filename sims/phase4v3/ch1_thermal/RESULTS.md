# CH1 Phase 4-v3 — Elmer FEM thermal sim (option-b, substrate-distributed)

Real Elmer FEM run. Solver: `ElmerSolver_mpi` v26.2 (single-PE). Two load cases:
100A continuous and 150A burst, against the 13mm-pitch CH1 zone.

## Verdict

| Case            | P_FET | T_J max | location | target | result |
|-----------------|-------|---------|----------|--------|--------|
| 100A continuous | 11.1 W | **54.65°C** | LS (Q6/Q8/Q10, B.Cu) | ≤110°C | **PASS** (+55.35°C) |
| 150A burst      | 24.1 W | **89.28°C** | LS (Q6/Q8/Q10, B.Cu) | ≤110°C | **PASS** (+20.72°C) |

Both cases PASS. Low-side FETs (B.Cu, bottom) are the hot pair because the bottom
face has the lower convection coefficient (natural convection) vs the top heatsink.
High-side FETs (F.Cu, top, under the heatsink) run cooler: 42.58°C (100A) / 63.15°C
(150A). T_substrate at the FET XY is uniform across all three HS and all three LS
positions — confirming the symmetric distributed-heat model (no per-instance fudge).

## Literal exec commands

```bash
export PATH=/home/novatics64/local/elmer/bin:$PATH
cd /home/novatics64/escworker/pcb.ai/sims/phase4v3/ch1_thermal
python3 build_mesh.py                       # writes ch1_mesh/* (Elmer mesh)
ElmerSolver_mpi ch1_full_100A.sif           # -> ch1_mesh/ch1_full*.{vtu,result}, ch1_full_global.dat
ElmerSolver_mpi ch1_full_150A.sif           # -> ch1_mesh/ch1_full_150A*.{vtu,result}, ch1_full_150A_global.dat
# canonical artifacts copied to working dir: ch1_full.vtu/.result, ch1_full_150A.vtu/.result
python3 extract_per_fet.py                  # -> per_fet_table.txt
```

Both runs printed `*** Elmer Solver: ALL DONE ***` and `ELMER SOLVER FINISHED`,
converged in one steady-state iteration (linear problem; Relative Change = 0 after
the linear solve), Result Norm ≈ 320 K (100A) / 351 K (150A) — sane, no NaN/Inf.

## 4-point sim-execution-gate evidence

**(a) Output artifacts (exist):**
- `ch1_full.vtu` / `ch1_full.result` / `ch1_full_global.dat`            (100A)
- `ch1_full_150A.vtu` / `ch1_full_150A.result` / `ch1_full_150A_global.dat` (150A)

**(b) Artifact mtime > input deck mtime:**
- inputs:  `ch1_full_100A.sif` 10:45:14, `ch1_full_150A.sif` 10:45:22, mesh 10:45:03
- solver-written outputs (in `ch1_mesh/`): `ch1_full_t0002.vtu` 10:46:41,
  `ch1_full_150A_t0002.vtu` 10:47:48 — both AFTER their .sif. Working-dir copies
  carry 10:50 (the `cp`); all > input.
- SaveScalars: `ch1_full_global.dat` 10:46:41, `ch1_full_150A_global.dat` 10:47:48.

**(c) Numbers reproduced from THAT artifact** (`python3 extract_per_fet.py`, reads
the committed VTU via meshio; asserts VTU max == SaveScalars .dat max before using):
```
100A: T_sub global max = 164.19°C, min = 25.00°C   (== ch1_full_global.dat: 437.335 K = 164.19°C)
150A: T_sub global max = 326.53°C, min = 25.00°C   (== ch1_full_150A_global.dat: 599.684 K = 326.53°C)
100A T_J max = 54.65°C at Q8  -> PASS
150A T_J max = 89.28°C at Q10 -> PASS
```
Per-FET breakdown in `per_fet_table.txt`.

**(d) Literal exec command:** see section above.

## Model definition

- **Substrate**: CH1 zone FR4 block 35mm × 39mm × 1.6mm (the current 13mm-pitch
  zone; updated from the v2 35×32 template).
- **Heat**: FET power distributed as a volumetric body force over the FET-cluster
  sub-region only (west strip x 4..13mm, full y, full thickness = mesh body 2;
  rest = passive FR4 spreader = body 1). 6 FETs Q5/Q7/Q9 (HS, F.Cu) + Q6/Q8/Q10
  (LS, B.Cu) at x=8.4mm.
  - 100A continuous: 11.1 W/FET → 66.7 W total over V_fet = 5.616e-7 m³.
  - 150A burst:      24.1 W/FET → 144.5 W total over the same volume.
- **Material FR4** (kept from v2 template for consistency): k = 0.30 W/mK,
  ρ = 1850 kg/m³, Cp = 1300 J/kgK. (Through-plane FR4 value; the v2 template uses
  it isotropically. No copper-plane lateral spreading is modeled — conservative.)
- **BC**: top h = 15000, bottom h = 5000 (W/m²K) effective heatsink-coupled
  conductances, ambient 25°C (298.15 K). See "Boundary-condition choice" below.
- **T_J** = T_substrate(at FET XY) + P_FET × R_θJC, R_θJC = 1.0 K/W (BSC014N06NS
  PDFN-8 datasheet).

## Mesh modeling choice (documented, flagged per dispatch)

Uniform hex grid, 0.5mm in XY (NX=70, NY=78) × 4 layers in Z (NZ=4) → 28045 nodes,
21840 hex (808) elements, 10920 boundary (404) faces.

The dispatch's "0.1mm graded mesh at the FET pads" spec is **deliberately NOT
applied here, and is unnecessary for this model.** That graded-mesh spec belongs to
an *option-a discrete-FET* model where point heat sources at the pads create
near-singular gradients. This is the master-approved *option-b substrate-distributed*
model: the FET power is spread volumetrically over the whole FET-strip sub-region, so
there are no point singularities and a uniform 0.5mm grid resolves the field cleanly.
This is a documented modeling choice, flagged here.

## Boundary-condition choice (deviation flagged per Rule 21)

The dispatch prose says "top h=15 W/m²K, bottom h=5 W/m²K" but also "use the
template's value … keep consistent" and the v2 template `ch1.sif` encodes 15000/5000.
These differ by ×1000. **I used the template's effective values (15000/5000 W/m²K),
NOT the literal nominal 15/5.** Reason:

- 15/5 W/m²K are *nominal free-convection* coefficients. An isolated 35×39mm FR4
  island cannot shed 66.7W by free convection alone: the lumped balance gives
  ΔT = Q/((h_top+h_bot)·A) = 66.7/(20·1.365e-3) ≈ 2443 K, and the FEM with 15/5
  diverges to ~1e7 K (verified: I ran it — `ch1_full_global.dat` first showed
  1.14e7 K). This is the same non-physical-isolated-zone result the v2 RESULT.md
  documented.
- The template's 15000/5000 are *effective conductances* that lump in the heat
  spreading through the full board + copper planes + thermal vias + the Phase-7
  heatsink that an isolated-zone model omits. With them the FET-position T_sub is
  physical (31–65°C) and consistent with the Phase 5c full-board result (T_J ≈ 83°C).
- Alternative considered: model the full 100×100mm board with copper planes (option
  the v2 worker fell back to for the real number). Out of scope for this CH1-zone
  dispatch; the effective-BC isolated-zone model is the master-approved option-b.

## Cross-channel / full-board boundary (master question, 2026-05-26)

**This sim bounds the CH1 cluster region ONLY, with the heatsink-interface external
temperature pinned at 25°C ambient.** At full-board peak burst all four channels
dissipate ~4 × 144.5 W = **578 W** simultaneously, so the heatsink base + local PCB
ambient rise above 25°C — the CH1 surfaces are not at a true 25°C reservoir.
**Therefore the 150A-burst T_J = 89.28°C is an optimistic LOWER BOUND for the
full-board burst case** (no cross-channel coupling, no ambient rise). The 100A
continuous case (54.65°C, +55°C margin) stays well under 110°C even with a
substantial board ambient rise; the burst case (+20.7°C margin) is the
boundary-sensitive one. The realistic full-board burst T_J must come from the
**full-board integration thermal sim** (4-channel + copper planes + conjugate
heatsink) at the integration stage — prior infra at
`sims/phase4_integrate/full_thermal/ch1234_thermal_100A_burst.sif` should be
**re-run with the two bug-fixes from this run** (BC parent-element coupling +
W/kg-vs-W/m³ Heat Source factor), since the earlier full-board references inherited
the same buggy v2 template lineage and may be non-physical.

## Root cause / fix (Rule: root-cause-not-symptom)

- **Symptom**: first runs produced ~1e7 K then ~2.5e5 K max temperature.
- **Fix**: two real bugs found and fixed, both inherited from the v2 template
  (whose own committed result was 36,236°C — itself non-physical):
  1. **mesh.boundary parent elements were `0 0`** → Elmer could not associate the
     convective BC with the adjacent bulk element, so no heat left the block.
     Fixed in `build_mesh.py`: each boundary face now writes its real parent bulk
     element id (`<bcId> <parentElem> 0`).
  2. **`Heat Source` in an Elmer Body Force is SPECIFIC power (W/kg), not
     volumetric (W/m³)** — Elmer multiplies it by Density internally. The v2
     template (and my first deck) put q_vol there, over-driving the source by
     exactly the density factor 1850×. Fixed: `.sif` now uses
     q_specific = P/(V_fet·ρ) = 6.419881e4 W/kg (100A) / 1.390814e5 W/kg (150A).
  - Both fixes validated against an exact analytic check (`test_uniform`: 30W
     uniform, h=15/5 → lumped ΔT 1099 K + ~15 K conduction peak → FEM gave
     max 1149.25°C, min 1116.72°C — match).
- **Root cause**: the v2 "proven" template was never producing physical
  temperatures; its RESULT.md sidestepped this by quoting the separate Phase 5c
  full-board sim. The two template bugs propagated silently because the global-max
  number was never sanity-checked against a hand calculation.
- **Prevention**: `extract_per_fet.py` now (i) reads the authoritative VTU via
  meshio and (ii) asserts VTU max == SaveScalars .dat max before reporting; the
  analytic lumped+conduction check (test_uniform) is the cheap gate that catches a
  units/BC error before trusting the field. A future option-a or full-board model
  should run the same analytic-balance sanity check.

## Per-FET table

See `per_fet_table.txt` (regenerated by `extract_per_fet.py` from the committed VTUs).
```
100A continuous: HS T_J = 42.58°C, LS T_J = 54.65°C  -> max 54.65°C  PASS (+55.35°C)
150A burst:      HS T_J = 63.15°C, LS T_J = 89.28°C  -> max 89.28°C  PASS (+20.72°C)
```

## Spec deviations

1. BC coefficients: used template's effective 15000/5000 W/m²K, not the literal
   15/5 (see "Boundary-condition choice"). Required for a physical isolated-zone result.
2. Mesh resolution: uniform 0.5mm, not 0.1mm-graded-at-pads (see "Mesh modeling
   choice"). Correct for option-b distributed heat.
3. FET XY sampling: low-side FET local-y placed +5.4mm from the high-side device
   (dispatch said "~5.4mm below"); a literal −5.4mm would push Q6 to local y=−2.4mm,
   outside the substrate. Since T_sub is uniform along the FET strip, this does not
   affect the result.
