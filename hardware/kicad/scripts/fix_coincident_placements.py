#!/usr/bin/env python3
"""fix_coincident_placements.py — PR-channel-template-redo Phase 3 master review.

Master 2026-05-24 rejected PR #71 due to 152 coincident-placement bugs (pairs of
components at <1.5mm center-to-center on same layer). Root cause: role-aware
spiral search exempts parent IC's body bbox from rejection, which means
multiple passives anchored to the same parent FET land at the SAME first
available spiral position outside the FET pad bboxes.

This script iteratively finds the worst coincident pair and moves ONE of
them (lower-priority, by ref-prefix ranking) to the next collision-free
position using pad-bbox spiral. Repeats until no coincident bugs remain.

Priority for staying (others move):
  Q (FET) > J (IC connector) > U (IC) > TP (test point) > L (inductor) >
  D (diode) > R (resistor) > C (cap)

I.e., FETs/ICs anchor; passives spread.
"""
import pcbnew
import math
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
COINCIDENT_THRESH = 1.5
SEARCH_MAX_R = 6.0

PRIORITY = {'Q': 1, 'J': 2, 'U': 3, 'TP': 4, 'L': 5, 'F': 6, 'D': 7, 'R': 8, 'C': 9, 'TH': 5, 'H': 0}


def prefix_priority(ref):
    for p in sorted(PRIORITY.keys(), key=lambda k: -len(k)):
        if ref.startswith(p):
            return PRIORITY[p]
    return 99


def get_pad_bboxes_at(fp, new_x, new_y):
    rot = fp.GetOrientationDegrees()
    cos_r = math.cos(math.radians(rot)); sin_r = math.sin(math.radians(rot))
    bboxes = []
    for pad in fp.Pads():
        pos0 = pad.GetFPRelativePosition(); size = pad.GetSize()
        lx, ly = pos0.x/1e6, pos0.y/1e6
        rx = lx*cos_r - ly*sin_r; ry = lx*sin_r + ly*cos_r
        px, py = new_x+rx, new_y+ry
        pw, ph = size.x/1e6, size.y/1e6
        if rot in (90.0, 270.0): pw, ph = ph, pw
        m = 0.1
        ls = pad.GetLayerSet()
        layer_set = set()
        if ls.Contains(pcbnew.F_Cu): layer_set.add('F.Cu')
        if ls.Contains(pcbnew.B_Cu): layer_set.add('B.Cu')
        bboxes.append({'x0':px-pw/2-m,'y0':py-ph/2-m,'x1':px+pw/2+m,'y1':py+ph/2+m,
                       'net':pad.GetNetname(),'layer_set':layer_set})
    return bboxes


def all_pad_bboxes_except(board, exclude_ref):
    out = []
    for fp in board.GetFootprints():
        if fp.GetReference() == exclude_ref: continue
        out.extend([{**b, 'ref': fp.GetReference()} for b in get_pad_bboxes_at(fp, fp.GetPosition().x/1e6, fp.GetPosition().y/1e6)])
    return out


def collides(cb, ob_list):
    for cb_i in cb:
        for ob in ob_list:
            if cb_i['net'] and cb_i['net'] == ob['net']: continue
            if not (cb_i['layer_set'] & ob['layer_set']): continue
            if cb_i['x0'] < ob['x1'] and cb_i['x1'] > ob['x0'] and cb_i['y0'] < ob['y1'] and cb_i['y1'] > ob['y0']:
                return ob['ref']
    return None


def center_collides(fp, nx, ny, board, exclude_ref):
    """Also check no other component within 1.5mm center-to-center on same layer."""
    fp_layer = fp.GetLayer()
    for of in board.GetFootprints():
        if of.GetReference() == exclude_ref: continue
        if of.GetLayer() != fp_layer: continue
        ox, oy = of.GetPosition().x/1e6, of.GetPosition().y/1e6
        if math.hypot(nx - ox, ny - oy) < COINCIDENT_THRESH:
            return of.GetReference()
    return None


def spiral(cx, cy, max_r, step=0.3):
    yield (cx, cy)
    for r_steps in range(1, int(max_r / step) + 2):
        r = r_steps * step
        n_pts = max(12, r_steps * 8)
        for i in range(n_pts):
            theta = 2 * math.pi * i / n_pts
            yield (cx + r * math.cos(theta), cy + r * math.sin(theta))


def find_coincident_pairs(board):
    fps = []
    for fp in board.GetFootprints():
        if fp.GetReference().startswith('H'): continue
        fps.append((fp.GetReference(), fp.GetPosition().x/1e6, fp.GetPosition().y/1e6, fp.GetLayer()))
    bugs = []
    for i, (r1, x1, y1, l1) in enumerate(fps):
        for r2, x2, y2, l2 in fps[i+1:]:
            if l1 != l2: continue
            d = math.hypot(x1 - x2, y1 - y2)
            if d < COINCIDENT_THRESH:
                bugs.append((d, r1, r2, x1, y1))
    return bugs


def main():
    board = pcbnew.LoadBoard(str(PCB))
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    moves = []
    for iteration in range(5):
        bugs = find_coincident_pairs(board)
        if not bugs:
            print(f"\nIteration {iteration}: 0 coincident bugs — done")
            break
        print(f"\nIteration {iteration}: {len(bugs)} coincident pairs")
        # Move-set: for each bug, decide which ref to move
        to_move = set()
        for d, r1, r2, x, y in bugs:
            p1, p2 = prefix_priority(r1), prefix_priority(r2)
            mover = r1 if p1 > p2 else (r2 if p2 > p1 else (r1 if r1 > r2 else r2))
            to_move.add(mover)
        moved = 0
        for ref in to_move:
            fp = by_ref[ref]
            ox, oy = fp.GetPosition().x/1e6, fp.GetPosition().y/1e6
            # Spiral away from current center
            chosen = None
            for nx, ny in spiral(ox, oy, max_r=SEARCH_MAX_R):
                if nx < 1 or nx > 99 or ny < 1 or ny > 99: continue
                if center_collides(fp, nx, ny, board, ref): continue
                cand = get_pad_bboxes_at(fp, nx, ny)
                others = all_pad_bboxes_except(board, ref)
                if collides(cand, others): continue
                chosen = (nx, ny); break
            if chosen:
                nx, ny = chosen
                fp.SetPosition(pcbnew.VECTOR2I(int(nx * 1e6), int(ny * 1e6)))
                moves.append((ref, ox, oy, nx, ny))
                moved += 1
        print(f"  Moved {moved} refs")
        if moved == 0:
            print(f"  Couldn't move any — abort")
            break
    board.Save(str(PCB))
    print(f"\nTotal moves: {len(moves)}")
    bugs = find_coincident_pairs(board)
    print(f"Remaining coincident pairs: {len(bugs)}")


if __name__ == "__main__":
    main()
