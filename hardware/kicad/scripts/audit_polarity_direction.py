#!/usr/bin/env python3
"""
audit_polarity_direction.py — G_PP9 polarity-marker orientation consistency.

Proactive 2026-05-26 (generalized uniformity catch class). Same-class
polarized components (diodes, LEDs, electrolytic caps) in a row/column or
subsystem cluster MUST face the same direction (rotation modulo 180°) so
the eye can read polarity at-a-glance during assembly inspection.

Catch class:
  - 4 LEDs in a row but one is flipped — easy hand-solder mistake at line
  - 2 diodes in same protection cluster flipped opposite — debug confusion
  - Adjacent caps with electrolytic + opposite orientation → polarity misread

Rule: within each subsystem zone, group D[digit] / CP[digit] components
by footprint family (lib:fp_name). Within each (subsystem × fp_family)
group, all rotations should be 0° or 180° (Y-axis flip = same direction)
OR all 90° / 270° (X-axis flip). Mixed = FAIL.

(Allows full footprint rotation flexibility but enforces consistency
within a group.)

Exit 0 = consistent, 1 = mixed orientation in any group.

Usage:
  python3 audit_polarity_direction.py <board.kicad_pcb>
"""

import sys
from collections import defaultdict
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable"); sys.exit(1)


def axis_of_rotation(deg):
    """Map rotation to axis: Y-axis (0/180) or X-axis (90/270)."""
    r = round(deg / 90) * 90 % 360
    if r in (0, 180):
        return "Y"
    return "X"


def is_polarized(ref):
    if ref.startswith("CP") and ref[2:].split("_")[0].isdigit():
        return True
    if ref.startswith("D") and ref[1:].split("_")[0].isdigit():
        return True
    return False


def subsystem_of(x, y):
    if x < 50 and y < 50: return "NW"
    if x >= 50 and y < 50: return "NE"
    if x >= 50 and y >= 50: return "SE"
    return "SW"


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found"); sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    print(f"=== Polarity-marker direction consistency audit: {Path(board_path).name} ===")
    print(f"Rule: same-fp-class polarized components within a subsystem share rotation axis\n")

    groups = defaultdict(lambda: defaultdict(list))  # (sub, fp_name) → {axis: refs}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not is_polarized(ref):
            continue
        pos = fp.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        if x >= 130:
            continue
        sub = subsystem_of(x, y)
        fp_name = str(fp.GetFPID().GetLibItemName())
        axis = axis_of_rotation(fp.GetOrientationDegrees())
        groups[(sub, fp_name)][axis].append(ref)

    fails = []
    for (sub, fp_name), axis_map in groups.items():
        if len(axis_map) > 1 and sum(len(v) for v in axis_map.values()) > 1:
            details = ", ".join(f"{a}-axis:{len(refs)}" for a, refs in axis_map.items())
            sample = []
            for refs in axis_map.values():
                sample.extend(refs[:2])
            fails.append(f"  [FAIL] {sub} {fp_name}: mixed axes {details}  refs: {sample[:4]}")

    if fails:
        for f in fails[:15]: print(f)
        if len(fails) > 15: print(f"  ... +{len(fails)-15} more")
        print(f"\nRESULT: FAIL — {len(fails)} mixed-orientation polarity groups (assembly mis-install risk)")
        sys.exit(1)
    print("RESULT: PASS — all polarized component groups share rotation axis")


if __name__ == "__main__":
    main()
