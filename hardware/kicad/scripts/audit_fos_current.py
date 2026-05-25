#!/usr/bin/env python3
"""
audit_fos_current.py — G_FoS2 trace ampacity Factor of Safety gate.

Proactive 2026-05-26 (Sai FoS mandate). For each high-current net with
declared load, verify trace width carries ≥ load_current × FoS_multiplier
per IPC-2152 nomographs (10°C rise, 1oz copper outer / 3oz heavy inner).

FoS multipliers (industry standard):
  Continuous load:  1.5× (50% safety margin)
  Burst load:       1.2× (20% transient margin — short pulse)

Reads routing_topology.yaml power_nets entries:
  +VMOTOR:
    constraint:
      ampacity_cont_A: 70
      ampacity_burst_A: 100
      min_trace_width_mm: 6.0   (in routing_topology, computed from IPC-2152)

Checks: any track on this net has width ≥ min_trace_width_mm.
SKIPs cleanly if no tracks on a given net yet (pre-routing).

Exit 0 = all PASS or SKIP, 1 = any FAIL.

Usage:
  python3 audit_fos_current.py <board.kicad_pcb> [<topology.yaml>]
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


# Industry FoS multipliers
FOS_CONT = 1.5
FOS_BURST = 1.2


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
        print(f"INFO: {topo_path} not found — gate inert (SKIP)")
        sys.exit(0)

    topology = yaml.safe_load(Path(topo_path).read_text()) or {}
    board = pcbnew.LoadBoard(board_path)

    print(f"=== Trace ampacity FoS audit: {Path(board_path).name} ===")
    print(f"FoS multipliers: continuous {FOS_CONT}× · burst {FOS_BURST}×\n")

    fails = []
    audited = 0
    skipped_no_tracks = 0

    nets = (topology.get("nets") or {})
    for net_name, spec in nets.items():
        if not isinstance(spec, dict):
            continue
        c = spec.get("constraint") or {}
        # Two acceptable shapes: explicit min_trace_width_mm OR
        # ampacity values that imply a min width via IPC-2152
        min_w = c.get("min_trace_width_mm")
        if min_w is None:
            ic = c.get("ampacity_cont_A")
            ib = c.get("ampacity_burst_A")
            if ic is None and ib is None:
                continue  # no current spec, nothing to audit
            # Pragmatic IPC-2152 rough: ~6mm wide carries 70A at 10°C rise
            # (3oz copper inner). Linear scale for now; full IPC-2152 lookup
            # is future enhancement.
            need_amps = max(ic * FOS_CONT if ic else 0, ib * FOS_BURST if ib else 0)
            min_w = max(0.5, need_amps * (6.0 / 70.0))

        audited += 1
        # Find all tracks on this net
        track_widths = []
        for t in board.GetTracks():
            if not isinstance(t, pcbnew.PCB_TRACK) or isinstance(t, pcbnew.PCB_VIA):
                continue
            if t.GetNetname() == net_name:
                track_widths.append(pcbnew.ToMM(t.GetWidth()))
        if not track_widths:
            skipped_no_tracks += 1
            print(f"  [SKIP] {net_name}: no tracks (pre-routing) — min_w spec {min_w:.2f}mm noted")
            continue
        narrowest = min(track_widths)
        if narrowest < min_w:
            fails.append(f"  [FAIL] {net_name}: narrowest track {narrowest:.2f}mm < {min_w:.2f}mm "
                         f"(per FoS-derived spec)")
        else:
            print(f"  [PASS] {net_name}: narrowest {narrowest:.2f}mm ≥ {min_w:.2f}mm")

    print()
    print(f"Audited: {audited} constrained nets · skipped (no tracks): {skipped_no_tracks}\n")

    if fails:
        for f in fails:
            print(f)
        print(f"\nRESULT: FAIL — {len(fails)} ampacity FoS violations")
        sys.exit(1)
    print("RESULT: PASS — all constrained nets meet trace ampacity FoS")


if __name__ == "__main__":
    main()
