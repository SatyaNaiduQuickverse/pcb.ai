#!/usr/bin/env python3
"""
audit_via_stitching_density.py — Phase 4-v3 Tier 1 PDN via stitching audit

Per ROUTING_METHODOLOGY.md Tier 1 + routing_topology.yaml +VMOTOR entry:
"ampacity 280A burst per IPC-2152, via_stitching_density_per_cm2: 4"

Per Erickson Ch. 17 (multi-layer power planes) + IPC-2152 nomographs:
At 280A burst through In3.Cu 3oz +VMOTOR plane, current must spread from
HS-FET drain pads (concentrated) into the plane (distributed). Via density
determines how quickly current can disperse without copper hotspot.

This audit:
  1. For each power net in routing_topology.yaml with via_stitching_density_per_cm2 spec:
     - Count vias on that net within board outline
     - Compute board area in cm²
     - Verify density ≥ spec

Exit 0 = all PASS, 1 = any FAIL.

Usage:
  python3 audit_via_stitching_density.py <board.kicad_pcb>
"""

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


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TOPOLOGY_PATH = REPO_ROOT / "docs" / "PHASE4V3_LOCKFILES" / "routing_topology.yaml"


def get_board_area_cm2(board):
    """Return board area in cm². Uses bounding-box approximation."""
    bbox = board.GetBoardEdgesBoundingBox()
    w_mm = pcbnew.ToMM(bbox.GetWidth())
    h_mm = pcbnew.ToMM(bbox.GetHeight())
    return (w_mm * h_mm) / 100.0  # mm² → cm²


def count_vias_on_net(board, net_name):
    """Count vias whose netname matches."""
    net = board.FindNet(net_name)
    if net is None:
        return 0
    n = 0
    for via in board.GetTracks():
        if isinstance(via, pcbnew.PCB_VIA) and via.GetNetname() == net_name:
            n += 1
    return n


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
    area_cm2 = get_board_area_cm2(board)

    print(f"=== Via stitching density audit: {board_path.name} ===")
    print(f"Board area: {area_cm2:.2f} cm²\n")

    fails = []
    passes = 0
    skipped = 0

    for net_name, spec in (topology.get("nets") or {}).items():
        if spec is None:
            continue
        constraint = spec.get("constraint") or {}
        target_density = constraint.get("via_stitching_density_per_cm2")
        if target_density is None:
            continue  # only nets with a density spec are audited

        via_count = count_vias_on_net(board, net_name)
        actual_density = via_count / area_cm2 if area_cm2 > 0 else 0.0

        if actual_density >= target_density:
            print(
                f"  [PASS] {net_name}: {via_count} vias / {area_cm2:.1f}cm² = "
                f"{actual_density:.2f}/cm² ≥ target {target_density}/cm²"
            )
            passes += 1
        else:
            msg = (
                f"{net_name}: {via_count} vias / {area_cm2:.1f}cm² = "
                f"{actual_density:.2f}/cm² < target {target_density}/cm² "
                f"(short by {target_density-actual_density:.2f}/cm²)"
            )
            print(f"  [FAIL] {msg}")
            fails.append(msg)

    nets_with_spec = passes + len(fails)
    if nets_with_spec == 0:
        print("(no nets in routing_topology.yaml have via_stitching_density_per_cm2 spec)")
        print("\nRESULT: SKIP — no constrained nets defined")
        sys.exit(0)

    print(f"\nPASS: {passes}  FAIL: {len(fails)}")
    if fails:
        print("\nRESULT: FAIL — power planes lack sufficient via stitching for ampacity")
        sys.exit(1)
    print("\nRESULT: PASS — all power nets meet stitching density target")


if __name__ == "__main__":
    main()
