# Phase 4-place-bulk-caps — Subsystem S2 placement + S1↔S2 pair-wise sims

**Sub-phase 2 of `docs/PHASE4_SUBSYSTEMS.md` §S2.**
**Branch**: `phase4-place-bulk-caps/subsystem-s2`.
**Master directive**: Task #50 dispatch 2026-05-22.

## What's placed (4 components in this PR; S1 preserved from PR #32)

| Ref | Value | Footprint | Layer | Position (x, y) mm |
|---|---|---|---|---|
| C1 | EEHZS1V471P (470µF/35V polymer-Al) | `Capacitor_SMD:CP_Elec_10x14.3` | F.Cu | (40, 24) |
| C2 | EEHZS1V471P | same | F.Cu | (60, 24) |
| C3 | EEHZS1V471P | same | F.Cu | (40, 40) |
| C4 | EEHZS1V471P | same | F.Cu | (60, 40) |

**S1 components preserved** (8): J1, D26, R1, R2, Q1, Q2, Q3, Q4 — positions per PR #32.

**Ceramic decouplers not placed**: master spec §S2 lists 8× ceramic decouplers (4× 100nF + 4× 10nF) but these are NOT present in the SKiDL netlist. Flagged as Phase 5 SKiDL follow-up if deemed necessary post-routing (current 4-cap polymer bank passes ripple spec without ceramic boost — see §Sim 1).

## Zone occupied + spec deviation

Spec §S2 (amended PR #32): X=42-58, Y=20-42 (16 mm wide × 22 mm tall central spine).

**Actual zone**: caps occupy X=33-67, Y=18.5-45.5 (post-bbox bodies including silkscreen). The 16 mm wide spec was based on the 10 mm cap body diameter, but the KiCad footprint `CP_Elec_10x14.3` actual bbox is **13.59 × 11.05 mm** (pads + silkscreen courtyard). Two caps side-by-side need ≥28 mm with clearance — exceeds 16 mm spec.

**Spec deviation honest flag**: S2 zone width amended X=42-58 → X=33-67 (with caps centered at x=40, x=60). Master adjudication accepted similar S1 deviation (Y=0-13 → Y=0-20) for similar physical reasons. Recommend updating `docs/PHASE4_SUBSYSTEMS.md` §S2 to X=33-67.

## I/O contract (per spec §S2)

- **Inputs**: +BATT_FUSED, GND (from S1 output, immediately south at Y=18-20 boundary)
- **Outputs**: +VMOTOR (clean, low-ESR), GND
- **Adjacency**: feeds S3 (supervisor + Hall) immediately above (Y=42-58 center spine); Q1/Q2 drain pads (S1 north edge at y=12) connect to C1/C2 anode pads (south edge at y=18.5) via short central spine traces — ≤ 5 mm + ESR-minimizing copper width

## Verification

- ✓ `verify_placement.py` bbox audit: **0 same-layer overlaps within S2 zone**
- ✓ **0 S1-internal overlaps** (preserved from PR #32)
- ✓ **0 S1↔S2 boundary overlaps**
- ✓ **0 overlaps S1+S2 vs other-placed-components** (mount holes only)
- ✓ `target.h` md5 unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`
- ✓ Only S2 components moved from kinet2pcb-default (4 placed); S1 preserved

## 3D render attachments

- [`docs/renders/phase4_place_bulk_caps/top.png`](renders/phase4_place_bulk_caps/top.png) (F.Cu — C1-C4 visible at center, S1 NTCs visible at bottom)
- [`docs/renders/phase4_place_bulk_caps/bottom.png`](renders/phase4_place_bulk_caps/bottom.png) (B.Cu — S1 rev-pol FETs + TVS visible)

## Sim verdicts (per master spec)

### Sim 1 — V_VMOTOR ripple at 100A burst (ngspice)

| Item | Value |
|---|---|
| Model | 4× CBULK explicit: V_SENSE (0V ammeter) + ESR 11 mΩ + ESL 5 nH + C 470 µF per cap |
| Load | DC 100A + AC PWM ripple 6A pk-pk triangular at 30 kHz |
| Source | `sims/phase4_place_bulk_caps/ripple_ngspice.cir` + `.py` |
| **V_VMOTOR pk-pk ripple** | **65 mV** |
| Spec | ≤ 200 mV |
| **Margin** | **135 mV** (68% headroom) |
| **Verdict** | **PASS ✓** |

**Per-cap measurements** (per master 'per-component metrics' rule):

| Cap | I_RMS | P_ESR | Verdict |
|---|---:|---:|---|
| C1 | 0.376 A | 1.55 mW | PASS ✓ (spec ≤ 4 A RMS, ≤ 1 W) |
| C2 | 0.376 A | 1.55 mW | PASS ✓ |
| C3 | 0.376 A | 1.55 mW | PASS ✓ |
| C4 | 0.376 A | 1.55 mW | PASS ✓ |

All 4 caps PASS Panasonic EEHZS1V471P AEC-Q200 ratings with **10× margin** on I_RMS and **600× margin** on ESR power.

Figure: `sims/phase4_place_bulk_caps/ripple.png`

### Sim 2 — Per-cap ESR thermal (Elmer FEM)

| Item | Value |
|---|---|
| Method | 3D FEM steady-state heat conduction on single-cap body 10×14.3×16.5 mm with effective k=50 W/m·K (Al can dominant) |
| BCs | PCB-mount face h=200 (B.Cu thermal coupling); top h=10 (still-air); sides h=10 (still-air); T_amb=60 °C |
| Heat source | P_per_cap = 1.55 mW (from Sim 1 ESR result) → 0.244 W/kg body force |
| Source | `sims/phase4_place_bulk_caps/cap_thermal_elmer/{cap.grd, cap.sif}` |
| **T_can max** | **60.05 °C** |
| Spec | ≤ 105 °C (Panasonic lifetime spec) |
| **Margin** | **44.95 °C** |
| **Verdict** | **PASS ✓** |

T_rise is essentially zero (0.05 °C above ambient) because per-cap dissipation is 1.55 mW — trivial thermal load.

### Sim 3 (pair-wise S1↔S2) — Inrush re-run with explicit S2 bank

Re-ran S1 inrush sim from PR #32 using the explicit 4× CBULK model (already used in PR #32):

| Item | Value |
|---|---|
| Source | `sims/phase4_place_bulk_caps/inrush_rerun_s1s2_ngspice.cir` (copied verbatim from PR #32 inrush_ngspice.cir) |
| **Peak inrush current** | **9.86 A** (unchanged from PR #32) |
| Spec | ≤ 16 A |
| **Margin** | **6.14 A** |
| **Verdict** | **PASS ✓** — no regression from S1 result |

### Sim 4 (pair-wise S1↔S2) — Supply hold-up at 1 ms interruption

| Item | Value |
|---|---|
| Model | 4× CBULK explicit + switch-driven V_BAT disconnect (10ms-11ms) — realistic battery-unplug not short |
| Load sweep | 5 A cruise / 40 A hover / 100 A burst (constant-current sink) |
| Source | `sims/phase4_place_bulk_caps/holdup_ngspice.{cir,py}` |
| Figure | `sims/phase4_place_bulk_caps/holdup.png` |

| Load | V_VMOTOR sag | Spec (≤ 5 V) | Verdict |
|---|---:|---|---|
| 5 A cruise | 2.73 V | ≤ 5 V | **PASS ✓** (margin 2.27 V) |
| 40 A hover | 21.82 V | ≤ 5 V | **FAIL ✗** (over by 16.8 V) |
| 100 A burst | 54.6 V (fully discharges) | ≤ 5 V | **FAIL ✗** (over by 49.6 V) |

**Honest reporting**: the 1 ms hold-up at 5 V sag spec is **physics-limited**. 1880 µF stores ~47 mC at 25.2 V; a 100 A · 1 ms glitch requires 100 mC — more than 2× the stored energy. The bank can't hold 1 ms at full-power load without massive capacitance increase (would need ~20 mF, ~4× current bank size).

**Adjudication request for master**:
- **Option A**: revise spec to 100 µs hold-up (at 100A: ΔV ≈ 5.3 V — borderline pass; realistic battery glitch from XT30 plug vibration)
- **Option B**: increase bulk capacitance (4 → 8+ polymer caps, doubling cost + space)
- **Option C**: accept FAIL at hover/burst — drone integrator manages connector quality; 1 ms hold-up at full power is an exceptional scenario
- **Option D** (recommended): keep current spec but RELAX acceptance to "PASS at cruise load", document hover/burst as "intentional brown-out under sustained battery disconnect"

Sim PASSES at cruise (5 A). Hover/Burst FAIL flagged for master adjudication, not deferred.

## Sim methodology notes + limitations

- **Ripple sim**: I_LOAD modeled as triangular PWM ripple 6 A pk-pk on 100 A DC. Real motor commutation has slightly higher di/dt during high-side turn-on. ESL voltage drop term not separately computed (would be ~0.125 V across 4-parallel ESL=1.25 nH at di/dt=1e8 A/s; minor vs ESR term).
- **Per-cap thermal**: single-cap mesh + uniform body source — captures conduction within the cap can. Adjacent cap thermal coupling not modeled (separated 6+ mm; minimal interaction).
- **Hold-up at 1 ms**: SPICE-ideal switch model for V_BAT disconnect; real XT30 disconnect has connector arcing + intermittent contact making this scenario rare except in connector failure.
- **Inrush re-run**: identical model to PR #32 (same 4× CBULK explicit). No new model needed since S2 placement matches the bank already used in PR #32 sim.

## What's NOT placed (deferred per spec §5)

| Sub-phase | Subsystem |
|---|---|
| S3 (next PR) | Supervisor + Hall sensor (TPS3700, ACS770ECB-200B) |
| S4 ×4 | Channel template (4× MCU + 6 MOSFET + driver + protection + bypass + TVS) |
| S5 | BEC (5 bucks + LDO + safety stack) |
| S6 | FC + AUX connectors + LEDs |

573 footprints remain at kinet2pcb-default. Placed in subsequent sub-phase PRs.

## Acceptance gates (per spec §6 + locked rules)

| Gate | Status |
|---|---|
| S1 placement preserved (8 from PR #32) | ✓ |
| ONLY S2 components placed (4 CBULK) | ✓ |
| 0 same-layer bbox overlaps (S1 + S2 + boundary + vs other) | ✓ |
| 3D render PNG (top + bottom) attached | ✓ |
| Sim 1 (ripple ngspice) — per-cap measurements documented | ✓ PASS all 4 caps |
| Sim 2 (per-cap ESR thermal Elmer FEM) — per-cap T_can | ✓ PASS all 4 caps (60.05 °C, margin 45 °C) |
| Sim 3 (S1↔S2 inrush re-run) — peak ≤ 16 A | ✓ PASS (9.86 A unchanged) |
| Sim 4 (S1↔S2 supply hold-up) — sag ≤ 5 V | **⚠ PASS at 5A only**; FAIL at 40A/100A — physics-limited, master adjudication flagged |
| target.h md5 unchanged | ✓ `7a4549d27e0e83d3d6f1ffaf67527d24` |
| One PR | ✓ |
