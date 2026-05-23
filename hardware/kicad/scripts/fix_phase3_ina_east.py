#!/usr/bin/env python3
"""fix_phase3_ina_east.py — PR-channel-template-redo Phase 3 Sub-task C.

Move CH-INA186 phase-A/phase-B 3mm inward to clear motor-TP keep-out zones.
Phase-C INAs at N/S edges don't have TP collision and stay.

Move map:
  CH1: J20 (5,62)→(8,62), J21 (5,74)→(8,74). J22 stays @(40,92).
  CH2: J25 (95,62)→(92,62), J27 (95,74)→(92,74). J26 stays @(60,92).
  CH3: J30 (95,38)→(92,38), J32 (95,26)→(92,26). J31 stays @(60,8).
  CH4: J35 (5,38)→(8,38), J36 (5,26)→(8,26). J37 stays @(40,8).

Also relocate C61 (currently at (83.6, 89.5)) to CH1 (NW quadrant X<50, Y>50)
to clear CH-PASSIVE-QUADRANT violation. C61 is c_local bus cap V5→GND per
channel_skidl.py — anchor on V5 net near the channel cluster.
"""
import pcbnew, math

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

INA_MOVES = [
    ('J20', 8.0,  62.0,  'CH1 INA phase A — east from X=5 to clear TP19 zone'),
    ('J21', 8.0,  74.0,  'CH1 INA phase B — east from X=5 to clear TP20 zone'),
    ('J25', 92.0, 62.0,  'CH2 INA phase A — west from X=95 to clear TP26 zone'),
    ('J27', 92.0, 74.0,  'CH2 INA phase B — west from X=95 to clear TP27 zone'),
    ('J30', 92.0, 38.0,  'CH3 INA phase A — west from X=95 to clear TP33 zone'),
    ('J32', 92.0, 26.0,  'CH3 INA phase B — west from X=95 to clear TP34 zone'),
    ('J35', 8.0,  38.0,  'CH4 INA phase A — east from X=5 to clear TP40 zone'),
    ('J36', 8.0,  26.0,  'CH4 INA phase B — east from X=5 to clear TP41 zone'),
]
# C61 to CH1 zone — anchor near Q5/Q6 phase-A FET pair on V5 rail (V5 is a global rail
# but c_local goes near each FET cluster). Place at (25, 65) — CH1 NW interior.
C61_TARGET = (25.0, 65.0)


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


def all_pad_bboxes_except(board, exclude_refs):
    out = []
    for fp in board.GetFootprints():
        if fp.GetReference() in exclude_refs: continue
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

    # Move all INAs first as a batch (so they don't conflict with each other in collision check)
    ina_refs = {ref for ref, *_ in INA_MOVES}
    other = all_pad_bboxes_except(board, ina_refs)

    for ref, tx, ty, reason in INA_MOVES:
        fp = by_ref.get(ref)
        if fp is None:
            print(f"  {ref}: NOT FOUND"); continue
        old = fp.GetPosition(); ox, oy = old.x/1e6, old.y/1e6
        chosen = None
        for cx, cy in spiral(tx, ty, max_r=3.0):
            if cx < 2 or cx > 98 or cy < 2 or cy > 98: continue
            cand = get_pad_bboxes_at(fp, cx, cy)
            col = collides(cand, other)
            if col is None:
                chosen = (cx, cy); break
        if chosen is None:
            print(f"  {ref}: NO SLOT near ({tx},{ty}) — stayed at ({ox:.1f},{oy:.1f})")
            continue
        nx, ny = chosen
        fp.SetPosition(pcbnew.VECTOR2I(int(nx*1e6), int(ny*1e6)))
        # Add newly-placed INA pad bboxes so subsequent INAs see them
        other.extend([{**b, 'ref': ref} for b in get_pad_bboxes_at(fp, nx, ny)])
        print(f"  {ref}: ({ox:.2f},{oy:.2f}) → ({nx:.2f},{ny:.2f}) — {reason}")
        moved += 1

    # Move C61 to CH1
    c61 = by_ref.get('C61')
    if c61 is not None:
        all_other = all_pad_bboxes_except(board, {'C61'})
        chosen = None
        tx, ty = C61_TARGET
        for cx, cy in spiral(tx, ty, max_r=6.0):
            if not (0 <= cx <= 50 and 50 <= cy <= 100): continue  # CH1 zone
            cand = get_pad_bboxes_at(c61, cx, cy)
            col = collides(cand, all_other)
            if col is None:
                chosen = (cx, cy); break
        if chosen:
            nx, ny = chosen
            old = c61.GetPosition(); ox, oy = old.x/1e6, old.y/1e6
            c61.SetPosition(pcbnew.VECTOR2I(int(nx*1e6), int(ny*1e6)))
            print(f"  C61:  ({ox:.2f},{oy:.2f}) → ({nx:.2f},{ny:.2f}) — relocate to CH1 NW quadrant")
            moved += 1

    board.Save(PCB)
    print(f"\nMoved {moved} of {len(INA_MOVES) + 1}. Saved.")


if __name__ == "__main__":
    main()
