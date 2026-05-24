#!/usr/bin/env python3
"""place_subsystem_s3_supervisor.py — Phase 4-v2 Step 2 S3 placement.

Per master 2026-05-24 preference (a). S3 zone (40, 18, 60, 40) — supervisor
+ Hall current sense + dividers. Central spine 20×22mm.

Layout:
  U1 (ACS770/CB_PFF Hall sensor): center (50, 28) — current path through
  U2 (TPS3700 supervisor): (50, 22) above Hall
  R7-R12 dividers: arrayed around U2
"""
import sys
from pathlib import Path
import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from place_subsystem_ch1_v3 import reset_text_to_body

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

ANCHORS = {
    'U1':  (50.0, 30.0),  # Hall sensor center
    'U2':  (50.0, 22.0),  # supervisor north
    'R7':  (45.0, 22.0),  # divider west
    'R8':  (55.0, 22.0),  # divider east
    'R9':  (45.0, 25.0),
    'R10': (55.0, 25.0),
    'R11': (45.0, 37.0),  # below Hall
    'R12': (55.0, 37.0),
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
    print(f"S3 components placed: {moved}/{len(ANCHORS)}")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
