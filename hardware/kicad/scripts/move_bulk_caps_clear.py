#!/usr/bin/env python3
"""move_bulk_caps_clear.py — Sai-catch #12 Option B v2 (master 2026-05-24).

Find nearest position for each bulk cap (C1, C2, C3, C4, C33) such that:
  a. New silk bbox doesn't contain any of the current invaders' pad centers
  b. Doesn't overlap any other host silk bbox
  c. Doesn't break coincident-placement (≥1.6mm center clear)
  d. Doesn't violate motor-TP keep-out
  e. Different-net pad-collision OK (same-net intentional — bulk caps live
     on +VMOTOR/GND planes, lots of same-net overlap is normal)
  f. Stays in original quadrant + on-board

Picks the SMALLEST displacement that satisfies (a)-(f). Codified per master
2026-05-24 directive.
"""
import pcbnew
import math

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

BULK_CAPS_TO_MOVE = ['C1', 'C2', 'C3', 'C4', 'C33']

SEARCH_RADIUS_MM = 15.0
STEP_MM = 0.5
HOST_MIN_AREA_MM2 = 5.0
AREA_RATIO_THRESHOLD = 4.0
SILK_MARGIN = 0.5
COINCIDENT_MIN_MM = 1.6
MOTOR_TP_REFS = ('TP19','TP20','TP21','TP26','TP27','TP28',
                 'TP33','TP34','TP35','TP40','TP41','TP42')
MOTOR_PAD_KEEPOUT_MM = 2.0


def silk_bbox(fp):
    silk_pts = []; ctyd_pts = []
    for d in fp.GraphicalItems():
        if not isinstance(d, pcbnew.PCB_SHAPE): continue
        ly = d.GetLayer()
        bb = d.GetBoundingBox()
        box = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
               pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
        if ly in (pcbnew.F_SilkS, pcbnew.B_SilkS): silk_pts.append(box)
        elif ly in (pcbnew.F_CrtYd, pcbnew.B_CrtYd): ctyd_pts.append(box)
    pts = silk_pts or ctyd_pts
    if not pts:
        bb = fp.GetBoundingBox()
        return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
    xs = [b[0] for b in pts] + [b[2] for b in pts]
    ys = [b[1] for b in pts] + [b[3] for b in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def main():
    board = pcbnew.LoadBoard(PCB)
    fps = list(board.GetFootprints())

    # Per-fp data
    data = {}
    for fp in fps:
        ref = fp.GetReference()
        b = silk_bbox(fp)
        area = (b[2] - b[0]) * (b[3] - b[1])
        pos = fp.GetPosition()
        cx = pcbnew.ToMM(pos.x); cy = pcbnew.ToMM(pos.y)
        pads_pos = []
        pad_bxs = []
        for pad in fp.Pads():
            pp = pad.GetPosition()
            pads_pos.append((pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y)))
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            pad_bxs.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                            pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                            ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu),
                            pad.GetNetname() or ''))
        data[ref] = {
            'fp': fp, 'bbox': b, 'area': area,
            'cx': cx, 'cy': cy, 'pads_pos': pads_pos, 'pad_bxs': pad_bxs,
            'layer': fp.GetLayer(),
        }

    moves = []
    for cap_ref in BULK_CAPS_TO_MOVE:
        if cap_ref not in data:
            print(f"  WARN: {cap_ref} not found, skipping")
            continue
        cap = data[cap_ref]
        cx0, cy0 = cap['cx'], cap['cy']
        cap_bbox = cap['bbox']
        # Silk bbox offset from center
        bx_off_min = cap_bbox[0] - cx0; by_off_min = cap_bbox[1] - cy0
        bx_off_max = cap_bbox[2] - cx0; by_off_max = cap_bbox[3] - cy0
        bw = bx_off_max - bx_off_min; bh = by_off_max - by_off_min

        # Identify CURRENT invaders for this cap
        current_invaders = []
        for ref, d in data.items():
            if ref == cap_ref: continue
            if d['layer'] != cap['layer']: continue
            if d['area'] >= cap['area'] / AREA_RATIO_THRESHOLD: continue  # only smaller
            cb = cap['bbox']
            ctr_in = cb[0] <= d['cx'] <= cb[2] and cb[1] <= d['cy'] <= cb[3]
            pads_in = sum(1 for (px, py) in d['pads_pos']
                          if cb[0] <= px <= cb[2] and cb[1] <= py <= cb[3])
            if ctr_in or pads_in > 0:
                current_invaders.append(d)

        # Host silk keepouts (every fp area ≥ 5mm² except itself + other bulk caps to move)
        silk_keepouts = []
        for ref, d in data.items():
            if ref == cap_ref: continue
            if ref in BULK_CAPS_TO_MOVE: continue
            if d['area'] >= HOST_MIN_AREA_MM2:
                silk_keepouts.append((d['bbox'], d['layer'], ref))
        for other in BULK_CAPS_TO_MOVE:
            if other == cap_ref or other not in data: continue
            od = data[other]
            silk_keepouts.append((od['bbox'], od['layer'], other))

        # Coincident: all other centers
        other_centers = [(d['cx'], d['cy'], d['layer'])
                         for r, d in data.items() if r != cap_ref]

        # Motor TPs
        motor_tps = [(data[r]['cx'], data[r]['cy'])
                     for r in MOTOR_TP_REFS if r in data]

        # Other pads — only those on different nets (same-net is OK)
        cap_pad_nets = {bb[6] for bb in cap['pad_bxs']}
        other_pads_diffnet = []
        for ref, d in data.items():
            if ref == cap_ref: continue
            for bb in d['pad_bxs']:
                pad_net = bb[6]
                if pad_net in cap_pad_nets: continue  # same-net OK
                other_pads_diffnet.append(bb)

        cap_pad_rel = []
        for bb in cap['pad_bxs']:
            cap_pad_rel.append((bb[0] - cx0, bb[1] - cy0,
                                bb[2] - cx0, bb[3] - cy0,
                                bb[4], bb[5]))

        # Spiral search — nearest position that clears all invaders + other constraints
        chosen = None
        for r_steps in range(1, int(SEARCH_RADIUS_MM / STEP_MM) + 1):
            r = r_steps * STEP_MM
            n_pts = max(8, r_steps * 6)
            for i in range(n_pts):
                theta = 2 * math.pi * i / n_pts
                nx = cx0 + r * math.cos(theta)
                ny = cy0 + r * math.sin(theta)
                # Stay in original quadrant
                if (cx0 < 50) != (nx < 50): continue
                if (cy0 < 50) != (ny < 50): continue
                # On-board
                if nx + bx_off_min < 1 or nx + bx_off_max > 99: continue
                if ny + by_off_min < 1 or ny + by_off_max > 99: continue
                # New silk bbox
                nb = (nx + bx_off_min, ny + by_off_min,
                       nx + bx_off_max, ny + by_off_max)
                # 1) CLEARS all current invaders
                cleared = True
                for inv in current_invaders:
                    if nb[0] <= inv['cx'] <= nb[2] and nb[1] <= inv['cy'] <= nb[3]:
                        cleared = False; break
                    for (px, py) in inv['pads_pos']:
                        if nb[0] <= px <= nb[2] and nb[1] <= py <= nb[3]:
                            cleared = False; break
                    if not cleared: break
                if not cleared: continue
                # 2) Don't overlap other host silk
                bad_silk = False
                for (hb, hlayer, _) in silk_keepouts:
                    if hlayer != cap['layer']: continue
                    if nb[0] < hb[2] - SILK_MARGIN and nb[2] > hb[0] + SILK_MARGIN and \
                       nb[1] < hb[3] - SILK_MARGIN and nb[3] > hb[1] + SILK_MARGIN:
                        bad_silk = True; break
                if bad_silk: continue
                # 3) Coincident
                coinc = False
                for (ox, oy, ol) in other_centers:
                    if ol != cap['layer']: continue
                    if math.hypot(ox - nx, oy - ny) < COINCIDENT_MIN_MM:
                        coinc = True; break
                if coinc: continue
                # 4) Motor TP zone
                in_tp = False
                for (mx, my) in motor_tps:
                    if abs(nx - mx) < MOTOR_PAD_KEEPOUT_MM + bw/2 and \
                       abs(ny - my) < MOTOR_PAD_KEEPOUT_MM + bh/2:
                        in_tp = True; break
                if in_tp: continue
                # 5) Different-net pad collision
                collide = False
                for (rx1, ry1, rx2, ry2, mF, mB) in cap_pad_rel:
                    mx1 = nx + rx1; my1 = ny + ry1
                    mx2 = nx + rx2; my2 = ny + ry2
                    for (ox1, oy1, ox2, oy2, oF, oB, _) in other_pads_diffnet:
                        same = (mF and oF) or (mB and oB)
                        if not same: continue
                        if mx1 - 0.2 < ox2 and mx2 + 0.2 > ox1 and \
                           my1 - 0.2 < oy2 and my2 + 0.2 > oy1:
                            collide = True; break
                    if collide: break
                if collide: continue
                chosen = (nx, ny, r)
                break
            if chosen: break

        if not chosen:
            print(f"  {cap_ref}: NO valid alternative within {SEARCH_RADIUS_MM}mm")
            continue
        nx, ny, dr = chosen
        cap['fp'].SetPosition(pcbnew.VECTOR2I(int(nx * 1e6), int(ny * 1e6)))
        dx = nx - cx0; dy = ny - cy0
        data[cap_ref]['cx'] = nx; data[cap_ref]['cy'] = ny
        data[cap_ref]['bbox'] = (cap_bbox[0]+dx, cap_bbox[1]+dy,
                                  cap_bbox[2]+dx, cap_bbox[3]+dy)
        data[cap_ref]['pads_pos'] = [(p[0]+dx, p[1]+dy) for p in cap['pads_pos']]
        data[cap_ref]['pad_bxs'] = [
            (b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy, b[4], b[5], b[6])
            for b in cap['pad_bxs']
        ]
        moves.append((cap_ref, cx0, cy0, nx, ny, dr, len(current_invaders)))
        print(f"  {cap_ref}: ({cx0:.2f}, {cy0:.2f}) → ({nx:.2f}, {ny:.2f})  "
              f"Δ={dr:.2f}mm  cleared {len(current_invaders)} invaders")

    print(f"\nMoved {len(moves)} / {len(BULK_CAPS_TO_MOVE)} bulk caps")
    board.Save(PCB)
    return 0 if len(moves) == len(BULK_CAPS_TO_MOVE) else 1


if __name__ == "__main__":
    raise SystemExit(main())
