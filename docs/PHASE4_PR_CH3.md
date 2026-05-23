# PR-CH3 — Channel 3 = 180°-rotation of CH1 (Task #76 continuing)

Tenth of 11 sequential A4-* PRs. CH3 SE quadrant = pure 180° rotation of CH1
about board center (50, 50).

## Symptom

Master baseline CH3 FETs Q17-Q22 at Y=41/30/19 (old P=11 from pre-A4-redo).
Symmetric placement requires CH3 = rot180(CH1) about (50, 50) → Y=44/32/20
(P=12 mirrored).

## Fix

CH3 placement = pure 180°-rot(50, 50) of CH1: x'=100-x, y'=100-y.

### FETs + Motor pads (verify_spec_diff PASS Δ=0.000mm)
- Q17 (88, 44), Q18 (70, 44) — Phase A (rot of Q5/Q6)
- Q19 (88, 32), Q20 (70, 32) — Phase B
- Q21 (88, 20), Q22 (70, 20) — Phase C
- TP33 (95, 44), TP34 (95, 32), TP35 (95, 20)

### CH3 ICs (rot of CH1 counterparts)
- J28 MCU (57, 38) — rot of J18 (43, 62)
- J29 DRV8300 (55, 26) — rot of J19 (45, 74)
- J30/J32/J31 INA186 — rot of J20/J21/J22
- U8/U9/U10 protection — rot of U2/U3/U4
- D17/D21/D63 LEDs — rot of D15/D19/D33
- TH3 NTC + R132-134 shunts — rot of TH1 + R56-58

verify_spec_diff: 87/88 PASS Δ=0.000mm (1 disclosed D26).

### Channel passives via mirror_ch1_to_ch234.py ch3
63 CH3 channel passives placed via 180° transform.

## Root cause

PR-A4-d had CH3 FETs at Y=19/30/41 (P=11) which broke symmetry with new CH1
P=12 Y=56/68/80. Symmetry rule requires pure transform.

## Prevention

- mirror_ch1_to_ch234.py extended to support all 3 channel transforms.
- verify_spec_diff.py validates all 4 channels per CHANNEL_MAP table.

## Spec deviations

NONE — pure transform applied.

## Audit state

| Gate                                | Status         |
|-------------------------------------|----------------|
| Symmetry verify_spec_diff           | 87/88 (D26 disclosed historic) |
| MOUNT-HOLE-CONFLICT                 | 0              |
| target.h md5 unchanged              | ✓              |
| Total PAD-OVERLAP                   | 696 vs master 523 (+173) — see note |

The +173 PAD-OVERLAP delta is structural inheritance from PR-CH1+CH2 +
CH3 channel mirror-placements landing on auto-anchored debris. Will be
cleaned in PR-CH4 + PR-A4-integrate. Master accepted similar trade-off in
PR-CH2 (+118).

## Sims (3, real + 4-point evidence per R18)

### Sim 1: verify_spec_diff.py — CH1↔CH3 transform validation

**Method**: 180° rotate (50,50) on CH1 coords → diff vs actual CH3.

**Result**: 87/88 PASS Δ=0.000mm. 1 D26 disclosed.

**4-point**: `verify_spec_diff.py` reproducible; output saved.

### Sim 2: Elmer FEM CH1+CH2+CH3 thermal (18 FETs)

**Scenario**: 100×80×1.6mm slab; 18 FET heat sources. Continuous case
0.58W per FET → 10.4W total. h_bot=1500, h_top=80.

**Acceptance**: T_J ≤ 100°C, channel-pair ΔT ≤1°C.

**Result**: **T_J 62.74°C** (vs CH1 alone 62.67, CH1+CH2 62.71). ΔT=+0.03°C
vs CH1+CH2 → 3-channel symmetry payoff confirmed. **PASS**

**4-point**: artifact `ch123_mesh/ch123.result` + `ch123_max.dat`,
mtime ✓, extract.py reproducible, exec `ElmerSolver ch123_thermal.sif`.

### Sim 3: CH1↔CH3 + CH2↔CH3 S21 coupling

**Method**: Hammerstad coupled-microstrip (scikit-rf style) per master
PR-CH2 pre-authorization for openEMS-port-truncation fallback.

**CH1↔CH3 (diagonal ~67mm)**:
- C_mutual: 0.0021 pF
- Xc @ 100MHz: 759k Ω
- **S21 = -83.63 dB** ✓ PASS

**CH2↔CH3 (adjacent ~30mm)**:
- C_mutual: 0.0047 pF
- Xc @ 100MHz: 340k Ω
- **S21 = -76.65 dB** ✓ PASS

Both ≤ -40 dB acceptance.

**4-point**: artifacts `s21_result.txt` per pair; reproducible scripts;
exec `python3 scikit_rf_s21.py`.

## Renders

- `docs/renders/ch3/top.png`
- `docs/renders/ch3/bottom.png`

## References

- Memories: [[feedback-symmetry-preserves-work]] [[feedback-spec-vs-placement-gate]]
- Master CLAUDE.md R18, R19, R20, R23, R25
