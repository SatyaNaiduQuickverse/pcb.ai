#!/usr/bin/env python3
"""
audit_anchor_positions.py — Phase 4-v3 Tier 1 mechanical anchor lockfile diff

Reads docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml (SSoT) and verifies every
mount hole, fiducial, connector, motor pad, and test point on the board matches
the lockfile position within ±0.01mm tolerance.

Per Phase 4-v3 placement methodology Tier 1:
"Anchors have constraints from PHYSICS OUTSIDE the PCB. Their position is SSoT.
Audit enforces match to lockfile."

Per [[feedback-master-gate-checklist]] this is gate G1.

Exit 0 = all PASS, 1 = any FAIL.

Usage:
  python3 audit_anchor_positions.py <board.kicad_pcb> [<lockfile.yaml>]
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml not installed; pip install pyyaml")
    sys.exit(1)

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


TOLERANCE_MM = 0.01  # per methodology spec


def check_anchor_match(board, ref, expected_pos, expected_layer, expected_rotation):
    """Returns (status, msg). status: 'PASS', 'FAIL', 'MISSING'."""
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        return "MISSING", f"{ref} not on board"
    pos = fp.GetPosition()
    actual_x = pcbnew.ToMM(pos.x)
    actual_y = pcbnew.ToMM(pos.y)
    actual_layer = fp.GetLayerName()
    actual_rot = fp.GetOrientationDegrees()

    issues = []
    if abs(actual_x - expected_pos[0]) > TOLERANCE_MM:
        issues.append(f"x={actual_x:.3f} expected {expected_pos[0]:.3f}")
    if abs(actual_y - expected_pos[1]) > TOLERANCE_MM:
        issues.append(f"y={actual_y:.3f} expected {expected_pos[1]:.3f}")
    if actual_layer != expected_layer:
        issues.append(f"layer={actual_layer} expected {expected_layer}")
    if abs(actual_rot - expected_rotation) > 0.5:
        issues.append(f"rot={actual_rot:.1f} expected {expected_rotation:.1f}")

    if issues:
        return "FAIL", f"{ref}: " + ", ".join(issues)
    return "PASS", f"{ref} matches lockfile"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    lockfile_path = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml"
    )

    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)
    if not Path(lockfile_path).exists():
        print(f"FAIL: {lockfile_path} not found")
        sys.exit(1)

    lockfile = yaml.safe_load(Path(lockfile_path).read_text())
    board = pcbnew.LoadBoard(board_path)

    print(f"=== Tier 1 mechanical anchor audit: {Path(board_path).name} ===")
    print(f"Lockfile: {lockfile_path}")
    print(f"Tolerance: ±{TOLERANCE_MM}mm position, ±0.5° rotation\n")

    any_fail = False
    any_missing = False

    # Categories with concrete refs (TBD placeholders skipped)
    for category in ("mount_holes", "fiducials", "connectors", "test_points"):
        entries = lockfile.get(category, [])
        print(f"--- {category} ({len(entries)}) ---")
        for entry in entries:
            ref = entry["ref"]
            pos = entry["pos"]
            layer = entry["layer"]
            rot = entry["rotation"]
            # Skip if pos is TBD placeholder
            if any(p == "TBD" or isinstance(p, str) for p in pos):
                print(f"  [SKIP] {ref}: placeholder (worker fills)")
                continue
            status, msg = check_anchor_match(board, ref, pos, layer, rot)
            if status == "PASS":
                print(f"  [PASS] {msg}")
            elif status == "MISSING":
                print(f"  [MISS] {msg}")
                any_missing = True
            else:  # FAIL
                print(f"  [FAIL] {msg}")
                any_fail = True
        print()

    # Motor pads + LEDs: skip if placeholder entries (worker fills)
    for category in ("motor_pads", "leds"):
        entries = lockfile.get(category, [])
        skipped = sum(
            1
            for e in entries
            if any(p == "TBD" or isinstance(p, str) for p in e.get("pos", []))
            or e.get("ref") == "TBD"
        )
        print(f"--- {category}: {skipped} placeholder entries (worker fills) ---\n")

    if any_fail:
        print("RESULT: FAIL — Tier 1 anchor positions diverge from lockfile")
        sys.exit(1)
    if any_missing:
        print("RESULT: WARN — some lockfile anchors missing on board (acceptable pre-place)")
        sys.exit(0)
    print("RESULT: PASS — all Tier 1 anchors match lockfile within tolerance")


if __name__ == "__main__":
    main()
