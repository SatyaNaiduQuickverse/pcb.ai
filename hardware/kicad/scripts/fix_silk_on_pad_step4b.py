#!/usr/bin/env python3
"""fix_silk_on_pad_step4b.py — Sai-catch #12 Step 4b v3 (master 2026-05-24).

Move U3/J13 refdes silk text to pad-clear positions (preserves critical-class
silk visibility per master Q1). Hide FID3 silk (fiducial — geometry-only).
Relocate C115 to pad-clear position outside D41 silk.

Positions chosen via pad-collision search:
  - U3 silk text → (48.5, 87.5) — north-east of U3 body, no pad overlap
  - J13 silk text → (44.0, 76.0) — west of J13 body, no pad overlap
  - FID3 silk → invisible
  - C115 → (82.5, 48.0) — south of D41/D54, no pad/body overlap
"""
import pcbnew


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"


def main():
    board = pcbnew.LoadBoard(PCB)
    fps = {f.GetReference(): f for f in board.GetFootprints()}

    # U3 refdes text
    fps['U3'].Reference().SetPosition(
        pcbnew.VECTOR2I(int(48.5 * 1e6), int(87.5 * 1e6)))
    print(f"  U3 refdes silk → (48.5, 87.5)")

    # J13 refdes text
    fps['J13'].Reference().SetPosition(
        pcbnew.VECTOR2I(int(44.0 * 1e6), int(76.0 * 1e6)))
    print(f"  J13 refdes silk → (44.0, 76.0)")

    # FID3 — hide
    fps['FID3'].Reference().SetVisible(False)
    print(f"  FID3 refdes silk → HIDDEN")

    # C115 — move out of D41 silk bbox
    fps['C115'].SetPosition(
        pcbnew.VECTOR2I(int(82.5 * 1e6), int(48.0 * 1e6)))
    print(f"  C115 → (82.5, 48.0)")

    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
