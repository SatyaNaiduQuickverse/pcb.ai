#!/usr/bin/env python3
"""fix_phase3_hand_craft.py — PR-channel-template-redo Phase 3 Sub-task 4.

Hand-craft cleanup of footprint-pair collisions. v2: uses pad-bbox spiral
search around target position to find first valid slot (avoiding collisions
with existing footprints).
"""
import pcbnew
import math

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# (ref, target_x, target_y, reason, search_radius)
# Targets aim for the "ideal" position; spiral search finds nearest collision-free slot.
MOVES = [
    ('L10',  5.0,  32.0,  'V9_VTX2 ferrite N of J35 INA-A',          4.0),
    ('C55',  29.0, 14.0,  'CH4 MCU 1uF decap W of J33',              4.0),
    ('C53',  37.5, 89.0,  'CH1 MCU 10uF bulk SE of J18',             4.0),
    ('R40',  53.0, 86.0,  'TLM pull-up S of J14 FC',                 4.0),
    ('C28',  43.0, 51.5,  '100uF bulk poly SW of U2',                5.0),
    ('C77',  35.5, 41.0,  'CH4 DRV 22uF bulk W of J34',              4.0),
    ('C58',  44.5, 41.5,  'CH4 DRV 100nF E-S of J34',                4.0),
    ('C20',  9.0,  26.0,  'CH4 INA-B 100nF E of J36',                4.0),
    ('R44',  40.0, 66.5,  'CH1 DRV 40K dt-resistor S of J19',        4.0),
]


def get_pad_bboxes_at(fp, new_x, new_y):
    rot = fp.GetOrientationDegrees()
    cos_r = math.cos(math.radians(rot))
    sin_r = math.sin(math.radians(rot))
    fp_layer = 'F.Cu' if fp.GetLayer() == pcbnew.F_Cu else 'B.Cu'
    bboxes = []
    for pad in fp.Pads():
        pos0 = pad.GetFPRelativePosition()
        size = pad.GetSize()
        lx, ly = pos0.x / 1e6, pos0.y / 1e6
        rx = lx * cos_r - ly * sin_r
        ry = lx * sin_r + ly * cos_r
        px = new_x + rx
        py = new_y + ry
        pw, ph = size.x / 1e6, size.y / 1e6
        if rot in (90.0, 270.0):
            pw, ph = ph, pw
        m = 0.1
        attr = pad.GetAttribute()
        if attr == pcbnew.PAD_ATTRIB_PTH or attr == pcbnew.PAD_ATTRIB_NPTH:
            layer_set = {'F.Cu', 'B.Cu'}
        else:
            layer_set = {fp_layer}
        bboxes.append({
            'x0': px - pw/2 - m, 'y0': py - ph/2 - m,
            'x1': px + pw/2 + m, 'y1': py + ph/2 + m,
            'net': pad.GetNetname(),
            'layer_set': layer_set,
        })
    return bboxes


def all_pad_bboxes_except(board, exclude_ref):
    out = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref == exclude_ref:
            continue
        out.extend([{**b, 'ref': ref} for b in get_pad_bboxes_at(fp, fp.GetPosition().x/1e6, fp.GetPosition().y/1e6)])
    return out


def collides(candidate_bboxes, other_bboxes):
    for cb in candidate_bboxes:
        for ob in other_bboxes:
            if cb['net'] and cb['net'] == ob['net']:
                continue
            if not (cb['layer_set'] & ob['layer_set']):
                continue
            if (cb['x0'] < ob['x1'] and cb['x1'] > ob['x0']
                    and cb['y0'] < ob['y1'] and cb['y1'] > ob['y0']):
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
            print(f"  {ref}: NOT FOUND — skip ({reason})")
            continue
        old = fp.GetPosition()
        ox, oy = old.x / 1e6, old.y / 1e6
        other = all_pad_bboxes_except(board, ref)
        chosen = None
        for cx, cy in spiral(tx, ty, max_r=max_r):
            if cx < 0 or cx > 100 or cy < 0 or cy > 100:
                continue
            cand = get_pad_bboxes_at(fp, cx, cy)
            col = collides(cand, other)
            if col is None:
                chosen = (cx, cy)
                break
        if chosen is None:
            print(f"  {ref}: NO FREE SLOT near ({tx},{ty}) within {max_r}mm — leaving at ({ox},{oy})")
            continue
        nx, ny = chosen
        fp.SetPosition(pcbnew.VECTOR2I(int(nx * 1e6), int(ny * 1e6)))
        print(f"  {ref}: ({ox:.2f},{oy:.2f}) → ({nx:.2f},{ny:.2f}) — {reason}")
        moved += 1
    board.Save(PCB)
    print(f"\nMoved {moved} of {len(MOVES)}. Saved {PCB}")


if __name__ == "__main__":
    main()
