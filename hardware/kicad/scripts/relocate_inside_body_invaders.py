#!/usr/bin/env python3
"""relocate_inside_body_invaders.py — Sai-catch #12 fix script.

Per master 2026-05-24 dispatch.

Algorithm:
  1. Build silk-bbox keepout list for all "host candidates" (area ≥ 5mm²)
  2. For each component on the board: if its center OR any pad lies inside a
     host's silk-bbox AND area(self) < 0.25 × area(host) AND not motor-exempt:
     it's an INVADER. Mark for relocation.
  3. For each invader: spiral-search outward from current position. Accept the
     first (x, y) that:
       a. is on-board (2-98mm both axes)
       b. is OUTSIDE all silk-bboxes (margin 1mm)
       c. doesn't collide with any other pad-bbox on same layer
       d. stays within 10mm of original anchor (preserves R23 anchoring)
  4. Move invader to chosen position.
  5. Save board, report.

Codified per [[feedback-anchor-outside-parent-body]] +
[[feedback-sai-catches-are-samples]].
"""
import pcbnew
import math
import re

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

AREA_RATIO_THRESHOLD = 4.0   # host > 4× inhabitant
HOST_MIN_AREA_MM2 = 5.0
SILK_MARGIN_MM = 0.5         # only reject positions actually inside silk (was 1.0 — too aggressive)
PAD_CLEAR_MM = 1.0           # bumped from 0.6 — was still creating DIFFNET
MAX_RELOCATE_MM = 8.0        # absolute cap (bumped from 6 for harder cases)
COINCIDENT_MIN_MM = 1.6      # audit threshold is 1.5; use 1.6 for safety
DECOUPLING_MAX_FROM_PIN_MM = 3.0   # R25 same-side-decoupling rule

# Motor TP keep-out (matches audit_layout_compliance R20)
MOTOR_TP_REFS = ('TP19','TP20','TP21','TP26','TP27','TP28',
                 'TP33','TP34','TP35','TP40','TP41','TP42')
MOTOR_PAD_KEEPOUT_MM = 2.0

# Motor-adjacent-net exempt regex (matches audit_layout_compliance.py R20)
_MOTOR_ADJACENT_NET_RE = re.compile(
    r'^(MOTOR_[ABC]_CH\d+|BEMF_[ABC]_CH\d+|CSA_[ABC]_OUT_CH\d+|CSA_MAX_CH\d+'
    r'|SHUNT_[ABC]_TOP_CH\d+|GH[ABC]_CH\d+|GL[ABC]_CH\d+|BST[ABC]_CH\d+)$'
)


def silk_bbox_mm(fp):
    silk_pts = []; ctyd_pts = []
    for d in fp.GraphicalItems():
        if not isinstance(d, pcbnew.PCB_SHAPE):
            continue
        layer = d.GetLayer()
        if layer in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            bucket = silk_pts
        elif layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            bucket = ctyd_pts
        else:
            continue
        bb = d.GetBoundingBox()
        bucket.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                       pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    pts = silk_pts or ctyd_pts
    if not pts:
        bb = fp.GetBoundingBox()
        return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
    xs = [b[0] for b in pts] + [b[2] for b in pts]
    ys = [b[1] for b in pts] + [b[3] for b in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def is_motor_exempt(fp):
    for pad in fp.Pads():
        no = pad.GetNet()
        if no is None: continue
        n = no.GetNetname() or ''
        if _MOTOR_ADJACENT_NET_RE.match(n):
            return True
    return False


def main():
    board = pcbnew.LoadBoard(PCB)
    fps = list(board.GetFootprints())

    # 1. Collect per-fp data
    info = []
    for fp in fps:
        ref = fp.GetReference()
        if ref.startswith('H'): continue
        b = silk_bbox_mm(fp)
        area = (b[2] - b[0]) * (b[3] - b[1])
        if area <= 0: continue
        pos = fp.GetPosition()
        cx = pcbnew.ToMM(pos.x); cy = pcbnew.ToMM(pos.y)
        pads_pos = []
        pad_bboxes = []
        for p in fp.Pads():
            pp = p.GetPosition()
            pads_pos.append((pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y)))
            bb = p.GetBoundingBox()
            ls = p.GetLayerSet()
            pad_bboxes.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                               pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                               ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu)))
        info.append({
            'ref': ref, 'fp': fp, 'bbox': b, 'area': area,
            'cx': cx, 'cy': cy, 'pads_pos': pads_pos, 'pad_bboxes': pad_bboxes,
            'layer': fp.GetLayer(),
            'motor_exempt': is_motor_exempt(fp),
        })

    # 2. Host silk-bbox keepouts
    silk_keepouts = []
    for fp_info in info:
        if fp_info['area'] >= HOST_MIN_AREA_MM2:
            silk_keepouts.append((fp_info['bbox'][0], fp_info['bbox'][1],
                                  fp_info['bbox'][2], fp_info['bbox'][3],
                                  fp_info['layer'], fp_info['ref']))

    # 3. Find invaders
    invaders = []
    for inh in info:
        if inh['motor_exempt']:
            continue
        ia = inh['area']
        for host in info:
            if host['ref'] == inh['ref']: continue
            if host['layer'] != inh['layer']: continue
            if host['area'] < AREA_RATIO_THRESHOLD * ia: continue
            bx0, by0, bx1, by1 = host['bbox']
            ctr_in = bx0 <= inh['cx'] <= bx1 and by0 <= inh['cy'] <= by1
            pads_in = sum(1 for (px, py) in inh['pads_pos']
                          if bx0 <= px <= bx1 and by0 <= py <= by1)
            if ctr_in or pads_in > 0:
                invaders.append((inh, host))
                break
    print(f"Invaders to relocate: {len(invaders)}")

    # 4. Build all pad bboxes (for collision check post-move)
    def all_pad_bboxes(exclude_ref):
        bxs = []
        for f in info:
            if f['ref'] == exclude_ref: continue
            for bb in f['pad_bboxes']:
                bxs.append(bb + (f['ref'],))
        return bxs

    # Collect motor TP positions for keep-out check
    motor_tp_positions = []
    for fp_info in info:
        if fp_info['ref'] in MOTOR_TP_REFS:
            motor_tp_positions.append((fp_info['cx'], fp_info['cy'],
                                        fp_info['layer']))

    def in_motor_tp_zone(nx, ny, layer):
        for mx, my, ml in motor_tp_positions:
            if abs(nx - mx) < MOTOR_PAD_KEEPOUT_MM and abs(ny - my) < MOTOR_PAD_KEEPOUT_MM:
                return True
        return False

    # Find decoupling parent: for a cap on +V*/+3V3 net, find the IC pin with
    # smallest pad-to-cap distance currently — that's its parent VDD/VCC pin.
    def find_decoupling_parent_pin(inhabitant):
        ref = inhabitant['ref']
        if not ref.startswith('C'): return None
        fp = inhabitant['fp']
        cap_nets = set()
        for pad in fp.Pads():
            no = pad.GetNet()
            if no is None: continue
            n = no.GetNetname() or ''
            if n.startswith('+') or n in ('VCC', 'VDD', 'AVDD', 'AVCC'):
                cap_nets.add(n)
        if not cap_nets: return None
        # Find closest IC pin on shared net
        best = None
        best_d = 1e9
        for other in info:
            oref = other['ref']
            if oref == ref: continue
            if not (oref.startswith('U') or oref.startswith('J')): continue
            for p in other['fp'].Pads():
                no = p.GetNet()
                if no is None: continue
                n = no.GetNetname() or ''
                if n not in cap_nets: continue
                pp = p.GetPosition()
                px = pcbnew.ToMM(pp.x); py = pcbnew.ToMM(pp.y)
                d = math.hypot(px - inhabitant['cx'], py - inhabitant['cy'])
                if d < best_d:
                    best_d = d; best = (px, py, oref)
        return best

    def is_decoupling_class(inhabitant):
        return find_decoupling_parent_pin(inhabitant) is not None

    def center_collide(inhabitant, nx, ny):
        """True if any other component center within COINCIDENT_MIN_MM on same layer."""
        layer = inhabitant['layer']
        for other in info:
            if other['ref'] == inhabitant['ref']: continue
            if other['layer'] != layer: continue
            if math.hypot(other['cx'] - nx, other['cy'] - ny) < COINCIDENT_MIN_MM:
                return True
        return False

    def position_clear(inhabitant, nx, ny, all_bxs, decoup_pin=None):
        """True if moving inhabitant to (nx, ny):
        - center not inside any silk keepout
        - center not coincident with another component
        - inhabitant's pad bboxes don't collide on same layer
        - inhabitant's pad centers not inside any host silk
        - not in motor-TP keep-out zone
        - if decoup_pin given: center within 3mm of decoup pin
        """
        if center_collide(inhabitant, nx, ny):
            return False
        if in_motor_tp_zone(nx, ny, inhabitant['layer']):
            return False
        if decoup_pin is not None:
            px, py, _ = decoup_pin
            if math.hypot(nx - px, ny - py) > DECOUPLING_MAX_FROM_PIN_MM:
                return False
        layer = inhabitant['layer']
        # Silk-body check (center)
        for sx0, sy0, sx1, sy1, slay, sref in silk_keepouts:
            if sref == inhabitant['ref']: continue
            if slay != layer: continue
            if sx0 - SILK_MARGIN_MM <= nx <= sx1 + SILK_MARGIN_MM and \
               sy0 - SILK_MARGIN_MM <= ny <= sy1 + SILK_MARGIN_MM:
                return False
        # Recompute moved pad bboxes
        dx = nx - inhabitant['cx']; dy = ny - inhabitant['cy']
        moved_pads = []
        for (x1, y1, x2, y2, F, B) in inhabitant['pad_bboxes']:
            moved_pads.append((x1+dx, y1+dy, x2+dx, y2+dy, F, B))
        # Pad-bbox collision vs all others on same layer
        for (mx1, my1, mx2, my2, mF, mB) in moved_pads:
            for (ox1, oy1, ox2, oy2, oF, oB, oref) in all_bxs:
                same = (mF and oF) or (mB and oB)
                if not same: continue
                # Add small clearance
                if mx1 - PAD_CLEAR_MM < ox2 and mx2 + PAD_CLEAR_MM > ox1 and \
                   my1 - PAD_CLEAR_MM < oy2 and my2 + PAD_CLEAR_MM > oy1:
                    return False
            # Moved pad inside any silk keepout
            mxc = (mx1 + mx2) / 2; myc = (my1 + my2) / 2
            for sx0, sy0, sx1, sy1, slay, sref in silk_keepouts:
                if sref == inhabitant['ref']: continue
                if slay != layer: continue
                if sx0 - SILK_MARGIN_MM <= mxc <= sx1 + SILK_MARGIN_MM and \
                   sy0 - SILK_MARGIN_MM <= myc <= sy1 + SILK_MARGIN_MM:
                    return False
        return True

    def spiral_points(cx, cy, max_dist, step=0.5):
        yield (cx, cy)
        for r_steps in range(1, int(max_dist / step) + 2):
            r = r_steps * step
            n = max(8, r_steps * 6)
            for i in range(n):
                theta = 2 * math.pi * i / n
                yield (cx + r * math.cos(theta), cy + r * math.sin(theta))

    relocated = 0
    failed = []
    # Sort by inhabitant area (smallest first — easier to fit)
    invaders.sort(key=lambda x: x[0]['area'])

    for (inh, host) in invaders:
        ref = inh['ref']
        cx, cy = inh['cx'], inh['cy']
        all_bxs = all_pad_bboxes(ref)
        chosen = None
        max_d = DECOUPLING_MAX_RELOCATE_MM if is_decoupling_class(inh) else MAX_RELOCATE_MM
        for (nx, ny) in spiral_points(cx, cy, max_d):
            if nx < 2.0 or nx > 98.0 or ny < 2.0 or ny > 98.0: continue
            if math.hypot(nx - cx, ny - cy) < 0.1: continue  # skip self
            if not position_clear(inh, nx, ny, all_bxs): continue
            chosen = (nx, ny)
            break
        if chosen is None:
            failed.append(ref)
            continue
        # Move
        nx, ny = chosen
        inh['fp'].SetPosition(pcbnew.VECTOR2I(int(nx * 1e6), int(ny * 1e6)))
        # Update local tracking
        dx = nx - cx; dy = ny - cy
        inh['cx'] = nx; inh['cy'] = ny
        inh['pads_pos'] = [(p[0]+dx, p[1]+dy) for p in inh['pads_pos']]
        inh['pad_bboxes'] = [(b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy, b[4], b[5])
                              for b in inh['pad_bboxes']]
        inh['bbox'] = (inh['bbox'][0]+dx, inh['bbox'][1]+dy,
                       inh['bbox'][2]+dx, inh['bbox'][3]+dy)
        relocated += 1
        print(f"  {ref}: ({cx:.2f},{cy:.2f}) → ({nx:.2f},{ny:.2f}) "
              f"(was inside {host['ref']})")

    print(f"\nRelocated: {relocated} / {len(invaders)}")
    if failed:
        print(f"Failed (no clear slot within {MAX_RELOCATE_MM}mm): {len(failed)}")
        for r in failed:
            print(f"  {r}")
    board.Save(PCB)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
