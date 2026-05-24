#!/usr/bin/env python3
"""investigate_11_fails.py — per-case diagnosis for the 11 R19 fail pairs.

For each, show:
  - src + dst current positions
  - expected mirror position
  - what's at the expected position (host conflict)
  - whether snap-with-loose-validation could work
"""
import pcbnew
import math
import re
import sys

sys.path.insert(0, '/home/novatics64/escworker/pcb.ai/hardware/kicad/scripts')
from snap_mirror_validated import (
    build_state, find_pairs, position_violates, expected_mirror, PCB
)


def main():
    board = pcbnew.LoadBoard(PCB)
    state = build_state(board)
    pairs = find_pairs(state)
    fails = sorted([p for p in pairs if p[3] > 5.0], key=lambda x: -x[3])

    print(f"=== Per-case investigation for {len(fails)} >5mm fails ===\n")

    for src, dst, dst_ch, d_orig, (ex, ey) in fails:
        s = state[src]
        d = state[dst]
        sx, sy = s['cx'], s['cy']
        dx, dy = d['cx'], d['cy']
        print(f"--- {src} → {dst} (CH1→CH{dst_ch}, Δ_current={d_orig:.2f}mm) ---")
        print(f"  src {src}: ({sx:.2f}, {sy:.2f})  lib={s['lib']}  ch_nets={s['ch_nets']}")
        print(f"  dst {dst}: ({dx:.2f}, {dy:.2f})  lib={d['lib']}  ch_nets={d['ch_nets']}")
        print(f"  expected mirror: ({ex:.2f}, {ey:.2f})")
        # Try exact snap with validation
        vios = position_violates(dst, ex, ey, state)
        print(f"  snap-validate at ({ex:.2f}, {ey:.2f}): {vios if vios else 'OK'}")
        # What's near expected position?
        near = []
        for oref, o in state.items():
            if oref == dst: continue
            if o['layer'] != d['layer']: continue
            dd = math.hypot(o['cx'] - ex, o['cy'] - ey)
            if dd < 3.0:
                near.append((oref, o['cx'], o['cy'], dd, o['lib']))
        near.sort(key=lambda x: x[3])
        if near:
            print(f"  Components within 3mm of ({ex:.2f}, {ey:.2f}):")
            for nr, nx, ny, nd, nlib in near[:5]:
                print(f"    {nr}: ({nx:.2f}, {ny:.2f}) d={nd:.2f}  lib={nlib}")
        print()


if __name__ == "__main__":
    main()
