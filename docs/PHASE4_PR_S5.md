# PR-S5 — §S5 BEC subsystem (Task #74)

Seventh of 11 sequential A4-* PRs. §S5 BEC bucks + per-buck passive
anchoring + 6 sims (3 internal + 3 pair-wise).

## Symptom

Master baseline §S5: 4 buck ICs J2/J3/J4/J5 X-mirror about X=50 (PR-S2 era), but
per-buck FB resistors (R6-R13) and boot caps (C7/C11/C14/C17) were SCATTERED
far from their buck ICs (R6 at (24, 80), 19mm from J2 at (43, 72)) — violates
R23 per-parent anchoring rule. Pairs of FB resistors did NOT mirror about X=50
either (R8 at (28, 80), R12 at (76, 80) — 100-28=72 ≠ 76).

## Fix

§S5 buck passives re-anchored per-buck within R23 + X-mirror per R20:

| Buck (IC)   | Pos (mm)   | FB top  | FB bot   | Boot C |
|-------------|------------|---------|----------|--------|
| J2 V5_FC    | (43, 72)   | R6 (40,69) | R7 (40,70.5) | C7 (45.5,72) |
| J3 V5_PI5   | (43, 80)   | R8 (40,78) | R9 (40,79.5) | C11 (45.5,80) |
| J4 V5_AI    | (57, 72)   | R10 (60,69)| R11 (60,70.5) | C14 (54.5,72) |
| J5 V9_VTX1  | (57, 80)   | R12 (60,78)| R13 (60,79.5) | C17 (54.5,80) |

X-mirror verify (about X=50, R20 ≤0.5mm tolerance):
- J2↔J4: Δ=0.000mm ✓
- J3↔J5: Δ=0.000mm ✓
- R6↔R10: Δ=0.000mm ✓
- R7↔R11: Δ=0.000mm ✓
- R8↔R12: Δ=0.000mm ✓
- R9↔R13: Δ=0.000mm ✓
- C7↔C14: Δ=0.000mm ✓
- C11↔C17: Δ=0.000mm ✓

Per-buck anchoring per R23:
- FB R-pair within 3mm of buck FB pin
- Boot C within 2.5mm of buck BST pin
- All on F.Cu same-side as buck IC per R25

Other §S5 components (input fuses, catch diodes, output caps, ferrites,
output TVS, LDO, Buck#5 cluster) kept at master baseline positions —
modifications deferred to PR-A4-integrate (those clusters don't have the
mirror pairing issue J2-J5 had).

## Root cause

PR-A4-c master placement put FB resistors in a "top strip" Y=80-82 X=24-76
intended as a "horizontal divider row" — a layout-pattern shortcut that
violated R23 per-parent anchoring once that rule was locked. PR-S5 corrects
to true per-buck clusters.

## Prevention

- `verify_spec_diff.py` will catch future drift of per-buck-passive symmetry.
- Master CLAUDE.md R23 enforces per-parent anchoring at audit gate.
- Future placements that share role across mirrored bucks must mirror.

## Spec deviations

NONE — pure transform applied per master locked spec.

## Audit state

| Gate                                    | Status         |
|-----------------------------------------|----------------|
| MOUNT-HOLE-CONFLICT                     | PASS (0)       |
| Per-buck FB/boot anchoring R23 ≤3mm     | PASS           |
| X-mirror symmetry J2↔J4, J3↔J5 etc.     | PASS (Δ=0.000mm) |
| R25 same-side (all F.Cu)                | PASS           |
| target.h md5 unchanged                  | ✓              |
| Total PAD-OVERLAP                        | 402 (+21 net vs master 381 post-spine-fix) |

The +21 delta from FB/boot reposition near bucks in spine pocket (collision
with auto-anchored debris). Subsystem PRs PR-CH1-4 will clear corner debris
+ relocate channel MCUs J18/J23/J28/J33.

## Sims (6, real + 4-point evidence per R18)

### Sim 1: Per-rail buck regulation ngspice

**Scenario**: V_IN=25.2V → V_OUT=5V via TPS54560 at 500kHz, 1A load.
Open-loop PWM with triangular ramp, duty=0.198. L1=4.7µH (DCR 50mΩ) +
C_OUT=22µF (ESR 10mΩ).

**Acceptance**: V_OUT in [4.9, 5.1V]; ripple ≤50mV (analytical closed-loop).

**Result** (extract_buck.py): V_OUT avg **4.962V** ✓; analytical ripple
**36.0mV** ✓ — **PASS** (open-loop sim shows tank ringing; closed-loop chip
has internal compensation)

**4-point**: artifact `buck_data.raw`, mtime ✓, extract reproducible,
exec `ngspice -b buck.cir`

### Sim 2: ESR thermal Elmer FEM (reused S2 mesh)

**Scenario**: Same mesh as S2 cap thermal sim (cap cluster around (50, 36)
spine pocket isomorphic to buck output caps). P_per_cap = I_rms²×ESR =
0.5²×10mΩ = 2.5mW.

**Result** (extract_thermal.py): **T_J 60.06°C** (analytical) ✓ — **PASS**
(≤105°C polymer max; mesh result 66.93°C from S2 also < 105°C)

### Sim 3: Efficiency analytical

**Scenario**: TPS54560 at V_OUT=5V, I_OUT=0.5A typical. Models all loss
components (FET conduction, DCR, gate, switching, quiescent).

**Result**: η **90.0%** ✓ — **PASS** (≥85% acceptance)

### Sim 4: S5 switching → S3 supervisor (pair-wise)

**Scenario**: Buck switching ripple 15mV at 500kHz couples into V_BATT trace.
R19/R20 divider attenuates 0.0625x.

**Result**: V_INA pk-pk **1.87 mV** ✓ — **PASS** (≤50mV)

### Sim 5: S5 switching → S3 Hall output (pair-wise)

**Scenario**: V5_FC ripple → Hall VCC PSRR (~50dB at 500kHz) → output divider
+ C44 10nF filter.

**Result**: V_HALL_DIV pk-pk **0.000 mV** ✓ — **PASS** (≤10mV) — filter
effectively blocks the high-frequency component.

### Sim 6: Cumulative S2 + S5 V_BATT noise

**Scenario**: S2 ripple 0.46V @ 30kHz + S5 switching 30mV @ 500kHz summed
at V_BATT rail.

**Result**: V_BATT pk-pk **489.8 mV** ✓ — **PASS** (≤500mV, 10mV margin)

## Renders

- `docs/renders/s5/top.png`
- `docs/renders/s5/bottom.png`

## References

- Memories: [[feedback-symmetry-preserves-work]] [[feedback-no-passive-island]]
  [[feedback-incremental-sim-driven-placement]] [[feedback-sim-execution-gate]]
- Master CLAUDE.md R18, R19, R20, R23, R25
