#!/usr/bin/env python3
"""flip_bcu_footprints.py — post-place_board pass that properly flips footprints
whose dict layer is 'B.Cu' but whose physical pads remained on F.Cu.

Bug in place_board.py: it text-edits (layer "F.Cu") → (layer "B.Cu") in the
footprint block but doesn't touch the pad-level (layer "F.Cu") inside each
(pad ...) sub-block. KiCad treats footprint.layer as the "side" indicator;
the pads need flipping via pcbnew Footprint.Flip() to actually move copper
from F.Cu to B.Cu.

This script:
  1. Loads the board (post place_board run)
  2. For each footprint, if its declared layer is B.Cu but its first pad is
     still on F.Cu only → call Footprint.Flip() to fix
  3. Saves the board
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"


def main():
    board = pcbnew.LoadBoard(PCB)
    flipped = 0
    for fp in board.GetFootprints():
        if fp.GetLayer() != pcbnew.B_Cu:
            continue
        # Check first pad's layer set
        first_pad = None
        for p in fp.Pads():
            if p.GetNumber():
                first_pad = p
                break
        if first_pad is None:
            continue
        ls = first_pad.GetLayerSet()
        if ls.Contains(pcbnew.F_Cu) and not ls.Contains(pcbnew.B_Cu):
            # Flip this footprint
            pos = fp.GetPosition()
            fp.Flip(pos, False)
            flipped += 1
    print(f"Flipped {flipped} footprints to B.Cu (pads + graphics)")
    board.Save(PCB)
    print(f"Saved {PCB}")


if __name__ == "__main__":
    main()
