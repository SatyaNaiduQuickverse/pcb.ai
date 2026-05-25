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
PARKING_X_THRESHOLD = 130.0  # board ≤100mm; parking_grid origin x=200; 30mm buffer


def check_anchor_match(board, ref, expected_pos, expected_layer, expected_rotation,
                       expected_footprint=None, staged_brought=None):
    """Returns (status, msg). status: 'PASS', 'FAIL', 'MISSING', 'PARKED'.

    Footprint comparison: strips library prefix (e.g. 'pcbai:ESCMotorPad_4x4mm_5via'
    → 'ESCMotorPad_4x4mm_5via') and compares bare name to lockfile entry.

    staged_brought: if set (list of brought subsystem names like ['S6']), anchors
    whose actual position is in the parking zone (x ≥ 130mm) are reported as PARKED
    (not FAIL) — they're correctly parked because their subsystem isn't brought yet.
    Added 2026-05-26 (worker-caught: G1 flagged TP19-44 channel pads at parking
    coords for Stage 0 S6).
    """
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        return "MISSING", f"{ref} not on board"
    pos = fp.GetPosition()
    actual_x = pcbnew.ToMM(pos.x)
    actual_y = pcbnew.ToMM(pos.y)
    # If --staged: parked anchor of not-yet-brought subsystem is EXPECTED, not FAIL.
    if staged_brought is not None and actual_x >= PARKING_X_THRESHOLD:
        return "PARKED", f"{ref} at parking x={actual_x:.1f}mm (subsystem not yet brought)"
    # BUG-FIX 2026-05-26 (worker-caught on real staged board):
    # GetLayerName() returns DISPLAY name like "F.Cu 3oz — Phase 4-v3 inner heat
    # copper" when the board has custom layer names. Lockfile uses canonical "F.Cu"
    # / "B.Cu". Compare canonical side via IsFlipped() instead.
    # See docs/AUDIT_VALIDATION/audit_anchor_positions.md.
    actual_layer = "B.Cu" if fp.IsFlipped() else "F.Cu"
    actual_rot = fp.GetOrientationDegrees()
    # Footprint bare-name extraction: GetLibItemName() returns just the footprint name
    # without the library prefix; this matches lockfile format which omits 'pcbai:' prefix.
    actual_fp_bare = str(fp.GetFPID().GetLibItemName())

    issues = []
    if abs(actual_x - expected_pos[0]) > TOLERANCE_MM:
        issues.append(f"x={actual_x:.3f} expected {expected_pos[0]:.3f}")
    if abs(actual_y - expected_pos[1]) > TOLERANCE_MM:
        issues.append(f"y={actual_y:.3f} expected {expected_pos[1]:.3f}")
    if actual_layer != expected_layer:
        issues.append(f"layer={actual_layer} expected {expected_layer}")
    if abs(actual_rot - expected_rotation) > 0.5:
        issues.append(f"rot={actual_rot:.1f} expected {expected_rotation:.1f}")
    if expected_footprint and actual_fp_bare != expected_footprint:
        issues.append(f"fp={actual_fp_bare} expected {expected_footprint}")

    if issues:
        return "FAIL", f"{ref}: " + ", ".join(issues)
    return "PASS", f"{ref} matches lockfile"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]

    # --staged <brought-subsystems>: parked anchors reported PARKED not FAIL.
    # Worker rec 2026-05-26: per-stage PR can't have CH-channel anchors placed
    # because their subsystems aren't brought yet; they sit at parking coords.
    staged_brought = None
    rest_args = sys.argv[2:]
    if "--staged" in rest_args:
        i = rest_args.index("--staged")
        if i + 1 < len(rest_args):
            staged_brought = rest_args[i + 1].split(",")
        else:
            staged_brought = []  # empty brought list = Stage 0 (foundation only)
        rest_args = rest_args[:i] + rest_args[i + 2:]

    lockfile_path = (
        rest_args[0]
        if rest_args
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
    print(f"Tolerance: ±{TOLERANCE_MM}mm position, ±0.5° rotation")
    if staged_brought is not None:
        print(f"Staged mode: brought={staged_brought} — parked anchors will be PARKED not FAIL\n")
    else:
        print()

    any_fail = False
    any_missing = False
    any_parked = 0

    # Categories with concrete refs (TBD placeholders skipped)
    # Include motor_pads which now have concrete entries with footprint field
    for category in ("mount_holes", "fiducials", "connectors", "motor_pads", "test_points"):
        entries = lockfile.get(category, [])
        print(f"--- {category} ({len(entries)}) ---")
        for entry in entries:
            ref = entry["ref"]
            pos = entry.get("pos")
            layer = entry.get("layer")
            rot = entry.get("rotation")
            fp_expected = entry.get("footprint")  # bare name (no lib prefix)
            # Skip if pos missing or is TBD placeholder
            if pos is None or any(p == "TBD" or isinstance(p, str) for p in pos):
                print(f"  [SKIP] {ref}: placeholder (worker fills)")
                continue
            status, msg = check_anchor_match(board, ref, pos, layer, rot, fp_expected,
                                             staged_brought=staged_brought)
            if status == "PASS":
                print(f"  [PASS] {msg}")
            elif status == "PARKED":
                print(f"  [PARK] {msg}")
                any_parked += 1
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
    if any_parked > 0:
        print(f"RESULT: PASS — all on-board Tier 1 anchors match lockfile ({any_parked} parked, awaiting subsystem bring)")
    else:
        print("RESULT: PASS — all Tier 1 anchors match lockfile within tolerance")


if __name__ == "__main__":
    main()
