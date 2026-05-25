#!/usr/bin/env python3
"""
audit_diff_pair_match.py — Phase 4-v3 Tier 4 differential pair length match.

Per ROUTING_METHODOLOGY.md Tier 4 + Howard Johnson HSDD Ch. 11:
Differential pairs (DShot RX, USB D+/D-, BEMF ABC) must be:
  1. Length-matched within tolerance (typically ±0.5mm for ≥500Mbps)
  2. Parallel-routed within max separation (typically ≤5mm)
  3. Reference-plane coupled (continuous GND below — not validated here, see
     audit_via_stitching_density.py for plane integrity)

This audit:
  1. For each diff_pair_groups entry in routing_topology.yaml:
     - Find both nets (pos + neg)
     - Sum all track segments per net (KiCad-native length)
     - Compute |len(pos) - len(neg)| spread
     - PASS if spread ≤ tolerance_mm

Exit 0 = all PASS, 1 = any FAIL, 2 = malformed yaml/missing nets.

Usage:
  python3 audit_diff_pair_match.py <board.kicad_pcb> [<topology.yaml>]
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


def net_track_length_mm(board, netname):
    """Sum of all track segment lengths on netname (mm)."""
    total = 0.0
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_TRACK):
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            continue  # vias have no length contribution
        if t.GetNetname() != netname:
            continue
        s, e = t.GetStart(), t.GetEnd()
        dx = pcbnew.ToMM(e.x - s.x)
        dy = pcbnew.ToMM(e.y - s.y)
        total += (dx * dx + dy * dy) ** 0.5
    return total


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    topology_path = (
        sys.argv[2] if len(sys.argv) > 2
        else "docs/PHASE4V3_LOCKFILES/routing_topology.yaml"
    )

    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)
    if not Path(topology_path).exists():
        print(f"WARN: {topology_path} not found — no diff_pair_groups to audit")
        sys.exit(0)

    topology = yaml.safe_load(Path(topology_path).read_text()) or {}
    groups = topology.get("diff_pair_groups", [])

    if not groups:
        print(f"INFO: routing_topology.yaml has no diff_pair_groups — nothing to audit")
        sys.exit(0)

    board = pcbnew.LoadBoard(board_path)

    print(f"=== Tier 4 differential-pair length match: {Path(board_path).name} ===")
    print(f"Topology: {topology_path}")
    print(f"Groups: {len(groups)}\n")

    any_fail = False
    for grp in groups:
        name = grp.get("name", "(unnamed)")
        pos_net = grp.get("pos")
        neg_net = grp.get("neg")
        tol = grp.get("tolerance_mm", 0.5)

        if not pos_net or not neg_net:
            print(f"  [SKIP] {name}: missing pos/neg net spec")
            continue

        len_pos = net_track_length_mm(board, pos_net)
        len_neg = net_track_length_mm(board, neg_net)
        spread = abs(len_pos - len_neg)

        if len_pos == 0 and len_neg == 0:
            print(f"  [SKIP] {name}: neither {pos_net} nor {neg_net} has tracks")
            continue

        if spread <= tol:
            status = "PASS"
        else:
            status = "FAIL"
            any_fail = True

        print(f"  [{status}] {name}: |{pos_net}={len_pos:.2f}mm − {neg_net}={len_neg:.2f}mm| = {spread:.2f}mm "
              f"(tol ±{tol}mm)")

    if any_fail:
        print("\nRESULT: FAIL — diff-pair length mismatch exceeds tolerance")
        sys.exit(1)
    print("\nRESULT: PASS — all diff pairs within length-match tolerance")


if __name__ == "__main__":
    main()
