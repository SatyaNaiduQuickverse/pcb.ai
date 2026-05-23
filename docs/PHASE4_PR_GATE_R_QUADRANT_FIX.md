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

After: 0 gate-Rs flagged. Remaining 64 violations are non-gate-R
passives (BEMF 8, VREF 14, CSA 4, MOTOR 21, LED 1, other 16) which
indicate broader cross-channel placement issues — flagged for a
separate follow-up PR. Breakdown deferred to that PR; not in scope here.

All other 11 audit gates pass (PAD-OVERLAP-DIFFNET=0, MOTOR-PAD-CLEAR=0,
QUADRANT-BALANCE PASS, off-board=0, pad-in-body=0, decoupling clean,
symmetry clean, external-connector-edge clean, TP-spacing clean).

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
