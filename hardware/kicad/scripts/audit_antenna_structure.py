#!/usr/bin/env python3
"""
audit_antenna_structure.py — G_R6 unintentional antenna structure gate.

Proactive 2026-05-26 (catch class: long unterminated trace + sharp dV/dt =
EMC compliance failure at fab/EMC bench). Per Ott EMC §6 + IEC 61000-4:

For any aggressor net (high dV/dt: SW_CHn, MOTOR_X_CHn, clocks), a trace
length λ/4 at the fundamental switching frequency becomes an efficient
quarter-wave antenna. For our 24-48kHz PWM:
  λ/4 at 50kHz = 1500m  → not a near-field concern
  λ/4 at 50MHz (5th harmonic of FET edge): 1.5m → not on PCB
  λ/4 at 500MHz (FET-edge harmonic): 150mm → APPROACHED on our 100×100mm board

Practical antenna risk: traces ≥ 50mm on aggressor nets with NO ground
shield/island below (or no nearby return path). Per Ott p.198, 50mm of
trace with 1ns edge rise = 25Ω characteristic, radiates 5-10dB above limits.

This gate:
  For each high-dV/dt net (SW_*, MOTOR_*_CHn, +VMOTOR_CHn) verify total
  cumulative track length ≤ 50mm OR has continuous ref plane (validated
  via G_R3). If neither: FAIL antenna risk.

SKIPs pre-routing.

Exit 0 = all PASS, 1 = any antenna structure risk.

Usage:
  python3 audit_antenna_structure.py <board.kicad_pcb>
"""

import re
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable"); sys.exit(1)


AGGRESSOR_PATTERN = re.compile(r"^(SW_CH|MOTOR_[ABC]_CH|\+VMOTOR_CH)\d", re.IGNORECASE)
MAX_AGGRESSOR_LENGTH_MM = 50.0  # λ/4 at ~500 MHz harmonic (Ott §6)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found"); sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    tracks = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_TRACK) and not isinstance(t, pcbnew.PCB_VIA)]
    if not tracks:
        print(f"=== Antenna structure audit: {Path(board_path).name} ===")
        print("INFO: no tracks — SKIP"); sys.exit(0)

    print(f"=== Antenna structure audit: {Path(board_path).name} ===")
    print(f"Aggressor pattern: {AGGRESSOR_PATTERN.pattern}")
    print(f"Max aggressor net length: {MAX_AGGRESSOR_LENGTH_MM}mm (Ott §6, λ/4 at ~500MHz)\n")

    # Sum length per aggressor net
    net_length = {}
    for t in tracks:
        n = t.GetNetname()
        if not AGGRESSOR_PATTERN.match(n):
            continue
        s, e = t.GetStart(), t.GetEnd()
        dx = pcbnew.ToMM(e.x - s.x)
        dy = pcbnew.ToMM(e.y - s.y)
        net_length[n] = net_length.get(n, 0) + (dx * dx + dy * dy) ** 0.5

    if not net_length:
        print("No aggressor nets routed yet — SKIP")
        sys.exit(0)

    fails = []
    for n, l in sorted(net_length.items()):
        if l > MAX_AGGRESSOR_LENGTH_MM:
            fails.append(f"  [FAIL] {n}: cumulative {l:.1f}mm > {MAX_AGGRESSOR_LENGTH_MM}mm — antenna risk")
        else:
            print(f"  [PASS] {n}: {l:.1f}mm")

    if fails:
        for f in fails: print(f)
        print(f"\nRESULT: FAIL — {len(fails)} potential antenna structures")
        sys.exit(1)
    print("RESULT: PASS — no aggressor net exceeds antenna-length threshold")


if __name__ == "__main__":
    main()
