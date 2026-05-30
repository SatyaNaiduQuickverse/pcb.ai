#!/usr/bin/env python3
"""audit_k3_chain_depth_compliance.py — G_K3_CHAIN_DEPTH_COMPLIANCE gate.

Per Sai 2026-05-30 Z directive: chronic-residual nets get K3 chain depth = 8
(vs default 4). This gate verifies the SoT:
  (1) K3_CHAIN_DEPTH_OVERRIDES contains the 5 chronic-residual nets.
  (2) K3_CHAIN_DEPTH_CHRONIC ≥ 6 (per Sai spec).
  (3) k3_chain_depth_for_net() returns the chronic value for each chronic
      net + default for non-chronic.
  (4) Audit log of K3 emits (if a board path given): every via-chain on a
      chronic net has chain length ≤ K3_CHAIN_DEPTH_CHRONIC (no silent
      overrun).

Exit 0 = compliant.
Exit 1 = SoT drift or chain overrun.

Usage:
    python3 audit_k3_chain_depth_compliance.py [<board.kicad_pcb>]
"""
from __future__ import annotations
import argparse
import os
import sys
from typing import List, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

try:
    import route_subsystem_cooperative as RC
except Exception as e:
    print(f"FAIL: import route_subsystem_cooperative: {e}", file=sys.stderr)
    sys.exit(2)


CHRONIC_NETS = (
    "PWM_INLA_CH1", "GLB_CH1", "KILL_RAIL_N_CH1",
    "PWM_INHB_CH1", "SWDIO_CH1",
)


def audit(board_path: str = None) -> Tuple[int, List[str]]:
    failures: List[str] = []

    # (1) chronic nets in overrides
    overrides = RC.K3_CHAIN_DEPTH_OVERRIDES
    for net in CHRONIC_NETS:
        if net not in overrides:
            failures.append(
                f"chronic net {net!r} missing from K3_CHAIN_DEPTH_OVERRIDES")
        else:
            d = overrides[net]
            if d < 6:
                failures.append(
                    f"chronic net {net!r}: depth {d} < 6 (Z spec min)")

    # (2) chronic constant ≥ 6
    if RC.K3_CHAIN_DEPTH_CHRONIC < 6:
        failures.append(
            f"K3_CHAIN_DEPTH_CHRONIC = {RC.K3_CHAIN_DEPTH_CHRONIC} < 6 "
            f"(Z spec requires ≥ 6)")

    # (3) per-net selector returns expected values
    for net in CHRONIC_NETS:
        d = RC.k3_chain_depth_for_net(net)
        if d != RC.K3_CHAIN_DEPTH_CHRONIC:
            failures.append(
                f"k3_chain_depth_for_net({net!r}) = {d}, expected "
                f"K3_CHAIN_DEPTH_CHRONIC = {RC.K3_CHAIN_DEPTH_CHRONIC}")
    # Non-chronic returns default
    for net in ("BEMF_A_CH1", "GND", "+VMOTOR"):
        d = RC.k3_chain_depth_for_net(net)
        if d != RC.K3_CHAIN_DEPTH_DEFAULT:
            failures.append(
                f"k3_chain_depth_for_net({net!r}) = {d}, expected "
                f"K3_CHAIN_DEPTH_DEFAULT = {RC.K3_CHAIN_DEPTH_DEFAULT}")

    # (4) Board-level check: K3 chain overrun (if board provided)
    overruns = []
    if board_path:
        import pcbnew
        from collections import defaultdict
        board = pcbnew.LoadBoard(board_path)
        # Group vias by net and proximity — a "chain" is a set of vias on
        # the same net within 0.5mm pitch (HDI via spacing). Count chain
        # lengths.
        vias_by_net = defaultdict(list)
        for t in board.GetTracks():
            if t.GetClass() != "PCB_VIA":
                continue
            net = t.GetNetname() or ""
            if net in CHRONIC_NETS:
                pos = t.GetPosition()
                vias_by_net[net].append((pos.x / 1e6, pos.y / 1e6))
        for net, vias in vias_by_net.items():
            # Rough chain count: all vias clustered within 1mm form a chain
            # (stacked microvias share same XY ± tolerance).
            clusters = []
            for vx, vy in vias:
                placed = False
                for cl in clusters:
                    for (cx, cy) in cl:
                        if abs(vx - cx) < 0.5 and abs(vy - cy) < 0.5:
                            cl.append((vx, vy))
                            placed = True
                            break
                    if placed:
                        break
                if not placed:
                    clusters.append([(vx, vy)])
            max_cluster = max((len(c) for c in clusters), default=0)
            if max_cluster > RC.K3_CHAIN_DEPTH_CHRONIC:
                overruns.append(
                    f"  {net}: max chain cluster size {max_cluster} > "
                    f"K3_CHAIN_DEPTH_CHRONIC ({RC.K3_CHAIN_DEPTH_CHRONIC})")
        if overruns:
            failures.extend(overruns)

    print(f"G_K3_CHAIN_DEPTH_COMPLIANCE audit:")
    print(f"  K3_CHAIN_DEPTH_DEFAULT: {RC.K3_CHAIN_DEPTH_DEFAULT}")
    print(f"  K3_CHAIN_DEPTH_CHRONIC: {RC.K3_CHAIN_DEPTH_CHRONIC}")
    print(f"  Chronic nets covered:   "
          f"{sum(1 for n in CHRONIC_NETS if n in overrides)}/{len(CHRONIC_NETS)}")
    if board_path:
        print(f"  Chain overruns on board: {len(overruns)}")
    if failures:
        print(f"\n❌ FAIL ({len(failures)} issue(s)):")
        for f in failures[:15]:
            print(f"  - {f}")
        return 1, failures
    print("\n✅ PASS — K3 chain depth compliance verified")
    return 0, []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board", nargs="?", default=None)
    args = ap.parse_args(argv)
    code, _ = audit(args.board)
    return code


if __name__ == "__main__":
    sys.exit(main())
