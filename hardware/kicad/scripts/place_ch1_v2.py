#!/usr/bin/env python3
"""place_ch1_v2.py — Phase 4-v2 Step 2 CH1 placement.

Place CH1 components within zone (0, 50, 35, 82) per BOARD_INVARIANTS.md.

Anchor positions (FETs already there + new IC placements):
- Q5/Q7/Q9: (12, 56)/(12, 68)/(12, 80) — west column
- Q6/Q8/Q10: (30, 56)/(30, 68)/(30, 80) — east column
- J18 MCU: (25, 80) — north central (in zone)
- J19 DRV: (20, 62) — central row, between FET rows
- J20 INA-A: (10, 62) — west
- J21 INA-B: (8, 75) — west
- J22 INA-C: (25, 76) — NE of Q9 (moved from S6 area into CH1)
- U3 LM393: (25, 80.5) — but conflict with J18 at (25,80); move to (28, 80)
- U4 LM393: (15, 72) — between FET rows, west
- LEDs D15/D19: near MCU (24, 78)/(26, 78)

Channel passives (resistors, caps, diodes) get auto-anchored to FET/DRV/MCU pads.
"""
import pcbnew
import re

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Hard-locked CH1 positions per Phase 4-v2 zone (0, 50, 35, 82)
CH1_POSITIONS = {
    # FETs (already at correct positions — confirm)
    'Q5':  (12.0, 56.0, 'F.Cu', 0.0),
    'Q6':  (30.0, 56.0, 'F.Cu', 0.0),
    'Q7':  (12.0, 68.0, 'F.Cu', 0.0),
    'Q8':  (30.0, 68.0, 'F.Cu', 0.0),
    'Q9':  (12.0, 80.0, 'F.Cu', 0.0),
    'Q10': (30.0, 80.0, 'F.Cu', 0.0),
    # ICs — relocate into zone
    'J18': (22.0, 78.0, 'F.Cu', 0.0),    # MCU QFN-32, central
    'J19': (20.0, 62.0, 'F.Cu', 0.0),    # DRV HVQFN-24, between FET rows
    'J20': (10.0, 62.0, 'F.Cu', 0.0),    # INA-A SOT-363 (already there)
    'J21': (8.3, 75.5, 'F.Cu', 0.0),     # INA-B SOT-363 (already there)
    'J22': (25.0, 76.0, 'F.Cu', 0.0),    # INA-C SOT-363, moved from (40,92)
    'U3':  (28.0, 80.0, 'F.Cu', 0.0),    # LM393 SOIC-8, NE corner
    'U4':  (15.0, 72.0, 'F.Cu', 0.0),    # LM393 SOT-353
    # Motor TPs (already at edge X=5)
    'TP19': (5.0, 56.0, 'F.Cu', 0.0),
    'TP20': (5.0, 68.0, 'F.Cu', 0.0),
    'TP21': (5.0, 80.0, 'F.Cu', 0.0),
}


def main():
    b = pcbnew.LoadBoard(PCB)
    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
    moved = 0
    for ref, (x, y, layer, rot) in CH1_POSITIONS.items():
        fp = fps.get(ref)
        if fp is None:
            print(f"  WARN: {ref} not found")
            continue
        cur = fp.GetPosition()
        cur_x, cur_y = pcbnew.ToMM(cur.x), pcbnew.ToMM(cur.y)
        if abs(cur_x - x) < 0.05 and abs(cur_y - y) < 0.05:
            continue  # already at position
        fp.SetPosition(pcbnew.VECTOR2I(int(x*1e6), int(y*1e6)))
        moved += 1
        print(f"  {ref}: ({cur_x:.1f},{cur_y:.1f}) → ({x:.1f},{y:.1f})")
    print(f"\nMoved {moved} CH1 IC anchors into zone (0,50,35,82)")
    b.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
