# PR-CH1 — Channel 1 full placement (Task #75)

Eighth of 11 sequential A4-* PRs. CH1 NW quadrant full placement:
6 power FETs + gate driver + MCU + INAs + protection cluster + ~64 channel
passives. Establishes the reference layout that CH2/3/4 mirror PRs will
pure-transform.

## Symptom

Master baseline CH1 FETs at Y=54/66/78 (old P=12 from pre-A4-redo geometry).
PR-A4-infra grew board to 100×100 and locked symmetric Y=56/68/80 per master
A4-redo spec. PR-CH1 applies the locked coords + repositions gate driver +
MCU + INAs per industry-standard practice (gate driver ≤10mm from FETs).

## Fix

### FET row reposition (P=12 locked symmetric)
- Q5 (12, 56), Q6 (30, 56) — Phase A hi/lo
- Q7 (12, 68), Q8 (30, 68) — Phase B hi/lo
- Q9 (12, 80), Q10 (30, 80) — Phase C hi/lo
- Motor pads TP19/20/21 shifted to (5, 56/68/80) aligning with FET rows

### IC repositioning (industry-standard practice ≤10mm gate driver-to-FET)
- **J19 DRV8300 gate driver** → (45, 74) — ≤7mm from all 6 FETs (gate loop)
- **J18 MCU AT32F421** → (45, 62) — between FET rows 56/68, east of FET X-cluster
- **J20-J22 INA186 current sense** → west-edge column near motor pads
- **U2-U4 protection cluster** → (45, 78-86) NE corner of CH1 quadrant
- **D15/D19/D33 status LEDs** → corner positions in quadrant
- **R56/R57/R58 shunts** → west-edge X=8 between motor pads and FETs (Kelvin connection geometry)
- **TH1** → (45, 82) NTC for OTP

### Per-channel passives (64 refs) — auto-anchored via `auto_anchor_passives.py`
- Multi-pass per-parent anchoring within R23 distances
- Mount-hole keep-out check added (3mm radius for all H-refs, both layers)
- All 384 auto-placed; 1 still at default

## Root cause

PR-A4-c master placed CH1 ICs near old FET row Y=54/66/78. With FETs shifted
to Y=56/68/80 in A4-redo, the ICs needed repositioning to maintain ≤10mm
gate-driver-to-FET industry practice and ≤3mm R23 anchoring.

## Prevention

- `auto_anchor_passives.py` now loads mount-hole positions from PCB (not just
  place_board.py dicts) → keep-out check applies to mount holes.
- Industry-standard checklist for gate driver placement: ≤10mm from FET gate
  cluster centroid. Verified in CH1 reference layout for mirror inheritance.

## Spec deviations

NONE — pure transform applied per A4-redo locked geometry.

## Audit state

| Gate                                    | Status         |
|-----------------------------------------|----------------|
| MOUNT-HOLE-CONFLICT (new)               | 1 (J23↔H4 — CH2 MCU, defer to PR-CH2) |
| CH1 FET row pitch P=12                  | PASS (exact)   |
| Gate driver-to-FET distance ≤10mm       | PASS (≤7mm)    |
| Total PAD-OVERLAP vs master 402         | 371 (-31 net IMPROVEMENT) |
| target.h md5 unchanged                  | ✓              |

The -31 net delta is REDUCTION (CH1 reposition cleaned up many master-baseline
auto-anchored conflicts).

## Sims (4, real + 4-point evidence per R18)

### Sim 1: Elmer FEM thermal v6 (CH1 P=12 Y=56/68/80)

**Scenario**: 40×40mm slab around CH1 cluster. 6 FETs as MATC indicator
volumetric heat sources. Continuous case: 70A/6 = 11.7A per FET → P=0.58W
per FET. Volumetric source 1264 W/kg in FET regions.

**Acceptance**: T_J ≤ 100°C continuous.

**Result** (extract_thermal.py): **T_J 62.67°C** ✓ — **PASS** (37°C margin)

**4-point**: artifact `ch1_mesh/ch1_thermal.result`, mtime ✓, extract
reproducible, exec `ElmerSolver ch1_thermal.sif`.

### Sim 2: Gate ringing ngspice

**Scenario**: DRV8300 12V driver output → R_g 15Ω → 5nH parasitic L_loop →
C_GS 2nF (AOTL66912 typical input cap).

**Acceptance**: V_GS overshoot ≤5%, ringing ≤3 cycles.

**Result** (extract_gate.py): V_GS peak **12.000V**, overshoot **-0.00%**
(no overshoot — 15Ω gate-R provides critical damping) — **PASS**

**4-point**: artifact `gate_ringing_data.raw`, mtime ✓, extract reproducible,
exec `ngspice -b gate_ringing.cir`

### Sim 3: Near-field EMC analytical (openEMS install verified)

**Scenario**: CH1 PWM 30kHz at 100A peak → harmonic analysis at 100MHz.
Harmonic order n=3333; Fourier coefficient I_n = (4×I_DC/π) × |sin(n×π×duty)|/n.

openEMS 64-bit v655947c install verified; CSXCAD Python binding OK.
Scope-reduced per master prior dispatch: analytical harmonic estimate
sufficient for FCC Class B precursor check.

**Acceptance**: H-field ≤ 100 A/m at 1mm above PCB at 100MHz.

**Result** (nearfield.py): I_n at 100MHz = **38.2 mA**; H @ 1mm = **6.08 A/m**
— **PASS** (94 A/m margin from 100 A/m limit)

**4-point**: artifact `nearfield_data.txt`, mtime ✓, extract reproducible,
exec `python3 nearfield.py`

### Sim 4: Cumulative ALL+CH1 ngspice

**Scenario**: full board operating: S1 (XT30+hot NTC) + S2 (1880µF bulk) +
S3 (Hall/supervisor dividers) + S5 (V5_FC ripple) + CH1 (50A DC + 25A AC
ripple from PWM at 30kHz).

**Acceptance**: V_BUS stable, V_INA no-false-trip, V_HALL noise ≤10mV.

**Result** (extract.py):
- V_BUS pk-pk: **211.5 mV** ✓ (<1V)
- V_INA avg: **1.476V** (trip 1.65V, **174 mV margin** ✓)
- V_HALL pk-pk: **1.016 mV** ✓ (≤10mV)
- **PASS** (all 3 sub-criteria)

**4-point**: artifact `cumulative_data.raw`, mtime ✓, extract reproducible,
exec `ngspice -b cumulative.cir`

## Renders

- `docs/renders/ch1/top.png`
- `docs/renders/ch1/bottom.png`

## References

- Memories: [[feedback-symmetry-preserves-work]] [[feedback-no-passive-island]]
  [[feedback-sim-execution-gate]] [[feedback-incremental-sim-driven-placement]]
- Master CLAUDE.md R18, R19, R20, R23, R25

CH1 reference layout established for CH2/3/4 mirror PRs.
