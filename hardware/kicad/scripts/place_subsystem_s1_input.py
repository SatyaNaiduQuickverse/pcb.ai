#!/usr/bin/env python3
"""place_subsystem_s1_input.py — Phase 4-v2 Step 2 S1 battery input placement.

Per master 2026-05-24 R26 parallel work (S2 blocked on BOM/zone) — S1 zone
(0, 0, 100, 18) battery input + reverse-polarity protection + TVS clamps.

Components: J1 (battery header), F1 (fuse), Q1-Q4 (4× protection FETs in
parallel for 280A peak), R1/R2 (NTC), D1/D2 (TVS), D3/D4 (LED indicators).

Layout — symmetric about X=50:
  Top edge (y=2-5): LEDs D3 D4 + R1 R2 NTC
  Mid (y=7-9):      Q1 Q2 J1 Q3 Q4 — 4-FET fan + battery header
  Lower (y=11-15):  F1 + D1/D2 TVS
"""
import sys
from pathlib import Path
import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from place_subsystem_ch1_v3 import reset_text_to_body

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# S1 component positions — symmetric about X=50
ANCHORS = {
    # Battery header centered
    'J1': (50.0, 5.0),
    # 4 protection FETs symmetric pairs (Q1-Q4)
    'Q1': (25.0, 8.0),
    'Q2': (40.0, 8.0),
    'Q3': (60.0, 8.0),
    'Q4': (75.0, 8.0),
    # NTC thermistors flank FETs
    'R1': (15.0, 5.0),
    'R2': (85.0, 5.0),
    # TVS clamps centered
    'D1': (50.0, 14.0),
    'D2': (45.0, 12.0),
    # Polarity LEDs at corners
    'D3': (5.0, 5.0),
    'D4': (95.0, 5.0),
    # Fuse near battery input
    'F1': (50.0, 11.0),
}


def main():
    board = pcbnew.LoadBoard(PCB)
    moved = 0
    for ref, (x, y) in ANCHORS.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            print(f"WARN: {ref} not found")
            continue
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        reset_text_to_body(fp)
        moved += 1
    print(f"S1 components placed: {moved}/{len(ANCHORS)}")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
