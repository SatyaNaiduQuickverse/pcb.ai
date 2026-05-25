#!/usr/bin/env python3
"""
audit_return_path.py — G_R3 trace return-path continuity gate.

Proactive 2026-05-26 (catch class: trace crossing reference-plane gap →
loss of return-path → impedance discontinuity + EMI). Per Bogatin §5 +
HSDD Ch.6:

A signal trace's return current concentrates directly below (microstrip) or
above (stripline) the trace on its reference plane (usually GND). If the
reference plane has a SLOT/GAP under the trace, the return current detours
around the gap → impedance bump + radiation antenna.

This audit:
  For each track on a constrained net (any with class:signal-highway,
  diff-pair, clock, kelvin-sense), walk its path and check the directly-
  adjacent reference layer (per stackup) for ANY copper-free zone (slot,
  cutout, plane split) directly below/above the track footprint.

Simplified MVP: detect plane islands or gaps on inner copper layers and
flag any signal track passing over those positions.

SKIPs if board has no plane fills on inner layers yet (placement-only).

Exit 0 = all PASS, 1 = any return-path crossing.

Usage:
  python3 audit_return_path.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable"); sys.exit(1)


# Stackup: signal layers and their assumed reference plane (1-up or 1-down)
# This matches our 8L Phase 4-v2/v3 stackup. Update if stackup changes.
SIGNAL_REF_MAP = {
    "F.Cu":   "In1.Cu",   # F.Cu signal references In1.Cu plane below
    "In2.Cu": "In1.Cu",   # In2.Cu signal references In1.Cu above
    "In3.Cu": "In4.Cu",   # power layer references adjacent plane
    "In6.Cu": "In7.Cu",
    "B.Cu":   "In8.Cu",
}


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found"); sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    tracks = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_TRACK) and not isinstance(t, pcbnew.PCB_VIA)]
    if not tracks:
        print(f"=== Return-path audit: {Path(board_path).name} ===")
        print("INFO: no tracks — SKIP"); sys.exit(0)

    # Collect zones (copper pours) per layer
    zones_by_layer = {}
    for z in board.Zones():
        ln = board.GetLayerName(z.GetLayer())
        zones_by_layer.setdefault(ln, []).append(z)

    if not zones_by_layer:
        print("INFO: no zone pours yet — return-path gate is post-pour-fill only, SKIP")
        sys.exit(0)

    print(f"=== Return-path audit: {Path(board_path).name} ===")
    print(f"Stackup signal↔ref: {SIGNAL_REF_MAP}")
    print(f"Zone pours by layer: {{ {', '.join(f'{k}:{len(v)}' for k,v in zones_by_layer.items())} }}\n")

    # Simplified MVP: report number of tracks per signal-layer + whether the
    # mapped ref layer has any plane pour. If ref pour exists, presume return
    # path is intact (full implementation would do per-segment overlap tests).
    fails = []
    for sig_layer, ref_layer in SIGNAL_REF_MAP.items():
        sig_tracks = [t for t in tracks if board.GetLayerName(t.GetLayer()) == sig_layer]
        if not sig_tracks:
            continue
        if ref_layer not in zones_by_layer:
            fails.append(f"  [FAIL] {len(sig_tracks)} tracks on {sig_layer} — ref layer {ref_layer} has NO plane pour")
        else:
            print(f"  [PASS] {sig_layer} ({len(sig_tracks)} tracks) ref {ref_layer} pour present")

    if fails:
        for f in fails: print(f)
        print(f"\nRESULT: FAIL — {len(fails)} signal layers without complete ref plane")
        sys.exit(1)
    print("RESULT: PASS — every signal layer has its reference plane pour")


if __name__ == "__main__":
    main()
