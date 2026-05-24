#!/usr/bin/env python3
"""explore_bulk_cap_alts.py — Option B feasibility test (master 2026-05-24).

For each bulk cap C1-C4, list alternative positions within 10mm that:
  a. Don't intersect any other component's silk bbox
  b. Don't intersect motor-TP zone
  c. Stay within their original quadrant (low-ESR to FETs)
  d. Don't go off-board
"""
import pcbnew
import math

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
BULK_CAP_REFS = ['C1', 'C2', 'C3', 'C4']
SEARCH_RADIUS_MM = 10.0
STEP_MM = 0.5
HOST_MIN_AREA_MM2 = 5.0
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
        data[ref] = {
            'fp': fp, 'bbox': b, 'area': area,
            'cx': pcbnew.ToMM(pos.x), 'cy': pcbnew.ToMM(pos.y),
            'layer': fp.GetLayer(),
        }

    # Host silk bboxes (large enough to host)
    silk_keepouts = []
    for ref, d in data.items():
        if ref in BULK_CAP_REFS: continue  # the bulk caps themselves
        if d['area'] >= HOST_MIN_AREA_MM2:
            silk_keepouts.append((d['bbox'], d['layer'], ref))

    # Motor TPs
    motor_tps = [(d['cx'], d['cy']) for r, d in data.items() if r in MOTOR_TP_REFS]

    for cap_ref in BULK_CAP_REFS:
        cap = data[cap_ref]
        cx0, cy0 = cap['cx'], cap['cy']
        cap_bbox = cap['bbox']
        # Relative offset of silk bbox from cap center (since silk drawing is fixed
        # relative to fp origin)
        bx_off_min = cap_bbox[0] - cx0
        by_off_min = cap_bbox[1] - cy0
        bx_off_max = cap_bbox[2] - cx0
        by_off_max = cap_bbox[3] - cy0
        # Cap silk size for clearance accounting
        bw = bx_off_max - bx_off_min
        bh = by_off_max - by_off_min

        print(f"\n=== {cap_ref} alternatives ===")
        print(f"  Current: ({cx0:.2f}, {cy0:.2f})  silk size {bw:.2f}×{bh:.2f}mm")

        alts = []
        # Spiral search outward
        for r in [v * STEP_MM for v in range(1, int(SEARCH_RADIUS_MM / STEP_MM) + 1)]:
            n_pts = max(8, int(r / STEP_MM) * 4)
            for i in range(n_pts):
                theta = 2 * math.pi * i / n_pts
                nx = cx0 + r * math.cos(theta)
                ny = cy0 + r * math.sin(theta)
                # Stay in same quadrant
                if (cx0 < 50) != (nx < 50): continue
                if (cy0 < 50) != (ny < 50): continue
                # On-board
                if nx < 6 or nx > 94 or ny < 6 or ny > 94: continue
                # New silk bbox of this cap if moved
                nb = (nx + bx_off_min, ny + by_off_min,
                       nx + bx_off_max, ny + by_off_max)
                # Don't overlap any host silk bbox
                bad = False
                for (hb, hlayer, href) in silk_keepouts:
                    if hlayer != cap['layer']: continue
                    if nb[0] < hb[2] and nb[2] > hb[0] and nb[1] < hb[3] and nb[3] > hb[1]:
                        bad = True; break
                if bad: continue
                # Not in motor TP zone (cap CENTER + bbox half-width margin)
                in_tp = False
                for mx, my in motor_tps:
                    if abs(nx - mx) < MOTOR_PAD_KEEPOUT_MM + bw/2 and \
                       abs(ny - my) < MOTOR_PAD_KEEPOUT_MM + bh/2:
                        in_tp = True; break
                if in_tp: continue
                alts.append((nx, ny, r))
        if alts:
            print(f"  Found {len(alts)} viable alt positions")
            # Show 5 closest
            alts.sort(key=lambda a: a[2])
            for nx, ny, r in alts[:5]:
                print(f"    ({nx:.2f}, {ny:.2f})  Δ={r:.2f}mm")
        else:
            print(f"  NO viable alt positions in {SEARCH_RADIUS_MM}mm spiral")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
