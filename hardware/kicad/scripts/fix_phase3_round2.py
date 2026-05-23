#!/usr/bin/env python3
"""fix_phase3_round2.py — clear remaining 9 PAD-OVERLAP + 3 DECOUPLING.

Round 2 of Phase 3 hand-craft.

PAD-OVERLAP-DIFFNET (9 pairs from audit):
  R100/R101 (CH2 BEMF C divider) — top/bot Rs too close
  R104/R105 (VREF_2V5 divider) — channel-specific divider top/bot too close
  R106/R107 (VREF_2V5 divider) — same
  J6.9 vs Q27.9: J6 (BEC AOZ1284) overlapping Q27 (CH4 FET)
  J6.9 vs R15.1: cross-subsystem
  R138 vs J10.3: PG_RPI pull-up vs J10 BEC out

DECOUPLING fixes — move 3 caps within 3mm of U4/U5/U7:
  C82 → near U4 (CH1 AND gate at 38, 78)
  C51 → near U5 (CH2 LM393 at 55, 84)
  C109 → near U7 (CH3 LM393 at 55, 16)
"""
import pcbnew, math

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

MOVES = [
    # DECOUPLING — 3 caps within 3mm of needy ICs
    ('C82',  40.0, 78.0,  '100nF decap → adjacent U4 CH1 AND gate', 3.0),
    ('C51',  53.0, 84.0,  '100nF decap → adjacent U5 CH2 LM393',    3.0),
    ('C109', 55.0, 13.0,  '100nF decap → adjacent U7 CH3 LM393',    3.0),
    # BEMF divider pair separations (R100/R101 etc)
    ('R100', 96.0, 68.0,  'CH2 BEMF C top — space from R101',       4.0),
    ('R101', 92.0, 68.0,  'CH2 BEMF C bot — space from R100',       4.0),
    # VREF_2V5 divider pair separations (per channel, R104/R105 are VREF_I_TRIP for CH2 maybe)
    ('R104', 58.0, 78.0,  'VREF divider top — space from R105',     4.0),
    ('R105', 52.0, 78.0,  'VREF divider bot',                       4.0),
    ('R106', 58.0, 80.0,  'VREF divider top — space from R107',     4.0),
    ('R107', 52.0, 80.0,  'VREF divider bot',                       4.0),
    # BEC cross-subsystem fixes
    ('J6',   60.0, 30.0,  'AOZ1284 BEC4 — west of orig location to clear Q27', 8.0),
    ('R15',  65.0, 30.0,  'BUCK5 FB — relocate east of J6',         5.0),
    ('R138', 28.0, 38.0,  'PG_RPI pull-up — relocate from J10 area', 5.0),
]


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


def spiral(cx, cy, max_r=4.0, step=0.5):
    yield (cx, cy)
    for r_steps in range(1, int(max_r / step) + 2):
        r = r_steps * step
        n_pts = max(8, r_steps * 6)
        for i in range(n_pts):
            theta = 2 * math.pi * i / n_pts
            yield (cx + r * math.cos(theta), cy + r * math.sin(theta))


def main():
    board = pcbnew.LoadBoard(PCB)
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    moved = 0
    for ref, tx, ty, reason, max_r in MOVES:
        fp = by_ref.get(ref)
        if fp is None:
            print(f"  {ref}: NOT FOUND ({reason})")
            continue
        old = fp.GetPosition(); ox, oy = old.x/1e6, old.y/1e6
        other = all_pad_bboxes_except(board, ref)
        chosen = None
        for cx, cy in spiral(tx, ty, max_r=max_r):
            if cx < 0 or cx > 100 or cy < 0 or cy > 100: continue
            cand = get_pad_bboxes_at(fp, cx, cy)
            col = collides(cand, other)
            if col is None:
                chosen = (cx, cy); break
        if chosen is None:
            print(f"  {ref}: NO SLOT near ({tx},{ty}) — stayed at ({ox:.1f},{oy:.1f})")
            continue
        nx, ny = chosen
        fp.SetPosition(pcbnew.VECTOR2I(int(nx*1e6), int(ny*1e6)))
        print(f"  {ref}: ({ox:.2f},{oy:.2f}) → ({nx:.2f},{ny:.2f}) — {reason}")
        moved += 1
    board.Save(PCB)
    print(f"\nMoved {moved} of {len(MOVES)}. Saved.")


if __name__ == "__main__":
    main()
