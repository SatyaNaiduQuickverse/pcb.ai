#!/usr/bin/env python3
"""place_subsystem_s6_connectors.py — Phase 4-v2 Step 2 S6 placement.

Per master 2026-05-24 preference (a). S6 zone (0, 82, 100, 100) — top edge
connectors: FC header + AUX header + LED indicators + ESD.

Layout (symmetric about X=50):
  J14 FC header center (50, 92)
  J17 AUX header (70, 88) + mirror partner (30, 88) if exists
  D23/D53 LED indicators corners
"""
import sys
from pathlib import Path
import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from place_subsystem_ch1_v3 import reset_text_to_body

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

ANCHORS = {
    'J14': (50.0, 92.0),    # FC header center
    'J17': (75.0, 87.0),    # AUX header east
    'J23': (25.0, 87.0),    # secondary connector west
    'D23': (90.0, 92.0),    # LED indicator east
    'D53': (10.0, 92.0),    # LED indicator west (mirror)
    'R36': (45.0, 90.0),    # VBAT_SENSE divider
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
    print(f"S6 components placed: {moved}/{len(ANCHORS)}")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
