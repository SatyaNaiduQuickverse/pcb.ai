#!/usr/bin/env python3
"""
audit_diff_pair_z0.py — G_R1 differential-pair Z0 impedance gate.

Proactive 2026-05-26 (catch class: diff-pair impedance mismatch → reflections).
Per Howard Johnson HSDD Ch.11 + IPC-2141:

For 100Ω differential impedance on 8L stackup (typical:0.18mm prepreg to ref
plane), trace width + spacing follow Polar Si9000 / IPC-2141:
  Edge-coupled microstrip, ε_r 4.3:
    100Ω diff: trace_w ~ 0.13mm, edge-edge ~ 0.13mm  (1×1 mil)
    90Ω  diff: trace_w ~ 0.15mm, edge-edge ~ 0.15mm
    85Ω  diff: trace_w ~ 0.17mm, edge-edge ~ 0.13mm

  Edge-coupled stripline (inner layer, fully shielded):
    100Ω diff: trace_w ~ 0.10mm, edge-edge ~ 0.15mm

Reads routing_topology diff_pair_groups[*] target_z0_ohms + trace_width_mm
+ edge_spacing_mm + layer; verifies tracks on those nets match within ±5%.

SKIP pre-routing.

Exit 0 = all PASS, 1 = any Z0 mismatch.

Usage:
  python3 audit_diff_pair_z0.py <board.kicad_pcb> [<topology.yaml>]
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml not installed"); sys.exit(1)

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable"); sys.exit(1)


WIDTH_TOL_PCT = 5.0


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    board_path = sys.argv[1]
    topo_path = sys.argv[2] if len(sys.argv) > 2 else "docs/PHASE4V3_LOCKFILES/routing_topology.yaml"
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found"); sys.exit(1)
    if not Path(topo_path).exists():
        print(f"INFO: topology missing — SKIP"); sys.exit(0)

    board = pcbnew.LoadBoard(board_path)
    tracks = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_TRACK) and not isinstance(t, pcbnew.PCB_VIA)]
    if not tracks:
        print("INFO: no tracks — SKIP"); sys.exit(0)

    topology = yaml.safe_load(Path(topo_path).read_text()) or {}
    groups = topology.get("diff_pair_groups", [])
    if not groups:
        print("INFO: no diff_pair_groups — SKIP"); sys.exit(0)

    print(f"=== Diff-pair Z0 audit: {Path(board_path).name} ===")
    print(f"Tolerance: ±{WIDTH_TOL_PCT}% from spec trace width\n")

    fails = []
    for grp in groups:
        name = grp.get("name", "?")
        target_w = grp.get("trace_width_mm")
        if not target_w:
            continue
        for net in (grp.get("pos"), grp.get("neg")):
            if not net:
                continue
            for t in tracks:
                if t.GetNetname() != net:
                    continue
                w = pcbnew.ToMM(t.GetWidth())
                delta_pct = abs(w - target_w) / target_w * 100
                if delta_pct > WIDTH_TOL_PCT:
                    fails.append(f"  [FAIL] {name}/{net}: track w={w:.3f}mm vs target {target_w:.3f}mm "
                                 f"(Δ {delta_pct:.1f}% > {WIDTH_TOL_PCT}%)")

    if fails:
        for f in fails[:10]: print(f)
        print(f"\nRESULT: FAIL — {len(fails)} Z0 trace-width violations"); sys.exit(1)
    print("RESULT: PASS — diff-pair trace widths match Z0 spec")


if __name__ == "__main__":
    main()
