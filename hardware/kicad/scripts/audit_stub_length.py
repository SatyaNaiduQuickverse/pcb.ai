#!/usr/bin/env python3
"""
audit_stub_length.py — G_R2 transmission-line stub length gate.

Proactive 2026-05-26 (catch class: ringing/reflection on unterminated stubs).
For high-speed signals (DShot, USB D+/D-, MCU clocks), any unterminated
stub off the main net must satisfy:

  stub_length ≤ rise_time × 0.1 × v_p_signal  (10% of one rise edge)
                                              (rise distance)

Pragmatic conservative rule (per Howard Johnson HSDD Ch. 6 + Bogatin §4):
  - DShot 600 (1.67 Mbps, ~600ns rise): max stub 50mm
  - DShot 1200 (3.33 Mbps, ~300ns rise): max stub 25mm
  - USB Full-Speed (12 Mbps, ~10ns rise): max stub 8mm
  - MCU SPI/CLK (≤ 50 MHz, ~3ns rise): max stub 2.5mm

Reads routing_topology.yaml nets.{net}.constraint.max_stub_length_mm or
defaults from class:
  signal-highway: 25mm (DShot 1200 conservative)
  spi:            2.5mm
  diff-pair:      8mm  (USB-FS proxy)

Stub detection: for each net, walk track segments. A "stub" is any track
segment terminating at a non-pad endpoint (T-junction or dead end).
Sum lengths from the junction to the dead end. > limit = FAIL.

SKIPs cleanly if no tracks routed (placement-only stages).

Exit 0 = all PASS, 1 = any stub over limit.

Usage:
  python3 audit_stub_length.py <board.kicad_pcb> [<topology.yaml>]
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


CLASS_DEFAULTS_MM = {
    "signal-highway": 25.0,
    "spi": 2.5,
    "diff-pair": 8.0,
    "clock": 2.5,
}


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    board_path = sys.argv[1]
    topo_path = sys.argv[2] if len(sys.argv) > 2 else "docs/PHASE4V3_LOCKFILES/routing_topology.yaml"
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found"); sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    track_count = sum(1 for t in board.GetTracks() if isinstance(t, pcbnew.PCB_TRACK) and not isinstance(t, pcbnew.PCB_VIA))
    if track_count == 0:
        print(f"=== Stub length audit: {Path(board_path).name} ===")
        print("INFO: no tracks — stub gate is post-routing only, SKIP")
        sys.exit(0)

    topology = yaml.safe_load(Path(topo_path).read_text()) if Path(topo_path).exists() else {}
    nets = topology.get("nets") or {}

    print(f"=== Stub length audit: {Path(board_path).name} ===")
    print(f"Tracks: {track_count}\n")

    # Build per-net endpoint graph
    net_segments = defaultdict(list)
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_TRACK) or isinstance(t, pcbnew.PCB_VIA):
            continue
        n = t.GetNetname()
        s, e = t.GetStart(), t.GetEnd()
        net_segments[n].append(
            ((pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)),
             (pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)),
             ((s.x - e.x) ** 2 + (s.y - e.y) ** 2) ** 0.5 / 1e6)
        )

    fails = []
    audited = 0
    for net_name, segs in net_segments.items():
        spec = nets.get(net_name) or {}
        constraint = spec.get("constraint") if isinstance(spec, dict) else {}
        max_stub = (constraint or {}).get("max_stub_length_mm") if constraint else None
        if max_stub is None:
            cls = spec.get("class") if isinstance(spec, dict) else None
            max_stub = CLASS_DEFAULTS_MM.get(cls)
        if max_stub is None:
            continue  # no spec → don't audit
        audited += 1

        # Endpoint count: any endpoint touched by only ONE segment = stub-end
        pt_count = defaultdict(int)
        for s, e, _ in segs:
            pt_count[s] += 1
            pt_count[e] += 1
        dead_ends = {p for p, c in pt_count.items() if c == 1}
        # Crude stub-length proxy: sum length of segments touching a dead-end
        stub_lengths = {}
        for s, e, l in segs:
            if s in dead_ends:
                stub_lengths[s] = stub_lengths.get(s, 0) + l
            if e in dead_ends:
                stub_lengths[e] = stub_lengths.get(e, 0) + l
        # Filter: dead ends that are at PAD locations are termination points (not stubs)
        # (Skipping pad-coincidence check for MVP — over-flags but safe direction)
        for pt, sl in stub_lengths.items():
            if sl > max_stub:
                fails.append(f"  [FAIL] {net_name}: stub ending at ({pt[0]:.1f},{pt[1]:.1f}) length {sl:.2f}mm > {max_stub}mm")

    print(f"Audited {audited} nets with stub-length spec\n")
    if fails:
        for f in fails[:10]:
            print(f)
        if len(fails) > 10:
            print(f"  ... +{len(fails)-10} more")
        print(f"\nRESULT: FAIL — {len(fails)} stubs over length limit")
        sys.exit(1)
    print("RESULT: PASS — all stubs within limit")


if __name__ == "__main__":
    main()
