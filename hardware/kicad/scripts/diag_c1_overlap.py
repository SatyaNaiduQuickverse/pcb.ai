#!/usr/bin/env python3
"""diag_c1_overlap.py — Sai-catch #12 diagnostic per master 2026-05-24.

Print C1 footprint, body bbox, and whether claimed-overlapping components
(J34, J11, C151, D22, D73, D82, R158, R160, R19, L10) are inside C1's body
solderable region.

Body bbox = footprint silk outline bounding box (NOT courtyard).
Pad inside body = any pad of suspect component lies inside C1's silk-bbox.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

SUSPECTS = ['J34', 'J11', 'C151', 'D22', 'D73', 'D82',
            'R158', 'R160', 'R19', 'L10']


def silk_bbox_mm(fp):
    """Return (xmin, ymin, xmax, ymax) of footprint silk outline (F.SilkS+B.SilkS).
    Falls back to courtyard if no silk drawings present."""
    silk_pts = []
    courtyard_pts = []
    for d in fp.GraphicalItems():
        if not isinstance(d, pcbnew.PCB_SHAPE):
            continue
        layer = d.GetLayer()
        if layer in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            bucket = silk_pts
        elif layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            bucket = courtyard_pts
        else:
            continue
        bb = d.GetBoundingBox()
        bucket.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                       pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    pts = silk_pts or courtyard_pts
    if not pts:
        bb = fp.GetBoundingBox()
        return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
    xs = [b[0] for b in pts] + [b[2] for b in pts]
    ys = [b[1] for b in pts] + [b[3] for b in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def pad_centers_mm(fp):
    out = []
    for pad in fp.Pads():
        p = pad.GetPosition()
        out.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), pad.GetPadName()))
    return out


def main():
    board = pcbnew.LoadBoard(PCB)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}

    c1 = fps.get('C1')
    if c1 is None:
        print("C1 NOT FOUND")
        return 1

    c1_pos = c1.GetPosition()
    c1_x = pcbnew.ToMM(c1_pos.x); c1_y = pcbnew.ToMM(c1_pos.y)
    c1_lib = c1.GetFPID().GetUniStringLibId()
    c1_bbox = silk_bbox_mm(c1)
    c1_layer = "F.Cu" if c1.GetLayer() == pcbnew.F_Cu else "B.Cu"

    print(f"=== C1 diagnostic ===")
    print(f"  Footprint lib:  {c1_lib}")
    print(f"  Layer:          {c1_layer}")
    print(f"  Center:         ({c1_x:.3f}, {c1_y:.3f}) mm")
    print(f"  Silk bbox:      x[{c1_bbox[0]:.3f},{c1_bbox[2]:.3f}] "
          f"y[{c1_bbox[1]:.3f},{c1_bbox[3]:.3f}] mm")
    print(f"  Silk size:      {c1_bbox[2]-c1_bbox[0]:.2f} × "
          f"{c1_bbox[3]-c1_bbox[1]:.2f} mm")
    print()

    xmin, ymin, xmax, ymax = c1_bbox

    print(f"=== Suspects inside C1 silk-bbox ===")
    print(f"{'Ref':<6} {'Layer':<5} {'CenterX':>8} {'CenterY':>8} "
          f"{'InBody':<7} {'PadsIn':<7} {'Footprint':<40}")
    print("-" * 95)

    for ref in SUSPECTS:
        fp = fps.get(ref)
        if fp is None:
            print(f"{ref:<6} NOT FOUND")
            continue
        pos = fp.GetPosition()
        fx = pcbnew.ToMM(pos.x); fy = pcbnew.ToMM(pos.y)
        layer = "F" if fp.GetLayer() == pcbnew.F_Cu else "B"
        in_body = xmin <= fx <= xmax and ymin <= fy <= ymax
        pads_in = 0
        for (px, py, _) in pad_centers_mm(fp):
            if xmin <= px <= xmax and ymin <= py <= ymax:
                pads_in += 1
        flib = fp.GetFPID().GetUniStringLibId()
        marker = "YES" if in_body else "no"
        print(f"{ref:<6} {layer:<5} {fx:>8.3f} {fy:>8.3f} "
              f"{marker:<7} {pads_in:<7} {flib:<40}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
