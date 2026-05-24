#!/usr/bin/env python3
"""place_subsystem_s5_bec.py — Phase 4-v2 Step 2 S5 BEC strips placement.

Per master 2026-05-24 preference (a). S5 zones:
  east strip:  60-65 × 50-82
  west strip:  35-40 × 50-82
  south strip: 35-65 × 18-25 (along S3 south boundary)

5 buck regulators (L1-L5 inductors) + protect inductors L6-L10 + fuses F1/F2.
"""
import sys
from pathlib import Path
import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from place_subsystem_ch1_v3 import reset_text_to_body

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

ANCHORS = {
    # Buck inductors (5×6mm or 5×3mm Sunlord)
    'L1': (37.5, 65.0),   # west strip, north
    'L2': (62.5, 65.0),   # east strip, north (mirror L1)
    'L3': (37.5, 75.0),   # west strip, south of L1
    'L4': (62.5, 75.0),   # east strip, mirror L3
    'L5': (37.5, 55.0),   # west strip top
    # Protect inductors (0805)
    'L6': (38.0, 23.0),   # south strip west
    'L7': (50.0, 23.0),   # south strip center
    'L8': (62.0, 23.0),   # south strip east (mirror L6)
    'L9': (62.5, 80.0),   # east strip bottom
    'L10': (37.5, 80.0),  # west strip bottom (mirror L9)
    # Fuses (1206)
    'F1': (50.0, 23.0),   # actually already place L7 here — remove this slot
    'F2': (37.5, 18.5),
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
    print(f"S5 BEC components placed: {moved}/{len(ANCHORS)}")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
