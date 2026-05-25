#!/usr/bin/env python3
"""
audit_rotation_alignment.py — G_PP4 component rotation alignment gate.

Proactive 2026-05-26 (catch class: DFM uniformity for pick-and-place).
Same-class components (same footprint family) within a subsystem zone
should share rotation orientation (0/90/180/270°) for:

  1. Pick-and-place head efficiency (no re-orient between picks)
  2. Visual inspection / debugging (aligned silk easier to read)
  3. Thermal uniformity (same orientation = same heat-flow geometry)

Rule: within each subsystem zone, group footprints by lib:fp_name. Per
group, count distinct rotations. >1 distinct rotation (excluding 0/180 or
90/270 pairs which are interchangeable for symmetric parts) = FAIL.

Special exemption: passives (R/C/L) on either 0/90 (E-W or N-S) are
universal — only flag if a same-class group has BOTH orientations within
the same subsystem (visual chaos).

Exit 0 = all PASS, 1 = any mixed-rotation group.

Usage:
  python3 audit_rotation_alignment.py <board.kicad_pcb>
"""

import sys
from collections import defaultdict
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


def normalize_rot(deg):
    """Map 0/180 → 0; 90/270 → 90 (symmetric passive equivalence)."""
    r = round(deg / 90) * 90 % 360
    if r >= 180:
        r -= 180
    return r


def subsystem_of(x, y):
    """Quick zone-of: NW=CH1, NE=CH2, SE=CH3, SW=CH4, center=S0/spine."""
    if x < 50 and y < 50: return "CH1"
    if x >= 50 and y < 50: return "CH2"
    if x >= 50 and y >= 50: return "CH3"
    if x < 50 and y >= 50: return "CH4"
    return "S0"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)

    # Group: (subsystem, fp_name) → set of rotations
    groups = defaultdict(lambda: defaultdict(list))
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        if x >= 130:  # parked
            continue
        fp_name = str(fp.GetFPID().GetLibItemName())
        sub = subsystem_of(x, y)
        rot = normalize_rot(fp.GetOrientationDegrees())
        groups[(sub, fp_name)][rot].append(ref)

    print(f"=== Rotation alignment audit: {Path(board_path).name} ===")
    print(f"Rule: within (subsystem × footprint-class), all components share normalized rotation (0/90)\n")

    fails = []
    for (sub, fp_name), rot_map in groups.items():
        if len(rot_map) > 1 and sum(len(v) for v in rot_map.values()) > 1:
            rots = sorted(rot_map.keys())
            counts = ", ".join(f"{r}°={len(rot_map[r])}" for r in rots)
            sample_refs = []
            for r in rots:
                sample_refs.extend(rot_map[r][:2])
            fails.append(f"  [FAIL] {sub} {fp_name}: mixed rotations {counts}  refs: {sample_refs[:6]}")

    if fails:
        for f in fails[:15]:
            print(f)
        if len(fails) > 15:
            print(f"  ... +{len(fails)-15} more")
        print(f"\nRESULT: FAIL — {len(fails)} mixed-rotation same-class groups")
        sys.exit(1)
    print("RESULT: PASS — all same-class groups share rotation within subsystem")


if __name__ == "__main__":
    main()
