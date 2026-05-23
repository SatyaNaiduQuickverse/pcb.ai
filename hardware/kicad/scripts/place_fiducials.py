#!/usr/bin/env python3
"""place_fiducials.py — JLC SMT fiducial placement (master 2026-05-24 Sai catch #8).

JLC SMT assembly requires ≥3 fiducial markers per side for machine-vision
pick-and-place alignment. Without fiducials, board is either manually placed
(slow, expensive) or rejected at DFM.

Standard fiducial pattern: 3 corners per side, ≥40mm apart (triangulation
accuracy), ≥5mm from board edge, no components within 3mm clearance.

Fiducial footprint: 1mm copper dot exposed (no mask) on the assembly side.
KiCad library: Fiducial:Fiducial_1mm_Mask2mm

Placement:
  Top side (F.Cu):
    FID1 at (5, 5)    — SW corner inset
    FID2 at (95, 5)   — SE corner inset
    FID3 at (5, 95)   — NW corner inset
  Bottom side (B.Cu):
    FID4 at (95, 95)  — NE corner inset (mirror SW)
    FID5 at (5, 95)   — NW (mirror SE)
    FID6 at (95, 5)   — SE (mirror NW)

Conflict with mount holes H1-H4 at (5,5)/(95,5)/(5,95)/(95,95) ± 5mm:
  Move fiducials inward — corners are taken by mount holes.

Revised positions (avoid H1-H4 keep-out + maintain ≥40mm triangulation):
  Top F.Cu:
    FID1 at (15, 50)   — west-center
    FID2 at (85, 50)   — east-center
    FID3 at (50, 85)   — north-center
  Bottom B.Cu:
    FID4 at (15, 50)   — mirror
    FID5 at (85, 50)
    FID6 at (50, 15)
"""
import pcbnew
import os

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Fiducial library + footprint name (KiCad standard)
FID_LIB = "/usr/share/kicad/footprints/Fiducial.pretty"
FID_FP = "Fiducial_1mm_Mask2mm"

PLACEMENTS = [
    # (ref, x, y, layer)
    ('FID1', 15.0, 50.0, 'F.Cu'),
    ('FID2', 85.0, 50.0, 'F.Cu'),
    ('FID3', 50.0, 85.0, 'F.Cu'),
    ('FID4', 15.0, 50.0, 'B.Cu'),
    ('FID5', 85.0, 50.0, 'B.Cu'),
    ('FID6', 50.0, 15.0, 'B.Cu'),
]


def main():
    board = pcbnew.LoadBoard(PCB)
    existing_refs = {fp.GetReference() for fp in board.GetFootprints()}
    placed = 0
    for ref, x, y, layer in PLACEMENTS:
        if ref in existing_refs:
            # Already there; just reposition
            for fp in board.GetFootprints():
                if fp.GetReference() == ref:
                    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
                    placed += 1
                    print(f"  {ref}: repositioned to ({x}, {y}) {layer}")
                    break
            continue
        try:
            fp = pcbnew.FootprintLoad(FID_LIB, FID_FP)
        except Exception as e:
            print(f"  ERROR loading {FID_FP} from {FID_LIB}: {e}")
            continue
        if fp is None:
            print(f"  ERROR: FootprintLoad returned None for {FID_FP}")
            continue
        fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        if layer == 'B.Cu':
            fp.Flip(fp.GetPosition(), False)
        board.Add(fp)
        placed += 1
        print(f"  {ref}: placed at ({x}, {y}) {layer}")
    board.Save(PCB)
    print(f"\nPlaced {placed} fiducials. Saved {PCB}")


if __name__ == "__main__":
    main()
