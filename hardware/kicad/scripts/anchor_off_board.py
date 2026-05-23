#!/usr/bin/env python3
"""anchor_off_board.py — PR-channel-template-redo Phase 3 helper (2026-05-23).

Anchors every footprint currently positioned off-board (outside 0-100mm range)
to its electrical parent (FET, IC, connector) via net-connectivity matching.

Differs from auto_anchor_passives.py:
- Reads ACTUAL footprint positions from PCB to decide what's unplaced (rather
  than trusting place_board.py dict membership; refs may be hardcoded but
  skipped due to value mismatch, leaving them off-board).
- Writes placements DIRECTLY to PCB instead of emitting a dict.

Algorithm per component to anchor:
  1. List nets it connects to (skip power rails for parent disambiguation).
  2. For each non-power net, find on-board components sharing it.
  3. Pick parent: most-specific net + prefer Q/U/J (FET/IC/connector) > passives.
  4. Place at parent + spiral offset (avoid pad collisions with already-placed).
"""
import pcbnew
import re
from collections import defaultdict
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
BOARD_MIN = 0.0
BOARD_MAX = 100.0
POWER_NETS = re.compile(
    r'^(GND|GNDA?|\+?3V3.*|\+?5V.*|\+?V(MOTOR|9_).*|V5.*|V9.*|VMOTOR.*|'
    r'VBAT.*|HALL_VCC.*|TLM|N\$\d+)$'
)
SPIRAL_OFFSETS = [
    (2.5, 0.0), (-2.5, 0.0), (0.0, 2.5), (0.0, -2.5),
    (2.0, 2.0), (-2.0, 2.0), (2.0, -2.0), (-2.0, -2.0),
    (4.0, 0.0), (-4.0, 0.0), (0.0, 4.0), (0.0, -4.0),
    (4.0, 2.5), (-4.0, 2.5), (4.0, -2.5), (-4.0, -2.5),
    (2.5, 4.0), (-2.5, 4.0), (2.5, -4.0), (-2.5, -4.0),
    (6.0, 0.0), (-6.0, 0.0), (0.0, 6.0), (0.0, -6.0),
]


def main():
    board = pcbnew.LoadBoard(str(PCB))
    fps = list(board.GetFootprints())

    # Build per-fp info
    info = {}
    for fp in fps:
        ref = fp.GetReference()
        p = fp.GetPosition()
        x, y = p.x / 1e6, p.y / 1e6
        nets = {pad.GetNetname() for pad in fp.Pads() if pad.GetNetname()}
        on_board = (BOARD_MIN - 0.5 <= x <= BOARD_MAX + 0.5
                    and BOARD_MIN - 0.5 <= y <= BOARD_MAX + 0.5)
        info[ref] = {
            'fp': fp, 'x': x, 'y': y, 'nets': nets, 'on_board': on_board
        }

    placed_refs = {r for r, d in info.items() if d['on_board']}
    unplaced_refs = {r for r, d in info.items() if not d['on_board']}
    print(f"On-board: {len(placed_refs)}, off-board: {len(unplaced_refs)}")

    # Build net→refs index
    net_refs = defaultdict(set)
    for r, d in info.items():
        for n in d['nets']:
            net_refs[n].add(r)

    # Occupancy: (x,y) of placed refs to avoid collision
    occupied = [(d['x'], d['y']) for d in info.values() if d['on_board']]

    def slot_free(x, y, min_d=1.5):
        for ox, oy in occupied:
            if abs(x - ox) < min_d and abs(y - oy) < min_d:
                return False
        return BOARD_MIN <= x <= BOARD_MAX and BOARD_MIN <= y <= BOARD_MAX

    placed = 0
    for ref in sorted(unplaced_refs):
        d = info[ref]
        # Find best parent
        candidates = []
        for n in d['nets']:
            if POWER_NETS.match(n):
                continue
            on_n = net_refs[n] - {ref}
            on_n_placed = [r for r in on_n if r in placed_refs]
            if not on_n_placed:
                continue
            spec = 100.0 / len(net_refs[n])
            for a in on_n_placed:
                bonus = 10 if a.startswith(('Q', 'U', 'J')) else 0
                candidates.append((spec + bonus, a, n))
        # Fallback: allow power-rail anchors to IC-class parents
        if not candidates:
            for n in d['nets']:
                on_n = net_refs[n] - {ref}
                on_n_placed = [
                    r for r in on_n if r in placed_refs
                    and r.startswith(('Q', 'U', 'J'))
                ]
                if not on_n_placed:
                    continue
                spec = 1.0 / max(1, len(net_refs[n]))
                for a in on_n_placed:
                    candidates.append((spec, a, n))
        if not candidates:
            print(f"  {ref}: NO PARENT FOUND — skip")
            continue
        candidates.sort(reverse=True)
        score, parent_ref, parent_net = candidates[0]
        px, py = info[parent_ref]['x'], info[parent_ref]['y']
        new_xy = None
        for ox, oy in SPIRAL_OFFSETS:
            nx, ny = px + ox, py + oy
            if slot_free(nx, ny):
                new_xy = (nx, ny)
                break
        if new_xy is None:
            print(f"  {ref}: NO FREE SLOT near {parent_ref} — skip")
            continue
        nx, ny = new_xy
        d['fp'].SetPosition(pcbnew.VECTOR2I(
            int(nx * 1e6), int(ny * 1e6)
        ))
        occupied.append((nx, ny))
        placed_refs.add(ref)
        placed += 1
        layer = 'F.Cu' if d['fp'].GetLayer() == pcbnew.F_Cu else 'B.Cu'
        print(f"  {ref} ({list(d['nets'])[0][:20]:20s}) → "
              f"{parent_ref}+offset ({nx:.1f}, {ny:.1f}) {layer}  via {parent_net}")

    board.Save(str(PCB))
    print(f"\nPlaced {placed} of {len(unplaced_refs)} unplaced components")
    print(f"Saved {PCB}")


if __name__ == "__main__":
    main()
