#!/usr/bin/env python3
"""
audit_length_match.py — Phase 4-v3 Tier 5 signal highway length-match audit

Per ROUTING_METHODOLOGY.md Tier 5 + routing_topology.yaml signal-highway
class entries with length_match_group + length_match_tolerance_mm.

Per Howard Johnson HSDD Ch. 4 (matched-delay routing): for clock-like signals
across multiple instances (per-channel DShot/TLM in our case), trace lengths
must match within tolerance to keep skew below propagation budget.

This audit:
  1. For each net in routing_topology.yaml with length_match_group:
     - Sum all track segments on the net (per-net total length)
  2. For each length_match_group:
     - Compute spread = max(len) - min(len)
     - Verify spread ≤ length_match_tolerance_mm

Exit 0 = all groups PASS, 1 = any group FAIL.

Usage:
  python3 audit_length_match.py <board.kicad_pcb>
"""

import sys
from collections import defaultdict
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


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TOPOLOGY_PATH = REPO_ROOT / "docs" / "PHASE4V3_LOCKFILES" / "routing_topology.yaml"


def net_total_length_mm(board, net_name):
    """Sum length of all track segments on this net (excludes via Z-traversal)."""
    total = 0.0
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_TRACK):
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetNetname() != net_name:
            continue
        # GetLength returns nm
        total += pcbnew.ToMM(t.GetLength())
    return total


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = Path(sys.argv[1])
    if not board_path.exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)
    if not TOPOLOGY_PATH.exists():
        print(f"FAIL: {TOPOLOGY_PATH} not found")
        sys.exit(1)

    topology = yaml.safe_load(TOPOLOGY_PATH.read_text())
    board = pcbnew.LoadBoard(str(board_path))

    print(f"=== Length-match audit: {board_path.name} ===\n")

    # Group nets by length_match_group
    groups = defaultdict(list)
    tolerances = {}
    for net_name, spec in (topology.get("nets") or {}).items():
        if spec is None:
            continue
        group = spec.get("length_match_group")
        if group is None:
            continue
        tol = spec.get("length_match_tolerance_mm", 2.0)
        groups[group].append(net_name)
        tolerances[group] = tol

    if not groups:
        print("(no nets in routing_topology.yaml have length_match_group)")
        print("RESULT: SKIP — no length-matched groups defined")
        sys.exit(0)

    fails = []
    passes = 0

    for group, net_names in groups.items():
        tol = tolerances[group]
        lengths = {}
        for net in net_names:
            lengths[net] = net_total_length_mm(board, net)
        # Only include nets with non-zero length (routed)
        routed = {n: l for n, l in lengths.items() if l > 0.0}
        if len(routed) < 2:
            print(f"  [SKIP] group '{group}': only {len(routed)} nets routed (need ≥2 to compare)")
            continue
        min_len = min(routed.values())
        max_len = max(routed.values())
        spread = max_len - min_len

        if spread <= tol:
            print(
                f"  [PASS] group '{group}' (tol ±{tol}mm): spread {spread:.2f}mm; "
                f"lengths {[f'{n}={l:.1f}' for n, l in routed.items()]}"
            )
            passes += 1
        else:
            msg = (
                f"group '{group}' (tol ±{tol}mm): spread {spread:.2f}mm EXCEEDS; "
                f"lengths {[f'{n}={l:.1f}' for n, l in routed.items()]}"
            )
            print(f"  [FAIL] {msg}")
            fails.append(msg)

    print(f"\nPASS: {passes}  FAIL: {len(fails)}")
    if fails:
        print("\nRESULT: FAIL — length-matched groups exceed tolerance")
        sys.exit(1)
    print("\nRESULT: PASS — all length-matched groups within tolerance")


if __name__ == "__main__":
    main()
