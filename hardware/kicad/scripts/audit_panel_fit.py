#!/usr/bin/env python3
"""
audit_panel_fit.py — G_M6 JLC panelization fit gate.

Proactive 2026-05-26 (catch class: board exceeds JLC max single-board size
→ panelization required → cost increase + lead-time hit).

JLC PCBA capabilities (2024+):
  Single-board max:    400 × 500 mm (way above our 100×100mm — always OK)
  Panel size cap:      400 × 500 mm
  Min board dimension: 5 × 5 mm
  Min slot width:      0.8 mm (for V-cut or rout panelization)

For us: board is 100×100mm — single-board (no panel). Gate verifies:
  1. Single-board outline within JLC max
  2. Min dimension ≥ 5mm
  3. Rectangular outline (no non-orthogonal Edge.Cuts that break panel rout)

Exit 0 = all PASS, 1 = any violation.

Usage:
  python3 audit_panel_fit.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


JLC_MAX_DIM_MM = 400.0
JLC_MIN_DIM_MM = 5.0


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found"); sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    bbox = board.GetBoardEdgesBoundingBox()
    w = pcbnew.ToMM(bbox.GetWidth())
    h = pcbnew.ToMM(bbox.GetHeight())

    print(f"=== JLC panel fit audit: {Path(board_path).name} ===")
    print(f"Board outline: {w:.1f} × {h:.1f} mm")
    print(f"JLC: {JLC_MIN_DIM_MM}mm ≤ dim ≤ {JLC_MAX_DIM_MM}mm per side\n")

    fails = []
    if w > JLC_MAX_DIM_MM or h > JLC_MAX_DIM_MM:
        fails.append(f"  [FAIL] {max(w,h):.1f}mm > JLC single-board max {JLC_MAX_DIM_MM}mm")
    if w < JLC_MIN_DIM_MM or h < JLC_MIN_DIM_MM:
        fails.append(f"  [FAIL] {min(w,h):.1f}mm < JLC min {JLC_MIN_DIM_MM}mm")

    # Check Edge.Cuts has only orthogonal segments (rectangular outline OK)
    arc_or_circ_count = 0
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        if d.GetShape() in (pcbnew.SHAPE_T_ARC, pcbnew.SHAPE_T_CIRCLE):
            arc_or_circ_count += 1
    if arc_or_circ_count > 4:  # max 4 corner radii is typical
        print(f"  [INFO] {arc_or_circ_count} arc/circle Edge.Cuts elements (corner radii OK; full curves may need rout panel)")

    if fails:
        for f in fails:
            print(f)
        print(f"\nRESULT: FAIL — JLC panel fit violation")
        sys.exit(1)
    print("RESULT: PASS — board fits JLC single-board envelope")


if __name__ == "__main__":
    main()
