#!/usr/bin/env python3
"""place_subsystem_s2_bulk.py — Phase 4-v2 Step 2 S2 bulk cap placement.

Per master 2026-05-24 preference (a). S2 zone (40,40,60,60) — 4 polymer caps
C1-C4 feeding +VMOTOR plane. Both-axis symmetric placement.

Layout: 2×2 grid centered on (50, 50), 10mm pitch:
  C1 (45, 45)  C2 (55, 45)
  C3 (45, 55)  C4 (55, 55)

Both X-axis mirror (about X=50) and Y-axis mirror (about Y=50) — pure double
symmetry per `feedback-symmetry-preserves-work` for non-channel subsystems.
"""
import sys
from pathlib import Path
import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from place_subsystem_ch1_v3 import reset_text_to_body

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

S2_ANCHORS = {
    'C1': (45.0, 45.0),
    'C2': (55.0, 45.0),
    'C3': (45.0, 55.0),
    'C4': (55.0, 55.0),
}


def main():
    board = pcbnew.LoadBoard(PCB)
    moved = 0
    for ref, (x, y) in S2_ANCHORS.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            print(f"WARN: {ref} not found")
            continue
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        # Orient: C1/C3 (west) cap pad1 east toward center; C2/C4 (east) pad1 west
        # +VMOTOR pad facing centerline for symmetric current flow
        if ref in ('C2', 'C4'):
            fp.SetOrientationDegrees(180)
        else:
            fp.SetOrientationDegrees(0)
        reset_text_to_body(fp)
        moved += 1
    print(f"S2 bulk caps placed: {moved}/{len(S2_ANCHORS)}")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
