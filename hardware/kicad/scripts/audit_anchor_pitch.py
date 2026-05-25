#!/usr/bin/env python3
"""
audit_anchor_pitch.py — G_PP8 anchor pitch uniformity gate.

Proactive 2026-05-26 (Sai-eye-caught — but we should have caught it).
For each column of same-class anchors (motor pads, test points along an edge,
LED row), verify SUCCESSIVE inter-pad gaps are uniform within tolerance.

Catch class: lockfile inherits coords from a prior placement that had a
channel-divide gap (e.g. CH4-bottom to CH1-top at 4.76mm vs intra-channel
12mm). G1 verifies board matches lockfile but does NOT verify lockfile is
sensible. This gate audits the lockfile itself.

Rule: per anchor category (motor_pads, test_points, leds), group by
column (X coordinate bin ±2mm). Within each column, compute successive
y-pitch. ALL pitches must be within ±2mm of the column's median pitch.

Exit 0 = uniform, 1 = non-uniform pitch detected.

Usage:
  python3 audit_anchor_pitch.py [<lockfile.yaml>]
"""

import statistics
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml not installed"); sys.exit(1)


PITCH_TOL_MM = 2.0   # successive-pitch must be ≤ tol from median
X_COLUMN_BIN_MM = 2.0  # group anchors by X coordinate within this tolerance


def main():
    lock = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml")
    if not lock.exists():
        print(f"FAIL: {lock} not found"); sys.exit(1)

    lf = yaml.safe_load(lock.read_text()) or {}
    print(f"=== Anchor pitch uniformity audit: {lock} ===")
    print(f"Tolerance: ±{PITCH_TOL_MM}mm from median pitch within each column\n")

    fails = []
    for category in ("motor_pads", "test_points", "leds"):
        anchors = lf.get(category, []) or []
        if not anchors:
            continue
        # Group by x-column
        cols = defaultdict(list)
        for a in anchors:
            ref = a.get("ref"); pos = a.get("pos")
            if not (ref and pos and isinstance(pos, list) and len(pos) == 2):
                continue
            x, y = pos[0], pos[1]
            if isinstance(x, str) or isinstance(y, str):
                continue
            col_key = round(x / X_COLUMN_BIN_MM) * X_COLUMN_BIN_MM
            cols[col_key].append((ref, x, y))

        for col_x, members in cols.items():
            # 2026-05-26 refinement: only enforce uniform pitch for SAME-role
            # anchors within a column. Different-role TPs that coincidentally
            # share X (e.g. CH3-SWD-CLK at y25 + CH2-SWD-CLK at y75 + V5-AI
            # supply pad at y87) are independent functional anchors — uniform
            # pitch doesn't apply across role boundaries.
            # Re-bin by role within column.
            from collections import defaultdict as _dd
            by_role = _dd(list)
            for ref, x, y in members:
                # role is the 4th element (added in cols.append below)
                role = "_unknown"
                # fetch from lockfile if available
                for cat_anchors in [lf.get(category, []) or []]:
                    for a in cat_anchors:
                        if a.get("ref") == ref:
                            role = a.get("role", "_unknown")
                            break
                by_role[role].append((ref, x, y))
            for role, role_members in by_role.items():
                if len(role_members) < 3:
                    continue
                role_members.sort(key=lambda m: m[2])
                pitches = [role_members[i+1][2] - role_members[i][2] for i in range(len(role_members)-1)]
                median_pitch = statistics.median(pitches)
                for i, p in enumerate(pitches):
                    if abs(p - median_pitch) > PITCH_TOL_MM:
                        a_ref, a_x, a_y = role_members[i]
                        b_ref, b_x, b_y = role_members[i+1]
                        fails.append(f"  [FAIL] {category} role={role} column x≈{col_x:.0f}: "
                                     f"{a_ref}@y{a_y:.1f} → {b_ref}@y{b_y:.1f} pitch {p:.2f}mm "
                                     f"vs median {median_pitch:.2f}mm (Δ {abs(p-median_pitch):.2f}mm > {PITCH_TOL_MM}mm)")

    if fails:
        for f in fails: print(f)
        print(f"\nRESULT: FAIL — {len(fails)} non-uniform anchor pitches "
              f"(adjacent-class anchors should be evenly spaced; tight gap = solder bridge / strain relief risk)")
        sys.exit(1)
    print("RESULT: PASS — all anchor columns have uniform inter-pad pitch")


if __name__ == "__main__":
    main()
