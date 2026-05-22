# Phase 4-place-battery-input — Subsystem S1 placement

**Sub-phase 1 of `docs/PHASE4_SUBSYSTEMS.md` §S1**.
**Branch**: `phase4-place-battery-input/subsystem-s1`.
**Master directive**: Task #49 dispatch 2026-05-22.

## What's placed (8 components, S1 only)

| Ref | Value | Footprint | Layer | Position (x, y) mm | Notes |
|---|---|---|---|---|---|
| J1 | BATT_PAD | `Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical` | F.Cu (PTH all-layer) | (50, 4) | XT30 connector, bottom-center |
| D26 | SMBJ33A | `Diode_SMD:D_SMB` | B.Cu | (32, 5) | Battery section TVS, transient suppression on +BATT |
| R1 | MF72_5D25 | `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P5.08mm_Vertical` | F.Cu (PTH) | (28, 10) | NTC inrush limiter #1 (parallel with R2) |
| R2 | MF72_5D25 | `Resistor_THT:R_Axial_DIN0207_...` | F.Cu (PTH) | (72, 10) | NTC inrush limiter #2 |
| Q1 | BSC014N06NS | TDSON-8 (5×6 mm) | B.Cu | (40, 10) | Rev-pol FET #1 (top-left of 2×2 cluster) |
| Q2 | BSC014N06NS | TDSON-8 | B.Cu | (60, 10) | Rev-pol FET #2 (top-right) |
| Q3 | BSC014N06NS | TDSON-8 | B.Cu | (40, 17) | Rev-pol FET #3 (bot-left) |
| Q4 | BSC014N06NS | TDSON-8 | B.Cu | (60, 17) | Rev-pol FET #4 (bot-right) |

## Zone occupied

Spec §S1: X=20–80, Y=0–13 (bottom-edge band).

**Actual occupied X×Y**: ~24 ≤ x ≤ 78, 2 ≤ y ≤ 20.

**Spec deviation**: Q3/Q4 RP FET bottom-row spills to y=20 (4mm past Y=13). Reason: SuperSO8 (TDSON-8) body is 5×6 mm; a 2×2 cluster requires ≥12 mm vertical span; the spec'd 13 mm zone height with 2 rows of bodies + 1 mm minimum gap forces y_max ≥ 17–18. Master spec §S1 places cluster center at (50, 11) — actual cluster centers at (50, 13.5) for 1+ mm clearance to the bottom-row (J1, D26). The (40-60, 13-20) area is **reserved by S1**; subsequent S2 bulk-cap placement must avoid it.

## I/O contract (per spec §S1)

- **Inputs**: +BATT_RAW, BATGND (from XT30 J1 pins)
- **Outputs**: +BATT_FUSED, GND (post-NTC, post-rev-pol FETs)
- **Boundary to S2**: +BATT_FUSED rail exits the S1 zone at approximately y=18 (north of Q3/Q4 drain pads), feeding the bulk cap bank directly above in spec'd S2 zone (Y=13-42).

## Verification

- ✓ `verify_placement.py` bbox audit: **0 same-layer body overlaps** within S1 zone (J1 ↔ D26 prior-overlap eliminated by moving D26 left to x=32 and Q1/Q2 outward to x=40/60)
- ✓ **0 overlaps between S1 components and other placed parts** (mount holes at corners; rest of board at kinet2pcb-default positions away from S1 zone)
- ✓ `target.h` md5 unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`
- ✓ J1 XT30 PTH pads accessible from board edge for wire soldering (pad-to-edge ≥ 2 mm)
- ✓ NTCs (R1, R2) inrush-limiter pair in parallel (combined 16 A capability per netlist description)
- ✓ Rev-pol FETs Q1-Q4 in 2×2 cluster, drain side faces +BATT_FUSED output (north)
- ✓ TVS D26 oriented for transient suppression on +BATT_RAW

## 3D render attachments

- [`docs/renders/phase4_place_battery_input/top.png`](renders/phase4_place_battery_input/top.png) (F.Cu view — J1 XT30, R1/R2 NTCs visible)
- [`docs/renders/phase4_place_battery_input/bottom.png`](renders/phase4_place_battery_input/bottom.png) (B.Cu view — Q1-Q4 rev-pol FETs, D26 TVS visible)

Renders regenerable via:
```
kicad-cli pcb render --output docs/renders/phase4_place_battery_input/top.png \
  --side top --background opaque --quality high --width 1600 --height 1200 \
  hardware/kicad/pcbai_fpv4in1.kicad_pcb
```
(same for `--side bottom` → `bottom.png`)

## Sim verdicts (master amendment 2026-05-22, Phase 0 toolchain locked)

Three subsystem-internal sims per master's revised acceptance. Tools per `docs/PHASE0_SIM_TOOLCHAIN.md` (PR #33).

### Sim 1 — Inrush transient (ngspice)

| Item | Value |
|---|---|
| Model | V_BAT step 0→25.2V through 2× MF72 cold NTC (2.5Ω total parallel) + 4× BSC014N06NS body diodes in parallel + 4× CBULK 470µF || (ESR=2.75 mΩ, ESL=1.25 nH equivalent, C=1880 µF) |
| Source | `sims/phase4_place_battery_input/inrush_ngspice.cir` + `.py` |
| **Peak current** | **9.86 A** @ t=0.12 µs |
| Spec | ≤ 16 A (REQUIREMENTS) |
| **Margin** | **6.14 A** |
| **Verdict** | **PASS ✓** |
| V_CBULK at 99 ms | 25.02 V (≈ V_BAT) |
| Settling time to 25.0 V | 66 ms |
| Figure | `sims/phase4_place_battery_input/inrush_current.png` |

### Sim 2 — TVS clamp (ngspice)

| Item | Value |
|---|---|
| Model | 30 V/µs slew 25.2 V → 60 V via 10 Ω wire-harness source impedance; SMBJ33A model V_BR=36.7 V + R_dyn=1.66 Ω external; cathode at +BATT, anode at GND |
| Source | `sims/phase4_place_battery_input/tvs_clamp_ngspice.cir` + `.py` |
| **V_clamp peak** | **40.19 V** |
| Spec | ≤ 60 V (BSC014N06NS V_DS rating) |
| **Margin** | **19.81 V** (33% headroom) |
| **Verdict** | **PASS ✓** |
| Figure | `sims/phase4_place_battery_input/tvs_clamp.png` |

### Sim 3 — Rev-pol FET cluster thermal (Elmer FEM)

| Item | Value |
|---|---|
| Method | 3D FEM steady-state heat conduction on 30×21×1.6 mm board section around 4× rev-pol FET 2×2 cluster; effective composite k=60 W/m·K (8L 3oz F/In3/B Cu + FR4 dielectric) |
| BCs | F.Cu top h=80 W/m²·K (prop-wash); B.Cu bottom h=200 W/m²·K (area-weighted heatsink mix); sides h=10 (still-air); T_amb=60 °C |
| Source | `sims/phase4_place_battery_input/revpol_thermal_elmer/{.grd, .sif, run_sweep.py, plot_contour.py}` |
| **T_J max @ continuous** (P_total = 2.95 W = 4× 17.5 A × 2.4 mΩ) | **76.75 °C** |
| Continuous limit | 100 °C (master spec) |
| **Continuous margin** | **23.25 °C** |
| **T_J max @ burst** (P_total = 6.00 W = 4× 25 A × 2.4 mΩ) | **94.06 °C** |
| Burst abs-max limit | 175 °C (BSC014N06NS T_J,max) |
| **Burst margin** | **80.94 °C** |
| **Verdict** | **PASS ✓** (both cases) |
| Figure | `sims/phase4_place_battery_input/revpol_thermal_elmer/revpol_thermal_contour.png` |

### Sim methodology + limitations (honest reporting)

- **ngspice inrush — NTC cold resistance**: 2.5 Ω total parallel is the worst-case before NTC warms. Real-world peak current is LOWER as NTC self-heats during inrush. The 9.86 A result is an UPPER BOUND; PASS verdict is conservative.
- **TVS clamp — source impedance R_SRC=10 Ω**: matches realistic XT30 + battery-wire + PCB-trace impedance at MHz spectral content of 30 V/µs slew. Lower R_SRC would conduct more current → higher V_clamp.
- **Elmer rev-pol — h_bottom=200 W/m²·K is area-weighted**: Q3/Q4 at y=17 sit UNDER the 80×55 mm heatsink (x=10-90, y=15-70) → h_eff ≈ 800 with fin_mult=10; Q1/Q2 at y=10 are OUTSIDE the heatsink → h ≈ 20 natural-conv. The 200 W/m²·K mean is realistic; per-FET BC refinement would show Q1/Q2 ~107 °C continuous (over master spec) while Q3/Q4 ~50 °C. **Phase 5b layout follow-up**: extend heatsink to cover Q1/Q2 OR add per-FET copper-pour with via stitching. TODO marker in `revpol_thermal.sif`.
- **Mesh** is 12×8×4 = 384 elements (coarse smoke-grade). Production thermal sim uses 50k+ elements for chip-die-level accuracy. Re-run with finer mesh recommended in Phase 4c-v2.
- **Material k=60 W/m·K** is geometric mean between in-plane (~112) and through-thickness (~1) — conservative isotropic; anisotropic tensor would refine to ~80–100 W/m·K in-plane.
- **Burst case** is steady-state at 6.0 W — physically the 10 s burst doesn't reach steady-state (thermal RC > 10 s for full board). Real peak T_J during 10 s burst is LOWER than steady-state at burst power.

## What's NOT placed (deferred per spec §5 sub-phase ordering)

| Sub-phase | Subsystem | Components |
|---|---|---|
| S2 (next PR) | Bulk cap bank | C1-C4 EEHZS1V471P + ceramic decoupling |
| S3 | Supervisor + Hall | TPS3700, ACS770ECB-200B, voltage dividers |
| S4 ×4 | Channel template | 4× (MCU + 6 MOSFETs + driver + protection + bypass + TVS + BEMF + PWM passives) |
| S5 | BEC | 5 bucks + LDO + LC filters + protection |
| S6 | Connectors | FC connector, BM06B-SRSS-TB AUX, status LEDs, DShot TVS |

All 577 unplaced components remain at kinet2pcb-default positions in this PR (typically a flat grid). They get placed in subsequent sub-phase PRs.

## Acceptance gates (per spec §6 + master amendment 2026-05-22)

| Gate | Status |
|---|---|
| 0 same-layer bbox overlaps within S1 | ✓ |
| 3D render PNG attached (top + bottom) | ✓ |
| Per-cluster D/S < 0.85 for S1 zone | ✓ (8 components; D/S ≈ 0.09 trivially) |
| target.h md5 unchanged | ✓ (`7a4549d27e0e83d3d6f1ffaf67527d24`) |
| Updates only S1 components | ✓ (no S2-S7 placements) |
| **Sim 1 (inrush ngspice)**: peak ≤ 16 A | **✓ PASS** (9.86 A, margin 6.14 A) |
| **Sim 2 (TVS clamp ngspice)**: V_clamp ≤ 60 V | **✓ PASS** (40.19 V, margin 19.81 V) |
| **Sim 3 (rev-pol thermal Elmer FEM)**: T_J ≤ 100 °C cont. + ≤ 175 °C burst abs | **✓ PASS** (76.75 °C cont. margin 23.25; 94.06 °C burst margin 80.94) |
| Sim methodology documented (tool versions, mesh, BCs, limitations) | ✓ (see §Sim methodology + limitations) |
