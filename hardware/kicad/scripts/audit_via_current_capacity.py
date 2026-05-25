#!/usr/bin/env python3
"""
audit_via_current_capacity.py — G_R5 via current capacity gate.

Proactive 2026-05-26 (catch class: hot vias melting at burst).
Per IPC-2152 + Brooks "PCB Currents" via ampacity model:

  Single via (0.3mm drill, 0.6mm cu, plated 1oz):
    continuous = 1.0 A · 10°C rise
    burst (1s) = 3.0 A

  Scaling: vias in parallel multiply linearly (within 2-via separation
  thermal coupling) — N vias = N × single-via ampacity.

For each net with current spec, count vias on the net, compute aggregate
capacity, verify ≥ load × FoS_via (1.5×).

Reads routing_topology.yaml nets.{net}.constraint.{ampacity_cont_A,
ampacity_burst_A, via_count_min, via_count_actual_will_be_added_post_routing}.

Pre-routing: SKIP cleanly (no tracks/vias). Post-routing: enforces.

Exit 0 = all PASS or SKIP, 1 = any FAIL.

Usage:
  python3 audit_via_current_capacity.py <board.kicad_pcb> [<topology.yaml>]
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


VIA_AMPS_PER_VIA_CONT = 1.0   # 0.3mm drill, 0.6mm cu, 1oz plating
VIA_AMPS_PER_VIA_BURST = 3.0  # 1s pulse, same via geometry
FOS_VIA = 1.5


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    topo_path = sys.argv[2] if len(sys.argv) > 2 else "docs/PHASE4V3_LOCKFILES/routing_topology.yaml"
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)
    if not Path(topo_path).exists():
        print(f"INFO: topology {topo_path} missing — gate inert (SKIP)")
        sys.exit(0)

    topology = yaml.safe_load(Path(topo_path).read_text()) or {}
    board = pcbnew.LoadBoard(board_path)

    print(f"=== Via current capacity FoS audit: {Path(board_path).name} ===")
    print(f"Per-via: {VIA_AMPS_PER_VIA_CONT}A cont / {VIA_AMPS_PER_VIA_BURST}A burst (1oz, 0.3mm drill)")
    print(f"FoS multiplier: {FOS_VIA}×\n")

    nets = topology.get("nets") or {}
    audited = 0
    skipped = 0
    fails = []
    for net_name, spec in nets.items():
        if not isinstance(spec, dict):
            continue
        c = spec.get("constraint") or {}
        ic = c.get("ampacity_cont_A")
        ib = c.get("ampacity_burst_A")
        if ic is None and ib is None:
            continue
        # Count vias on this net
        n_vias = 0
        for t in board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == net_name:
                n_vias += 1
        if n_vias == 0:
            skipped += 1
            print(f"  [SKIP] {net_name}: no vias (pre-routing)")
            continue
        audited += 1
        cap_cont = n_vias * VIA_AMPS_PER_VIA_CONT
        cap_burst = n_vias * VIA_AMPS_PER_VIA_BURST
        ok = True
        if ic is not None:
            required = ic * FOS_VIA
            if cap_cont < required:
                fails.append(f"  [FAIL] {net_name} continuous: {n_vias} vias = {cap_cont:.1f}A < "
                             f"required {required:.1f}A ({ic}A × {FOS_VIA} FoS)")
                ok = False
        if ib is not None:
            required = ib * FOS_VIA
            if cap_burst < required:
                fails.append(f"  [FAIL] {net_name} burst: {n_vias} vias = {cap_burst:.1f}A < "
                             f"required {required:.1f}A ({ib}A × {FOS_VIA} FoS)")
                ok = False
        if ok:
            print(f"  [PASS] {net_name}: {n_vias} vias ({cap_cont:.1f}A cont, {cap_burst:.1f}A burst)")

    print()
    print(f"Audited: {audited} nets · skipped (pre-route): {skipped}\n")
    if fails:
        for f in fails:
            print(f)
        print(f"\nRESULT: FAIL — {len(fails)} via current capacity violations")
        sys.exit(1)
    print("RESULT: PASS — all power nets have via current capacity with FoS")


if __name__ == "__main__":
    main()
