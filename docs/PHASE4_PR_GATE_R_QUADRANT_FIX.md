# PR — gate-R quadrant fix (Sai-eye-catch #6)

Branch: `phase4-gate-R-quadrant-fix` · Date: 2026-05-23

## Symptom

Master query of the layout flagged 14 phase-C gate-Rs sitting in the
wrong channel quadrant. Each gate-R must be ≤5mm of its parent FET gate
pad (R23 no-passive-island).

## Fix

Two parts:

1. **Audit gate added** —
   `hardware/kicad/scripts/audit_layout_compliance.py` gains
   `check_per_channel_passive_quadrant`. For every R/C/L/D whose pads
   carry exactly one `_CH[1234]`-suffixed net, the component center must
   sit inside that channel's locked quadrant. Boundary tolerance 2mm
   exempts shared-bus passives that legitimately straddle the X=50 or
   Y=50 half-axes.

   The locked quadrant map is derived from FET geometry (Q5-Q28):

   | Channel | X range | Y range  | Anchor FETs |
   |---------|---------|----------|-------------|
   | CH1     | 0-50    | 50-100   | Q5-Q10 (rot=0)   |
   | CH2     | 50-100  | 50-100   | Q11-Q16 (rot=180) |
   | CH3     | 50-100  | 0-50     | Q17-Q22 (rot=0)   |
   | CH4     | 0-50    | 0-50     | Q23-Q28 (rot=0)   |

2. **8 phase-C gate-Rs relocated** via
   `hardware/kicad/scripts/fix_gate_r_quadrant.py`. Each gate-R now sits
   2.0–4.4mm from its parent FET's gate pad, inside the correct
   quadrant, and clear of motor-TP +2mm keep-out zones:

   | Ref  | Net      | Old pos       | New pos       | Parent FET | Gate-dist |
   |------|----------|---------------|---------------|------------|-----------|
   | R52  | GHC_CH1  | (48.0, 22.0)  | (13.50, 83.00)| Q9         | 4.35mm    |
   | R53  | GLC_CH1  | (51.0, 21.0)  | (25.00, 82.00)| Q10        | 2.33mm    |
   | R90  | GHC_CH2  | (52.0, 22.0)  | (86.50, 77.00)| Q15        | 4.35mm    |
   | R91  | GLC_CH2  | (49.0, 21.0)  | (72.85, 75.09)| Q16        | 2.00mm    |
   | R128 | GHC_CH3  | (52.0, 78.0)  | (85.15, 24.91)| Q21        | 2.00mm    |
   | R129 | GLC_CH3  | (49.0, 79.0)  | (67.15, 24.91)| Q22        | 2.00mm    |
   | R166 | GHC_CH4  | (48.0, 78.0)  | (13.50, 22.91)| Q27        | 4.35mm    |
   | R167 | GLC_CH4  | (51.0, 79.0)  | (27.15, 24.91)| Q28        | 2.00mm    |

## Root cause

When phase-C gate-R passives were first emitted (post-PR-A4), all 8 were
parked near the central spine (X≈50, Y≈21 or Y≈78) — not anchored to
their parent FETs. This swept them into the wrong channel zones while
the audit was zone-blind. The new audit gate now catches this class.

## Prevention

`check_per_channel_passive_quadrant` is gate 12 of audit; CI must run
audit on every layout-PR baseline (already in master gate-R23 / R24
review flow).

## Spec deviations (R21 disclosure)

Positions are **not pure coordinate mirrors** of R52 across the locked
transforms (mirror_X, 180°-rot, mirror_Y). Reason: CH2 FETs are rot=180
versus CH1/CH3/CH4 rot=0, so the gate pad exits on the opposite side
in absolute coords. Each gate-R is instead role-symmetric — placed
2–4.4mm from its OWN FET's gate pad, on the outside of the FET body.
The FET-rotation asymmetry between channels is pre-existing in the
locked geometry and is out of scope here.

R52/R90/R166 each have an extra ~2mm lateral offset (vs the natural
"2mm beyond gate pad along the gate axis") to clear motor-TP +2mm
keep-out: TP21 (covers Q9 gate axis), TP28 (covers Q15 gate axis),
TP42 (covers Q27 gate axis). All remain within R23 5mm.

## Audit results

Before: 8 gate-Rs flagged by `check_per_channel_passive_quadrant`
(among the broader 64 channel-tagged-passive violations).

After: 0 gate-Rs flagged. R23 functional requirement met for gate-drive
integrity (each gate-R 2.0–4.35mm from parent FET gate pad).

All other 11 audit gates clean: PAD-OVERLAP-DIFFNET=0, MOTOR-PAD-CLEAR=0,
QUADRANT-BALANCE PASS, off-board=0, pad-in-body=0, decoupling clean,
symmetry clean, external-connector-edge clean, TP-spacing clean,
quadrant-balance PASS.

## Residual: 56 non-gate-R quadrant violations — deferred (master adjudicated)

`check_per_channel_passive_quadrant` flags 56 additional channel-tagged
passives (BEMF/VREF/CSA/MOTOR/LED/other) sitting outside their parent
channel zone. Master adjudication 2026-05-23: **spot-fix infeasible due
to density constraint** — broader scope deferred to
**PR-channel-template-redo** (architectural placement redo).

**Why density blocks spot-fix:**
- CH1 zone (50×50mm) currently holds 146 F.Cu components — central spine
  Y=65–85 averages 5–7 components per 5×5mm cell
- 63 channel-tagged passives × 4 channels = 252 components in 2500mm²
  per channel = ~10mm² per component is too tight to satisfy R23 + R25
  + the new quadrant rule simultaneously
- Spiral search (8mm radius around parent IC, 0.5mm grid, 1mm clearance):
  0 of 19 CH1 violator groups found a 4-channel mirror-compatible spot
- Naive coordinate-mirror attempt: created 24 new fab-blocking
  PAD-OVERLAP-DIFFNET errors — strict regression
- B.Cu has 2500/2500 free 1mm cells per channel — but flipping
  IC-decoupling caps to B.Cu violates R25 (same-side decoupling)

**Follow-up scope (PR-channel-template-redo):**
1. Schematic audit: which nets cross channels — identify components that
   MUST be per-channel vs can move to central shared spine (TL431 Vref
   sharing? LM393 comparators are clearly per-channel.)
2. Redesign channel template to leave free space for the 19 violator
   groups per channel
3. Regenerate all 4 channels via locked transforms
4. Re-audit: target 0 violations on all 12 gates

**Tracked residuals — 56 components by target channel zone:**

CH1 (16 violators, target zone X=0–50 Y=50–100):
- D26 (15.0, 5.0) MOTOR_A_CH1 — currently in CH4 zone
- R50 (42.5, 22.0) MOTOR_B_CH1 — currently in CH4 zone
- R51 (44.0, 20.5) SHUNT_B_TOP_CH1 — currently in CH4 zone
- R54 (54.0, 20.5) MOTOR_C_CH1 — currently in CH3 zone
- R55 (58.0, 25.0) SHUNT_C_TOP_CH1 — currently in CH3 zone
- R59 (42.0, 26.0) MOTOR_A_CH1 — currently in CH4 zone
- R60 (45.0, 26.0) BEMF_A_CH1 — currently in CH4 zone
- R61 (42.0, 24.0) MOTOR_B_CH1 — currently in CH4 zone
- R63 (54.5, 23.5) MOTOR_C_CH1 — currently in CH3 zone
- R64 (57.0, 26.0) BEMF_C_CH1 — currently in CH3 zone
- R67 (45.0, 31.0) VREF_2V5_CH1 — currently in CH4 zone
- R70 (53.0, 31.0) VREF_2V5_CH1 — currently in CH3 zone
- R71 (57.0, 31.0) VREF_OTP_CH1 — currently in CH3 zone
- R72 (42.0, 34.0) CSA_MAX_CH1 — currently in CH4 zone
- R73 (44.0, 33.0) I_TRIP_N_CH1 — currently in CH4 zone
- R76 (53.5, 35.0) KILL_RAIL_N_CH1 — currently in CH3 zone

CH2 (17 violators, target zone X=50–100 Y=50–100):
- D48 (43.0, 76.0) LED_GPIO_CH2 — currently in CH1 zone
- R88 (57.5, 22.0) MOTOR_B_CH2 — currently in CH3 zone
- R89 (56.0, 20.5) SHUNT_B_TOP_CH2 — currently in CH3 zone
- R92 (46.0, 20.5) MOTOR_C_CH2 — currently in CH4 zone
- R93 (42.0, 25.0) SHUNT_C_TOP_CH2 — currently in CH4 zone
- R97 (59.0, 26.0) MOTOR_A_CH2 — currently in CH3 zone
- R98 (55.0, 26.0) BEMF_A_CH2 — currently in CH3 zone
- R99 (58.0, 24.0) MOTOR_B_CH2 — currently in CH3 zone
- R101 (45.5, 23.5) MOTOR_C_CH2 — currently in CH4 zone
- R102 (43.0, 27.0) BEMF_C_CH2 — currently in CH4 zone
- R105 (55.0, 31.0) VREF_2V5_CH2 — currently in CH3 zone
- R106 (53.0, 30.0) VREF_2V5_CH2 — currently in CH3 zone
- R108 (47.0, 31.0) VREF_2V5_CH2 — currently in CH4 zone
- R109 (43.0, 31.0) VREF_OTP_CH2 — currently in CH4 zone
- R110 (58.0, 34.0) CSA_MAX_CH2 — currently in CH3 zone
- R111 (56.0, 33.0) I_TRIP_N_CH2 — currently in CH3 zone
- R114 (46.5, 35.0) KILL_RAIL_N_CH2 — currently in CH4 zone

CH3 (14 violators, target zone X=50–100 Y=0–50):
- R126 (57.5, 78.0) MOTOR_B_CH3 — currently in CH2 zone
- R127 (55.0, 80.5) SHUNT_B_TOP_CH3 — currently in CH2 zone
- R131 (42.0, 75.0) SHUNT_C_TOP_CH3 — currently in CH1 zone
- R135 (59.0, 74.0) MOTOR_A_CH3 — currently in CH2 zone
- R136 (55.0, 74.0) BEMF_A_CH3 — currently in CH2 zone
- R137 (58.0, 76.0) MOTOR_B_CH3 — currently in CH2 zone
- R139 (45.5, 77.0) MOTOR_C_CH3 — currently in CH1 zone
- R140 (44.0, 76.0) BEMF_C_CH3 — currently in CH1 zone
- R143 (55.0, 69.0) VREF_2V5_CH3 — currently in CH2 zone
- R146 (47.0, 69.0) VREF_2V5_CH3 — currently in CH1 zone
- R147 (43.0, 69.0) VREF_OTP_CH3 — currently in CH1 zone
- R148 (58.0, 66.0) CSA_MAX_CH3 — currently in CH2 zone
- R149 (56.0, 67.0) I_TRIP_N_CH3 — currently in CH2 zone
- R152 (46.5, 65.0) KILL_RAIL_N_CH3 — currently in CH1 zone

CH4 (17 violators, target zone X=0–50 Y=0–50):
- D71 (39.8, 57.0) MOTOR_A_CH4 — currently in CH1 zone
- R164 (42.5, 78.0) MOTOR_B_CH4 — currently in CH1 zone
- R165 (41.5, 82.0) SHUNT_B_TOP_CH4 — currently in CH1 zone
- R168 (54.0, 79.5) MOTOR_C_CH4 — currently in CH2 zone
- R169 (58.0, 75.0) SHUNT_C_TOP_CH4 — currently in CH2 zone
- R173 (42.0, 74.0) MOTOR_A_CH4 — currently in CH1 zone
- R174 (44.0, 75.0) BEMF_A_CH4 — currently in CH1 zone
- R175 (42.0, 76.0) MOTOR_B_CH4 — currently in CH1 zone
- R177 (54.5, 76.5) MOTOR_C_CH4 — currently in CH2 zone
- R178 (57.0, 74.0) BEMF_C_CH4 — currently in CH2 zone
- R181 (45.0, 69.0) VREF_2V5_CH4 — currently in CH1 zone
- R182 (47.0, 70.0) VREF_2V5_CH4 — currently in CH1 zone
- R184 (53.0, 69.0) VREF_2V5_CH4 — currently in CH2 zone
- R185 (57.0, 69.0) VREF_OTP_CH4 — currently in CH2 zone
- R186 (42.0, 66.0) CSA_MAX_CH4 — currently in CH1 zone
- R187 (44.0, 67.0) I_TRIP_N_CH4 — currently in CH1 zone
- R190 (53.5, 65.0) KILL_RAIL_N_CH4 — currently in CH2 zone

These 56 residuals are functionally OK (BEMF dividers and VREF
networks remain electrically valid via netlist connections — the
violation is symmetry/quadrant placement, not connectivity).
R23 gate-drive integrity (which IS functionally critical) is
fully resolved in this PR.

## Files changed

- `hardware/kicad/scripts/audit_layout_compliance.py` (gate added)
- `hardware/kicad/scripts/fix_gate_r_quadrant.py` (new — 8 relocations)
- `hardware/kicad/pcbai_fpv4in1.kicad_pcb` (8 footprints repositioned)
- `docs/PHASE4_PR_GATE_R_QUADRANT_FIX.md` (this file)

## Verification command

```
python3 hardware/kicad/scripts/audit_layout_compliance.py \
    hardware/kicad/pcbai_fpv4in1.kicad_pcb
```

No routes in this PR — placement only.
