#!/usr/bin/env python3
"""compute_board_invariant_hash.py — SHA256 of BOARD_INVARIANTS.md content.

Per Phase 4-v2 Step 1: any PR changing zones/I-O/highways/target.h md5
without explicit "invariant-change" PR title = REJECT.

Reads docs/BOARD_INVARIANTS.md, extracts the structured tables (zones,
I/O ports, highways, symmetry pairs, target.h md5), serializes to canonical
JSON, hashes with SHA256.

Usage:
  python3 compute_board_invariant_hash.py [--write]
"""
import hashlib
import json
import re
import sys


# DOC path: auto-locate relative to script (works in any worktree)
import os as _os
_SCRIPT_DIR = _os.path.dirname(_os.path.abspath(__file__))
DOC = _os.path.normpath(_os.path.join(_SCRIPT_DIR, "..", "..", "..", "docs", "BOARD_INVARIANTS.md"))


def parse_md_table(text, header_match):
    """Extract a markdown table whose header line matches `header_match`."""
    lines = text.splitlines()
    rows = []
    in_table = False
    for ln in lines:
        if header_match in ln:
            in_table = True
            continue
        if in_table:
            if not ln.strip() or not ln.startswith('|'):
                break
            if ln.startswith('|---'):
                continue  # separator
            cells = [c.strip() for c in ln.strip().strip('|').split('|')]
            if cells:
                rows.append(cells)
    return rows


def main():
    doc = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else DOC
    with open(doc) as f:
        text = f.read()

    # Extract structured data
    zones = parse_md_table(text, "Subsystem | x_min | y_min | x_max | y_max")
    io_ports = parse_md_table(text, "From → To | Port pos")
    highways = parse_md_table(text, "Highway | x_min | y_min | x_max | y_max")
    target_md5_m = re.search(r'target\.h md5:\s*`([a-f0-9]+)`', text)
    target_md5 = target_md5_m.group(1) if target_md5_m else ""

    # Canonical form
    canonical = {
        "outline_mm": [100, 100],
        "stackup": ["F.Cu", "In1.Cu_GND", "In2.Cu", "In3.Cu_VMOTOR",
                    "In4.Cu", "In5.Cu_GND", "In6.Cu", "B.Cu"],
        "mount_holes_M3": [[5,5],[95,5],[5,95],[95,95]],
        "symmetry_pairs": [["CH1","CH2","mirror_X_50"], ["CH3","CH4","mirror_X_50"]],
        "target_md5": target_md5,
        "zones": zones,
        "io_ports": io_ports,
        "highways": highways,
    }
    canonical_json = json.dumps(canonical, sort_keys=True, indent=2)
    h = hashlib.sha256(canonical_json.encode()).hexdigest()
    print(f"BOARD_INVARIANT_HASH = {h}")
    print(f"Canonical content:\n{canonical_json[:500]}...")

    if "--write" in sys.argv:
        # Update BOARD_INVARIANTS.md hash placeholder
        new_text = re.sub(r'BOARD_INVARIANT_HASH = .*',
                          f'BOARD_INVARIANT_HASH = {h}',
                          text)
        with open(DOC, 'w') as f:
            f.write(new_text)
        print(f"Hash written to {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
