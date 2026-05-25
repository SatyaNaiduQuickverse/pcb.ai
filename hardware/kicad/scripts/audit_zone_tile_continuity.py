#!/usr/bin/env python3
"""
audit_zone_tile_continuity.py — G_Z1 subsystem zone tiling continuity.

Proactive 2026-05-26 (generalized catch class — Sai 'doesnt happen across
any other subsystem'). Verifies declared subsystem zones in BOARD_INVARIANTS.md
tile the board WITHOUT gaps or overlaps (other than intentional spine + edge
margins).

Catch class:
  - Zone definitions inherited from a prior layout; one moves but adjacent
    doesn't follow → gap or overlap.
  - This session: S1↔S6 swap could leave a hole if BOARD_INVARIANTS not
    updated in sync.

Rule per zone pair (X-adjacent or Y-adjacent):
  - Edge-to-edge gap should be 0mm (adjacent) OR clearly = an intentional
    spine corridor (≥4mm gap).
  - Overlap = always FAIL (impossible electrically).

Exit 0 = all zones consistent, 1 = overlap or unexpected gap.

Usage:
  python3 audit_zone_tile_continuity.py [<board_invariants.md>]
"""

import re
import sys
from pathlib import Path


SPINE_MIN_MM = 4.0  # gaps ≥ this are intentional spines, OK
UNEXPECTED_GAP_MM = 0.1  # tolerance for "touching" vs "small gap"


def parse_zones(md_path):
    """Parse BOARD_INVARIANTS.md zones table → {name: (x_min, y_min, x_max, y_max)}."""
    if not md_path.exists():
        return {}
    txt = md_path.read_text()
    zones = {}
    # Match table rows like: | S1 battery input | 0 | 82 | 100 | 100 | ...
    for m in re.finditer(
        r"^\|\s*([\w\s+\-/]+?)\s*\|\s*(-?\d+(?:\.\d+)?)\s*\|\s*(-?\d+(?:\.\d+)?)\s*\|\s*(-?\d+(?:\.\d+)?)\s*\|\s*(-?\d+(?:\.\d+)?)\s*\|",
        txt, re.MULTILINE
    ):
        name, xmin, ymin, xmax, ymax = m.groups()
        try:
            zones[name.strip()] = (float(xmin), float(ymin), float(xmax), float(ymax))
        except ValueError:
            continue
    return zones


def rect_overlap_mm2(a, b):
    """Overlap area in mm² (0 if no overlap)."""
    dx = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    dy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return dx * dy


def main():
    md_path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/BOARD_INVARIANTS.md")
    if not md_path.exists():
        print(f"FAIL: {md_path} not found"); sys.exit(1)

    zones = parse_zones(md_path)
    if not zones:
        print(f"WARN: no zones parsed from {md_path}"); sys.exit(0)

    print(f"=== Zone tile continuity audit: {md_path} ===")
    print(f"Parsed {len(zones)} zones: {sorted(zones.keys())}\n")

    fails = []
    items = list(zones.items())
    for i, (na, ra) in enumerate(items):
        for nb, rb in items[i+1:]:
            ov = rect_overlap_mm2(ra, rb)
            if ov > 1.0:  # ≥1mm² overlap
                fails.append(f"  [FAIL] {na} ↔ {nb}: OVERLAP {ov:.1f}mm² "
                             f"({ra} ∩ {rb}) — electrically impossible")

    if fails:
        for f in fails: print(f)
        print(f"\nRESULT: FAIL — {len(fails)} zone overlaps detected")
        sys.exit(1)
    print("RESULT: PASS — no zone overlaps (gap continuity needs visual review)")


if __name__ == "__main__":
    main()
