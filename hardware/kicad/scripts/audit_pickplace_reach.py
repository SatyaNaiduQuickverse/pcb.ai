#!/usr/bin/env python3
"""
audit_pickplace_reach.py — G_PP2 pick-and-place head reach gate.

Proactive 2026-05-26 (catch class: assembly machine can't reach pad
because neighbour tall component blocks the head's clearance angle).

JLC/standard PnP machine clearance: head needs ~5mm radial clear around
the pad it's placing, with neighbour-component height ≤3mm within that
radius (or ≤4mm if neighbour is on the OPPOSITE side of the placement
direction).

Simplified rule: for each small SMD component (R/C/L/SOIC), no tall
component (CP*, TO-220, large connector) within 3mm Euclidean.

This complements G_PP5 (which checks TP probe access) and G5 component-
inside-body (which checks geometric overlap). Together they cover the
DFM assembly + bring-up + service triangle.

Exit 0 = all PASS, 1 = any reach violation.

Usage:
  python3 audit_pickplace_reach.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


PNP_CLEAR_RADIUS_MM = 3.0
TALL_PREFIXES = ("CP",)
TALL_LIB_HINTS = ("TO-220", "TO220", "TO-263", "TO-247", "TO-252",
                  "AMASS_XT30", "SM06B-SRSS", "SM08B-SRSS", "Mounting")


def is_tall(fp):
    ref = fp.GetReference()
    if any(ref.startswith(p) for p in TALL_PREFIXES):
        return True
    lib = str(fp.GetFPID().GetLibItemName())
    if any(h in lib for h in TALL_LIB_HINTS):
        return True
    return False


def is_small_smd(fp):
    """Heuristic: R/C/L starting with R/C/L + digits, small body."""
    ref = fp.GetReference()
    if not any(ref.startswith(p) for p in ("R", "C", "L", "D", "Q", "U")):
        return False
    if not ref[1:].split("_")[0].isdigit():
        return False
    # Skip clearly tall things
    if is_tall(fp):
        return False
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    print(f"=== Pick-and-place head reach audit: {Path(board_path).name} ===")
    print(f"Rule: each small SMD has ≥{PNP_CLEAR_RADIUS_MM}mm clear of tall (≥3mm body) neighbours\n")

    smalls = []
    talls = []
    for fp in board.GetFootprints():
        pos = fp.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        if x >= 130:
            continue
        # Components on SAME side compete for head clearance
        side = "F" if fp.GetLayer() == pcbnew.F_Cu else "B"
        if is_small_smd(fp):
            smalls.append((fp.GetReference(), x, y, side))
        if is_tall(fp):
            talls.append((fp.GetReference(), x, y, side))

    print(f"On-board: {len(smalls)} small SMD, {len(talls)} tall\n")

    fails = set()
    for s_ref, sx, sy, s_side in smalls:
        for t_ref, tx, ty, t_side in talls:
            if s_ref == t_ref or s_side != t_side:
                continue
            d = ((sx - tx) ** 2 + (sy - ty) ** 2) ** 0.5
            if d < PNP_CLEAR_RADIUS_MM:
                fails.add((s_ref, t_ref, round(d, 2)))

    if fails:
        for s, t, d in sorted(fails)[:15]:
            print(f"  [FAIL] {s} too close to tall {t}: {d}mm < {PNP_CLEAR_RADIUS_MM}mm")
        if len(fails) > 15:
            print(f"  ... +{len(fails)-15} more")
        print(f"\nRESULT: FAIL — {len(fails)} pick-place clearance violations")
        sys.exit(1)
    print("RESULT: PASS — all small SMDs have PnP head clearance")


if __name__ == "__main__":
    main()
