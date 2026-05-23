#!/usr/bin/env python3
"""swap_b1_bom.py — PR-A4-integrate amendment 5 BOM swap.

In-place swap on existing pcbai_fpv4in1.kicad_pcb (working around broken
kinet2pcb plugin in this environment):

B-1a: Q5-Q28 channel FETs
  TO-263-3_TabPin2 (AOTL66912 10×9 drain) → W-PDFN-8-1EP_6x5 (BSC014N06NS 5×6)

B-1b: J18, J23, J28, J33 channel MCUs
  LQFP-32_7x7 (AT32F421K8T7) → QFN-32-1EP_5x5 (AT32F421K8U7)

Preserves position, rotation, layer, reference text. Net assignment is
re-applied by fix_fet_netlist_drop.py after this runs.
"""
import pcbnew
from pathlib import Path

PCB = "hardware/kicad/pcbai_fpv4in1.kicad_pcb"
FP_LIB_DFN_QFN = "/usr/share/kicad/footprints/Package_DFN_QFN.pretty"

import sys
WAVE = sys.argv[1] if len(sys.argv) > 1 else 'all'  # 'mcu', 'fet', or 'all'

SWAPS = []
if WAVE in ('fet', 'all'):
    # B-1a: Q5-Q28 → PDFN-8
    for i in range(5, 29):
        SWAPS.append((f"Q{i}", FP_LIB_DFN_QFN, "W-PDFN-8-1EP_6x5mm_P1.27mm_EP3x3mm"))
if WAVE in ('mcu', 'all'):
    # B-1b: 4 channel MCUs → QFN-32
    for r in ("J18", "J23", "J28", "J33"):
        SWAPS.append((r, FP_LIB_DFN_QFN, "QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm_ThermalVias"))


def main():
    # Approach: load fresh footprint from library inside each swap iteration
    # (avoids Duplicate() segfault). Capture old footprint state first, remove
    # old fp, then load + place new fp.
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    swap_index = {ref: (lib, lib_item) for ref, lib, lib_item in SWAPS}

    # Phase 1: read board, collect plan
    board = pcbnew.LoadBoard(PCB)
    plan = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in swap_index:
            pos = fp.GetPosition()
            plan.append({
                "ref": ref,
                "value": fp.GetValue(),
                "px": pos.x, "py": pos.y,
                "rot": fp.GetOrientationDegrees(),
                "layer": fp.GetLayer(),
                "old": fp,
                "lib": swap_index[ref][0],
                "lib_item": swap_index[ref][1],
            })
    print(f"Plan: {len(plan)} swaps", flush=True)

    # Phase 2: for each, remove old, load fresh + place
    swapped = []
    for p in plan:
        new_fp = io.FootprintLoad(p["lib"], p["lib_item"])
        if new_fp is None:
            print(f"FAIL: FootprintLoad returned None for {p['ref']}", flush=True)
            continue
        new_fp.SetReference(p["ref"])
        new_fp.SetValue(p["value"])
        new_pos = pcbnew.VECTOR2I(p["px"], p["py"])
        new_fp.SetPosition(new_pos)
        new_fp.SetOrientationDegrees(p["rot"])
        if p["layer"] != new_fp.GetLayer():
            new_fp.Flip(new_pos, False)
        board.Remove(p["old"])
        board.Add(new_fp)
        swapped.append(p["ref"])
        print(f"  swapped {p['ref']}", flush=True)

    print(f"Swapped {len(swapped)} footprints", flush=True)
    board.Save(PCB)
    print(f"Saved {PCB}", flush=True)


if __name__ == "__main__":
    main()
