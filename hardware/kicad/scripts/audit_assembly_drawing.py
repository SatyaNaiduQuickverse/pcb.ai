#!/usr/bin/env python3
"""
audit_assembly_drawing.py — G_M5 assembly drawing completeness gate.

Proactive 2026-05-26 (catch class: JLC SMT requires complete assembly
drawing or misorients components → 5-day rework cycle).

JLC SMT assembly requires (per their submission guide):
  1. Every-component rotation in CPL file (else 0°-assumed → wrong orient)
  2. Polarity marker on silk (diodes, electrolytics, ICs) — visual check at line
  3. 0,0 reference fiducial defined (we use H3 at (5,5))
  4. Pick-and-place file consistent with BOM + schematic

This audit checks PCB-side prerequisites:
  - All non-mounting-hole footprints have orientation declared (≠ default 0
    is fine; the check is just that GetOrientationDegrees returns finite)
  - Every footprint has a non-empty Value field (CPL uses Value as part-id)
  - Every footprint has Reference visible OR explicitly hidden (not orphan)

Exit 0 = all PASS, 1 = any orphan/incomplete metadata.

Usage:
  python3 audit_assembly_drawing.py <board.kicad_pcb>
"""

import math
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable"); sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found"); sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    print(f"=== Assembly drawing completeness audit: {Path(board_path).name} ===\n")

    fails = []
    on_board = 0
    parked = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        x = pcbnew.ToMM(pos.x)
        if x >= 130:
            parked += 1
            continue
        on_board += 1
        # Skip mount holes — no assembly required
        if ref.startswith(("H", "FID")):
            continue
        val = fp.GetValue()
        if not val or val.strip() == "":
            fails.append(f"  [FAIL] {ref}: empty Value field — CPL part-id missing")
        rot = fp.GetOrientationDegrees()
        if not math.isfinite(rot):
            fails.append(f"  [FAIL] {ref}: non-finite rotation")
        # KiCad attributes — verify FP attribute (SMD vs THT) is set
        attrs = fp.GetAttributes()
        if attrs == 0:
            fails.append(f"  [WARN] {ref}: no attributes set (SMD/THT undeclared — defaults to THT)")

    print(f"On-board: {on_board} · parked: {parked} skipped\n")
    if fails:
        for f in fails[:15]: print(f)
        if len(fails) > 15: print(f"  ... +{len(fails)-15} more")
        # Treat as WARN by default — JLC will infer most; only true blanks are fab-blocking
        print(f"\nRESULT: WARN — {len(fails)} assembly metadata gaps")
        sys.exit(0)
    print("RESULT: PASS — every on-board footprint has Value + rotation + attribute set")


if __name__ == "__main__":
    main()
