#!/usr/bin/env python3
"""swap_one_fet.py REF — swap a single footprint to BSC014N06NS PDFN-8.

Invoked once per FET in a shell loop to avoid pcbnew Python heap issues
that segfault on bulk in-process swaps. Each invocation: fresh Python
process → load board → swap one ref → save → exit.
"""
import pcbnew
import sys

PCB = "hardware/kicad/pcbai_fpv4in1.kicad_pcb"
LIB = "/usr/share/kicad/footprints/Package_DFN_QFN.pretty"
FP_NAME = "W-PDFN-8-1EP_6x5mm_P1.27mm_EP3x3mm"

if len(sys.argv) < 2:
    raise SystemExit("usage: swap_one_fet.py REF")
ref = sys.argv[1]

io = pcbnew.PCB_IO_KICAD_SEXPR()
new_fp = io.FootprintLoad(LIB, FP_NAME)
if new_fp is None:
    raise SystemExit(f"FootprintLoad failed for {LIB}/{FP_NAME}")

board = pcbnew.LoadBoard(PCB)
target = None
already_pdfn = False
for fp in board.GetFootprints():
    if fp.GetReference() == ref:
        target = fp
        # Don't call str(fpid.GetLibItemName()) — that triggers segfault.
        # Check via pad count instead: PDFN-8 has 13 pads, TO-263 has 8.
        if len(list(fp.Pads())) == 13:
            already_pdfn = True
        break
if target is None:
    raise SystemExit(f"{ref} not found in board")
if already_pdfn:
    print(f"{ref}: already PDFN — skipping")
    sys.exit(0)

pos = target.GetPosition()
new_fp.SetReference(ref)
new_fp.SetValue(target.GetValue())
new_fp.SetPosition(pos)
new_fp.SetOrientationDegrees(target.GetOrientationDegrees())
if target.GetLayer() != new_fp.GetLayer():
    new_fp.Flip(pos, False)

board.Remove(target)
board.Add(new_fp)
board.Save(PCB)
print(f"{ref}: swapped to PDFN")
