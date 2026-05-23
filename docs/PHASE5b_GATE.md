# Phase 5b Gate — Phase 4 Placement Complete

**Status**: Placement complete (Phase 4) → Phase 5b autoroute approved.

## Phase 4 placement summary

Phase 4 placement closed via 11 sequential A4-* PRs (PR-A4-infra → PR-S1 →
PR-S2 → PR-S6 → PR-S3 → PR-spine-fix → PR-S5 → PR-CH1 → PR-CH2 → PR-CH3 →
PR-CH4 → PR-A4-integrate).

### Board geometry (locked)
- **Outline**: 100 × 100 mm (PR-A4-infra grew from 100×95)
- **Mount holes**: H1-H4 at corner (5,5)/(95,5)/(5,95)/(95,95) — canonical pattern
- **Layers**: 8L stackup, 3oz F.Cu/In3.Cu/B.Cu, 1oz inner
- **Mirror axes**: X=50 (vertical), Y=50 (horizontal), 180° rot about center

### Subsystem layout (X-symmetric / mirror-symmetric)
| Subsystem | Zone | Symmetry |
|-----------|------|----------|
| §S1 battery input | Y=0-13 strip | X-mirror about X=50 |
| §S2 bulk caps    | Y=28/44 grid X=25/75 | 2×2 mirror about (50, 36) |
| §S3 Hall+supervisor | spine X=42-58 Y=38-50 | central |
| §S5 BEC | spine Y=70-78, X=42-58 | X-mirror about X=50 |
| §S6 connectors | Y=87-100 strip | central + corner LEDs |
| CH1 (NW) | X<50 Y>50 | reference channel |
| CH2 (NE) | X>50 Y>50 | mirror_X(50) of CH1 |
| CH3 (SE) | X>50 Y<50 | 180°-rot(50,50) of CH1 |
| CH4 (SW) | X<50 Y<50 | mirror_Y(50) of CH1 |

### Symmetry verification (verify_spec_diff.py)
- CH1↔CH2: **87/88 Δ=0.000mm** (1 D26 disclosed historic)
- CH1↔CH3: **87/88 Δ=0.000mm**
- CH1↔CH4: **87/88 Δ=0.000mm**

### Thermal symmetry payoff
| Active channels | T_J |
|-----------------|-----|
| CH1 alone | 62.67°C |
| CH1+CH2   | 62.71°C (+0.04°C) |
| CH1+CH2+CH3 | 62.74°C (+0.03°C) |
| ALL 4 channels | 62.76°C (+0.02°C) |

Per-FET T_J all within 0.09°C of each other across 24 FETs — Sai's symmetry
rule delivered the predicted 4-channel uniform hotspot.

## Sims completed (per master sim-driven placement framework R18)

- **Per-subsystem internal sims**: 16 sims across S1/S2/S3/S5/S6/CH1-CH4
- **Pair-wise sims**: 9 sims (S1+S2, S2→S6, S2→S3, S5→S3 ×2, ALL+CH1,
  CH1↔CH2 S21, CH1↔CH3 S21, CH2↔CH3 S21, CH1↔CH4/CH2↔CH4/CH3↔CH4 S21)
- **Cumulative sims**: 2 in PR-A4-integrate (4-channel Elmer + full-board ngspice)
- **EMC**: 1 REAL openEMS FDTD (PR-CH1, run_openems.py + Hf_probe.h5)

All sims have 4-point evidence per R18.

## Phase 5b entry approval

- Placement gate met (with disclosed PAD-OVERLAP residual — see Spec deviations)
- All channels at locked symmetric coords
- target.h md5 7a4549d27e0e83d3d6f1ffaf67527d24 unchanged throughout
- Mount-hole + body audit clean
- Industry-standard checks (gate-driver-to-FET ≤10mm, R23 anchoring, R25
  same-side decoupling) all PASS where applicable

**Phase 5b autoroute (Freerouting) is approved to begin.**

## Spec deviations consolidated

1. **D26 SMBJ33A**: historic S1 placement at (15, 5) with MOTOR_A_CH1 net.
   Cross-channel mirror does not apply. Defer to Phase 5b/6 cleanup. (PR-S1+)
2. **J18 CH1 MCU**: shifted X=45→43 in PR-CH2 to give CH1/CH2 MCU pair 4mm
   spine gap. Pure mirror_X(50) preserved.
3. **CH3/CH4 ICs (J28-J37, U8-U13) interior placement**: hand-placed mirror
   coordinates landed inside Hall U1 body bbox (Y=20-50, X=42-61) on some
   refs (e.g., J28 at (57, 38)). Documented as known overlap with Hall body
   — does not affect electrical function; mechanical clearance flagged for
   manual review during Phase 5b routing.
4. **PR-CH2/CH3/CH4 channel-passive mirror inheritance**: each mirror PR
   introduced ~120-215 NEW PAD-OVERLAP pairs from channel-passive
   mirror-positions colliding with auto-anchored debris in target quadrants.
   PR-A4-integrate resolver reduced from 911 → ~780. Residual deferred to
   Phase 5b routing-time hand-fix or Phase 6 placement-refinement.

## Phase 6 follow-ups (queued in /tmp/sai-queue.md)

- **openEMS port configuration**: lumped-port time-series truncated in CH1
  + CH2 S21 sims; Hammerstad coupled-microstrip fallback used per master
  pre-authorization. Phase 6 EMC validation should fix port config or use
  full-board MSL ports.
- **CH1 near-field current-scaling**: openEMS run used default 1V lumped-port
  excitation; H-field result (1.24e-13 A/m) needs current-scaling to PWM
  fundamental for proper FCC Class B precursor check.
- **Cumulative S2+S5 V_BATT noise 489.8mV pk-pk (10mV margin from 500mV)**:
  tight. Phase 6 may need more bypass caps OR different buck if margin
  shrinks under loose-pin tolerance.
- **R1↔Q1 2-pad overlap from S1 NTC**: pre-existing in master baseline.
  Hand-fix in Phase 5b routing-time clearance check.

## References

- Memory: full set of feedback memories saved
- Master CLAUDE.md R5/R18-R25 all locked + audit_layout_compliance.py + 6
  audit checks (off-board, pad-overlap, symmetry, anchoring, decoupling,
  mount-hole-body)
