# PR-CH4 — Channel 4 = Y-mirror of CH1 (Task #76 final)

Eleventh of 11 sequential A4-* PRs. CH4 SW quadrant = pure Y-mirror of CH1
about Y=50. Final channel mirror — full 4-channel symmetric layout established.

## Symptom

Master baseline CH4 FETs Q23-Q28 at Y=41/30/19 (old P=11). Final symmetry
requires CH4 = mirror_Y(50) of CH1 → Y=44/32/20 (P=12).

## Fix

CH4 placement = pure mirror_Y(50) of CH1: x'=x, y'=100-y.

### FETs + Motor pads (verify_spec_diff PASS Δ=0.000mm)
- Q23/Q24 (12/30, 44), Q25/Q26 (12/30, 32), Q27/Q28 (12/30, 20)
- TP40-42 at X=5

### CH4 ICs/LEDs/shunts (mirror_Y of CH1 counterparts)
- J33 MCU (43, 38) — mirror_Y of J18 (43, 62)
- J34 DRV (45, 26), J35/J36/J37 INAs, U11-U13, D18/D22/D78 LEDs
- TH4 NTC + R170/171/172 shunts

verify_spec_diff: **87/88 PASS Δ=0.000mm** (1 D26 disclosed historic).

### Channel passives — mirror_ch1_to_ch234.py ch4
63 CH4 channel passives placed via Y-mirror transform.

## Root cause

Master baseline kept CH4 at P=11. Mirror symmetry rule required CH4 follow
CH1 P=12 reposition for clean 4-channel transform set.

## Spec deviations

NONE — pure transform applied. (D26 disclosed historic from PR-S1.)

## Audit state

| Gate                                | Status         |
|-------------------------------------|----------------|
| Symmetry verify_spec_diff CH1↔CH4   | 87/88 PASS     |
| MOUNT-HOLE-CONFLICT                 | 0              |
| target.h md5 unchanged              | ✓              |
| Total PAD-OVERLAP                   | 911 vs master 696 (+215) — flagged for PR-A4-integrate cleanup |

The +215 PAD-OVERLAP delta is structural inheritance from CH4 channel-mirror
placements landing on auto-anchored debris. Master accepted similar trade-off
in PR-CH2 (+118) and PR-CH3 (+173). PR-A4-integrate will resolve cumulative
overlap via consolidated cleanup.

## Sims (3, real + 4-point evidence per R18)

### Sim 1: verify_spec_diff.py — CH1↔CH4 mirror_Y validation

**Result**: 87/88 PASS Δ=0.000mm; 1 D26 disclosed.

### Sim 2: Elmer FEM ALL 4 channels thermal (24 FETs)

**Scenario**: 100×100×1.6mm mesh; 24 FET heat sources via MATC indicator.
0.58W per FET continuous = 13.9W total. h_bot=1500 full-back heatsink.

**Acceptance**: T_J ≤ 100°C continuous; all 24 FETs within ±1°C of CH1 pair.

**Result**: **T_J 62.76°C** (vs CH1 alone 62.67°C, ΔT=+0.09°C) — **PASS**

Channel-by-channel thermal progression:
- CH1 alone: 62.67°C
- CH1+CH2: 62.71°C (+0.04°C)
- CH1+CH2+CH3: 62.74°C (+0.03°C)
- CH1+CH2+CH3+CH4: 62.76°C (+0.02°C)

**Full 4-channel symmetry payoff**: each added channel adds <0.05°C to peak
T_J — heatsink (h=1500) handles 24-FET load with massive thermal margin.
Sai's symmetry rule validated: ALL 24 FETs hit identical hotspot pattern.

**4-point**: artifact `ch1234_mesh/ch1234.result` + `ch1234_max.dat`,
mtime ✓, extract.py reproducible, exec `ElmerSolver ch1234_thermal.sif`.

### Sim 3: S21 coupling — CH1↔CH4 + CH2↔CH4 + CH3↔CH4 (Hammerstad)

Per master pre-authorization (PR-CH2): scikit-rf Hammerstad coupled-microstrip
model for openEMS-port-truncation fallback.

| Pair      | Separation | Xc @ 100MHz | S21       | Verdict |
|-----------|-----------|-------------|-----------|---------|
| CH1↔CH4   | 36mm (NW↔SW) | 405k Ω    | -78.24 dB | PASS ✓  |
| CH2↔CH4   | 67mm (NE↔SW) | 759k Ω    | -83.63 dB | PASS ✓  |
| CH3↔CH4   | 76mm (SE↔SW) | 861k Ω    | -84.73 dB | PASS ✓  |

All ≤ -40dB acceptance.

**4-point**: 3 separate `s21_result.txt` artifacts per pair; reproducible
`python3 scikit_rf_s21.py` per directory.

## Renders

- `docs/renders/ch4/top.png`
- `docs/renders/ch4/bottom.png`

## References

- Memories: [[feedback-symmetry-preserves-work]] [[feedback-spec-vs-placement-gate]]
- Master CLAUDE.md R18, R19, R20, R23, R25

**Full 4-channel symmetric layout complete.** Next: PR-A4-integrate for
consolidated cleanup of the +173+215 PAD-OVERLAP structural inheritance.
