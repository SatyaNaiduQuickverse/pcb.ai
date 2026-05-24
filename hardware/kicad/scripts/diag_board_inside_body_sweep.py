#!/usr/bin/env python3
"""diag_board_inside_body_sweep.py — Sai-catch #12 board-wide sweep.

For every same-layer (A, B) pair, if A's center OR any A pad lies inside B's
SILK bbox AND area(A) < 0.5 × area(B): record violation.

Output:
  1. Total violation count
  2. Per-host (B) breakdown: how many invaders each host has
  3. Per-inhabitant-family breakdown: 0402, 0603, SOD, etc.
  4. Top 30 violators
"""
import pcbnew
from collections import defaultdict

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

AREA_RATIO_THRESHOLD = 0.5  # A must be smaller than 50% of B


def silk_bbox_mm(fp):
    silk_pts = []
    ctyd_pts = []
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


def main():
    board = pcbnew.LoadBoard(PCB)
    fps = list(board.GetFootprints())
    print(f"Total footprints: {len(fps)}")

    # Pre-compute per-fp: bbox, area, center, layer, pad positions
    data = []
    for fp in fps:
        b = silk_bbox_mm(fp)
        area = (b[2] - b[0]) * (b[3] - b[1])
        pos = fp.GetPosition()
        cx = pcbnew.ToMM(pos.x); cy = pcbnew.ToMM(pos.y)
        pads = []
        for pad in fp.Pads():
            p = pad.GetPosition()
            pads.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
        layer = fp.GetLayer()
        data.append({
            'fp': fp, 'ref': fp.GetReference(), 'bbox': b, 'area': area,
            'cx': cx, 'cy': cy, 'pads': pads, 'layer': layer,
            'lib': fp.GetFPID().GetUniStringLibId(),
        })

    violations = []
    host_count = defaultdict(int)
    inhabitant_family = defaultdict(int)

    for a in data:
        for b in data:
            if a['ref'] == b['ref']: continue
            if a['layer'] != b['layer']: continue
            if a['area'] >= AREA_RATIO_THRESHOLD * b['area']: continue
            bx0, by0, bx1, by1 = b['bbox']
            ctr_in = bx0 <= a['cx'] <= bx1 and by0 <= a['cy'] <= by1
            pads_in = sum(1 for (px, py) in a['pads']
                          if bx0 <= px <= bx1 and by0 <= py <= by1)
            if ctr_in or pads_in > 0:
                violations.append({
                    'invader': a['ref'], 'inv_lib': a['lib'],
                    'host': b['ref'], 'host_lib': b['lib'],
                    'ctr_in': ctr_in, 'pads_in': pads_in,
                })
                host_count[b['ref']] += 1
                # Classify inhabitant
                lib = a['lib'].lower()
                if '0402' in lib: fam = '0402_passive'
                elif '0603' in lib: fam = '0603_passive'
                elif '0805' in lib: fam = '0805_passive'
                elif 'sod-123' in lib: fam = 'SOD-123_diode'
                elif 'sod-323' in lib: fam = 'SOD-323_diode'
                elif 'sma' in lib: fam = 'SMA_diode'
                elif 'sot' in lib: fam = 'SOT_transistor'
                else: fam = 'other'
                inhabitant_family[fam] += 1

    print(f"\n=== TOTAL VIOLATIONS: {len(violations)} ===")
    print(f"\n=== HOSTS (top 30 by invader count) ===")
    print(f"{'Ref':<8} {'Count':<6} {'Footprint':<60}")
    for ref, n in sorted(host_count.items(), key=lambda kv: -kv[1])[:30]:
        host_lib = next((v['host_lib'] for v in violations if v['host'] == ref), '?')
        print(f"{ref:<8} {n:<6} {host_lib:<60}")

    print(f"\n=== INHABITANT FAMILIES ===")
    for fam, n in sorted(inhabitant_family.items(), key=lambda kv: -kv[1]):
        print(f"  {fam:<25} {n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
