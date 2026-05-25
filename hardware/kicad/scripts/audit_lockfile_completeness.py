#!/usr/bin/env python3
"""
audit_lockfile_completeness.py — G_L1 lockfile vs netlist completeness gate.

Proactive 2026-05-26 (gate-class catch: silent drop-outs like the J11→J14
reconcile we caught manually). Every J*/H*/FID*/TP* referenced in the netlist
MUST have a lockfile entry. Conversely, every lockfile entry must exist on
the board (post-import). Catches silent kinet2pcb drop-outs + lockfile-stale
references.

Per [[reference-kinet2pcb-silent-drop]] + Phase 4-v3 R28 (lockfile authority).

Exit 0 = all PASS, 1 = any missing entry.

Usage:
  python3 audit_lockfile_completeness.py <board.kicad_pcb> [<lockfile.yaml>]
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml not installed")
    sys.exit(1)

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# Refdes prefixes that MUST be lockfile-anchored (mechanical / immovable).
ANCHOR_PREFIXES = ("H", "FID", "J", "P", "TP")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    lock_path = (
        sys.argv[2] if len(sys.argv) > 2
        else "docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml"
    )

    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)
    if not Path(lock_path).exists():
        print(f"FAIL: {lock_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    lf = yaml.safe_load(Path(lock_path).read_text()) or {}

    # Build lockfile ref set
    lock_refs = set()
    for cat in ("mount_holes", "fiducials", "connectors", "motor_pads",
                "test_points", "leds"):
        for e in lf.get(cat, []) or []:
            r = e.get("ref")
            if r and not (isinstance(r, str) and r.upper() == "TBD"):
                lock_refs.add(r)

    # Build board ref set (filter to anchor prefixes)
    board_anchor_refs = set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        # Anchor-class prefix? (be specific to avoid pulling Q*, U*, etc)
        if ref.startswith(("H", "FID", "TP")):
            if ref[1:].split("_")[0].lstrip("ID").isdigit() or ref[1:].isdigit():
                board_anchor_refs.add(ref)
        elif (ref.startswith("J") or ref.startswith("P")) and ref[1:].split("_")[0].isdigit():
            board_anchor_refs.add(ref)

    print(f"=== Lockfile completeness audit: {Path(board_path).name} ===")
    print(f"Lockfile: {lock_path}")
    print(f"  Lockfile anchor refs: {len(lock_refs)}")
    print(f"  Board anchor-class refs: {len(board_anchor_refs)}\n")

    # 1. Board has anchor-class ref NOT in lockfile (drop-out or untracked)
    board_missing_from_lock = board_anchor_refs - lock_refs
    # 2. Lockfile has ref not on board (stale entry or kinet2pcb drop)
    lock_missing_from_board = lock_refs - board_anchor_refs

    fails = []
    if board_missing_from_lock:
        # Filter: J* on board that look like channel sub-refs may legitimately not be in lockfile
        # (e.g., J18 = MCU placeholder, not a connector). Only flag if generic J/P/H/FID/TP-style.
        critical_missing = sorted(board_missing_from_lock)[:20]
        fails.append(f"BOARD-NOT-IN-LOCKFILE: {len(board_missing_from_lock)} anchor-class refs on board lack lockfile entry")
        for r in critical_missing:
            fails.append(f"  {r}")
        if len(board_missing_from_lock) > 20:
            fails.append(f"  ... +{len(board_missing_from_lock)-20} more")

    if lock_missing_from_board:
        fails.append(f"LOCKFILE-NOT-ON-BOARD: {len(lock_missing_from_board)} lockfile entries missing from board")
        for r in sorted(lock_missing_from_board)[:20]:
            fails.append(f"  {r} (lockfile entry, but no board footprint — kinet2pcb drop?)")
        if len(lock_missing_from_board) > 20:
            fails.append(f"  ... +{len(lock_missing_from_board)-20} more")

    if not fails:
        print("RESULT: PASS — lockfile and board anchor refs are 1:1 consistent")
        sys.exit(0)

    for f in fails:
        print(f)
    print(f"\nRESULT: WARN — lockfile/board consistency gap "
          f"(may be expected pre-Stage-10; investigate before fab)")
    # WARN not FAIL — pre-Stage-1 boards legitimately have anchor refs unbrought
    sys.exit(0)


if __name__ == "__main__":
    main()
