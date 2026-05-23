#!/usr/bin/env python3
"""fix_gate_r_quadrant.py — PR-gate-R-quadrant-fix.

Master directive 2026-05-23: 14+ phase-C gate-Rs are in wrong channel
quadrant. Relocate to within R23 (≤5mm of parent FET gate pad) AND
inside the channel's locked zone.

The 8 C-phase mismatches identified by audit gate
check_per_channel_passive_quadrant:
  R52 GHC_CH1, R53 GLC_CH1     (near Q9/Q10 rot=0,  Y=80)
  R90 GHC_CH2, R91 GLC_CH2     (near Q15/Q16 rot=180, Y=80)
  R128 GHC_CH3, R129 GLC_CH3   (near Q21/Q22 rot=0,  Y=20)
  R166 GHC_CH4, R167 GLC_CH4   (near Q27/Q28 rot=0,  Y=20)

Note on symmetry: pure coord mirror is INSUFFICIENT here because
CH2 FETs are rot=180 (their gate pads face the opposite direction
in absolute coords). Each gate-R is placed 2.0mm from its OWN
FET's gate pad — symmetric in role, not in raw XY.

PDFN-8 gate pad (pad 4) location relative to FET center:
  rot=0:   (cx - 2.85, cy + 2.91)
  rot=180: (cx + 2.85, cy - 2.91)
Gate-R offset 2.0mm further from FET body in the same direction.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"


def mm_to_iu(x):
    return pcbnew.FromMM(x)


# (ref, parent_FET_center_x, parent_FET_center_y, fet_rot) → new gate-R position
# Gate-R sits 2.0mm beyond the gate pad along the same axis the gate exits
RELOC = [
    # CH1 (Y=50-100): FETs rot=0, gate south. TP21@(5,80) bbox X[-,10.39]
    # forces R52 outside X>10.39. TP9@(25,86) bbox Y[82.6,89.25] forces
    # R53 below Y=82.60. Both kept within R23 (≤5mm of gate pad).
    # Motor-TP +2mm keep-out forces R52/R90/R166 off the natural axis.
    # TP21+2mm = X[-2.39, 12.39] Y[74.75, 85.40]
    ('R52',  12.0, 80.0,   0, (13.50, 83.00)),   # GHC_CH1 → Q9 (dist 4.35mm, clears TP21)
    ('R53',  30.0, 80.0,   0, (25.00, 82.00)),   # GLC_CH1 → Q10 (dist 2.33mm, Y<82.60 clears TP9 bbox)
    # CH2 FETs rot=180, gate north. TP28+2mm = X[87.61, 102.39] Y[74.60, 85.25]
    ('R90',  88.0, 80.0, 180, (86.50, 77.00)),   # GHC_CH2 → Q15 (dist 4.35mm, clears TP28)
    ('R91',  70.0, 80.0, 180, (72.85, 75.09)),   # GLC_CH2 → Q16 (dist 2.00mm, no TP conflict)
    # CH3 FETs rot=0, gate south. TP35@(95,20) bbox+2mm X[87.61, -] — R128
    # at X=85.15 is left of zone. No conflict.
    ('R128', 88.0, 20.0,   0, (85.15, 24.91)),   # GHC_CH3 → Q21 (dist 2.00mm)
    ('R129', 70.0, 20.0,   0, (67.15, 24.91)),   # GLC_CH3 → Q22 (dist 2.00mm)
    # CH4 FETs rot=0. TP42+2mm = X[-2.39, 12.39] Y[14.75, 25.40] — push R166 east.
    ('R166', 12.0, 20.0,   0, (13.50, 22.91)),   # GHC_CH4 → Q27 (dist 4.35mm, clears TP42)
    ('R167', 30.0, 20.0,   0, (27.15, 24.91)),   # GLC_CH4 → Q28 (dist 2.00mm)
]
# NOTE on symmetry (R19/R21 disclosure): These positions are NOT pure
# mirror transforms of R52. They are role-symmetric (each gate-R sits
# ~2-3mm from its FET's gate pad on the outside) but coord-asymmetric
# because (a) CH2 FETs are rot=180 vs CH1 rot=0 — gate exits opposite
# side, (b) TP test-point pads occupy different absolute corners after
# Sai-eye-catch #4 spreading. Symmetry preserved at FET-gate-pad level,
# not raw XY level.


def main():
    board = pcbnew.LoadBoard(PCB)
    by_ref = {f.GetReference(): f for f in board.GetFootprints()}

    moved = 0
    for ref, fx, fy, frot, (nx, ny) in RELOC:
        fp = by_ref.get(ref)
        if fp is None:
            print(f"  {ref}: not found — skip")
            continue
        old = fp.GetPosition()
        ox, oy = pcbnew.ToMM(old.x), pcbnew.ToMM(old.y)
        fp.SetPosition(pcbnew.VECTOR2I(mm_to_iu(nx), mm_to_iu(ny)))
        # Distance to gate-pad (R23 check)
        if frot == 0:
            gpx, gpy = fx - 2.85, fy + 2.91
        else:  # 180
            gpx, gpy = fx + 2.85, fy - 2.91
        dist = ((nx - gpx) ** 2 + (ny - gpy) ** 2) ** 0.5
        ok = "OK" if dist <= 5.0 else "FAIL"
        print(f"  {ref}: ({ox:.2f},{oy:.2f}) → ({nx:.2f},{ny:.2f})  gate-dist={dist:.2f}mm {ok}")
        moved += 1

    board.Save(PCB)
    print(f"\nMoved {moved} gate-Rs. Saved {PCB}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
