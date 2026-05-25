#!/usr/bin/env python3
"""
audit_silk_size.py — G_PP3 silk text size readability gate.

Proactive 2026-05-26 (catch class: silk legibility for assembly + bring-up).
JLC SMT requires refdes silk text height ≥ 0.8mm to render legibly; <1.0mm
is risky on dense passive arrays. We adopt ≥ 1.0mm hard floor.

Per IPC-7351 silkscreen guidance + JLC SMT capability:
  - Min character height: 0.8mm (capability), 1.0mm (recommended)
  - Min stroke width: 0.15mm
  - Max stroke / height ratio: ~0.2 (10x readable)

Exit 0 = all PASS, 1 = any text below threshold.

Usage:
  python3 audit_silk_size.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


MIN_HEIGHT_MM = 1.0
MIN_STROKE_MM = 0.15


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)

    print(f"=== Silk text size audit: {Path(board_path).name} ===")
    print(f"Threshold: height ≥ {MIN_HEIGHT_MM}mm, stroke ≥ {MIN_STROKE_MM}mm\n")

    fails = []
    parked = 0
    visible_refs = 0
    invisible_refs = 0

    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        if pcbnew.ToMM(pos.x) >= 130:  # parked
            parked += 1
            continue
        rf = fp.Reference()
        if not rf.IsVisible():
            invisible_refs += 1
            continue
        visible_refs += 1
        sz = rf.GetTextHeight()
        sw = rf.GetTextThickness()
        h_mm = pcbnew.ToMM(sz)
        s_mm = pcbnew.ToMM(sw)
        if h_mm < MIN_HEIGHT_MM:
            fails.append(f"  [FAIL] {ref}: refdes text height {h_mm:.2f}mm < {MIN_HEIGHT_MM}mm")
        if s_mm < MIN_STROKE_MM:
            fails.append(f"  [FAIL] {ref}: refdes stroke {s_mm:.3f}mm < {MIN_STROKE_MM}mm")

    print(f"On-board refs: {visible_refs} visible, {invisible_refs} hidden, {parked} parked\n")

    if fails:
        for f in fails[:20]:
            print(f)
        if len(fails) > 20:
            print(f"  ... +{len(fails)-20} more")
        print(f"\nRESULT: FAIL — {len(fails)} silk legibility violations")
        sys.exit(1)
    print("RESULT: PASS — all visible silk meets JLC SMT readability minimum")


if __name__ == "__main__":
    main()
