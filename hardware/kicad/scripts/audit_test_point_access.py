#!/usr/bin/env python3
"""
audit_test_point_access.py — G_PP5 hand-solder / probe access for TPs.

Proactive 2026-05-26 (catch class: TPs blocked by tall neighbour components,
unusable for bring-up scoping).

Per Sai-#TPs spacing rule + industry probe-tip clearance: every TP must
have ≥3mm vertical clearance from neighbour components (no ≥3mm-tall
component within 4mm radius blocking probe approach).

Component height heuristic (no 3D database here — use refdes prefix proxy):
  - Tall (≥3mm body): TO-220 (Q[digit] in TO220 lib), capacitors CP* (8mm
    polymer/electrolytic), large connectors J*
  - Short (<3mm): R/C/L SMD passives, SOIC ICs, USBLC6 ESD arrays

Rule: each TP center must have no tall component within 4mm radius.

Exit 0 = all PASS, 1 = any TP blocked.

Usage:
  python3 audit_test_point_access.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


PROBE_CLEAR_RADIUS_MM = 4.0
TALL_PREFIXES = ("CP",)  # bulk caps definitely tall
TALL_LIB_HINTS = ("TO-220", "TO220", "TO-263", "SOT-223", "TO-247",
                  "ESCMotorPad", "AMASS_XT30", "Mounting")


def is_tall(fp):
    ref = fp.GetReference()
    if any(ref.startswith(p) for p in TALL_PREFIXES):
        return True
    lib = str(fp.GetFPID().GetLibItemName())
    if any(h in lib for h in TALL_LIB_HINTS):
        return True
    return False


def is_test_point(fp):
    ref = fp.GetReference()
    return ref.startswith("TP") and ref[2:].split("_")[0].isdigit()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    print(f"=== Test point probe-access audit: {Path(board_path).name} ===")
    print(f"Rule: no tall component (CP* / TO-220 / connector) within "
          f"{PROBE_CLEAR_RADIUS_MM}mm of any TP\n")

    tps = []
    talls = []
    for fp in board.GetFootprints():
        pos = fp.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        if x >= 130:
            continue
        if is_test_point(fp):
            tps.append((fp.GetReference(), x, y))
        if is_tall(fp):
            talls.append((fp.GetReference(), x, y))

    print(f"On-board: {len(tps)} TPs, {len(talls)} tall components\n")

    fails = []
    for tp_ref, tx, ty in tps:
        for tall_ref, gx, gy in talls:
            if tp_ref == tall_ref:
                continue
            d = ((tx - gx) ** 2 + (ty - gy) ** 2) ** 0.5
            if d < PROBE_CLEAR_RADIUS_MM:
                fails.append(f"  [FAIL] {tp_ref}@({tx:.1f},{ty:.1f}) blocked by tall {tall_ref}@({gx:.1f},{gy:.1f}) at {d:.2f}mm")

    if fails:
        for f in fails[:15]:
            print(f)
        if len(fails) > 15:
            print(f"  ... +{len(fails)-15} more")
        print(f"\nRESULT: FAIL — {len(fails)} TPs blocked by tall neighbour")
        sys.exit(1)
    print("RESULT: PASS — all TPs have probe access clearance")


if __name__ == "__main__":
    main()
