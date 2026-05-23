#!/usr/bin/env python3
"""diag_all_bulk_caps.py — Master 2026-05-24 Q2: verify C1-C4 + find all
components inside each bulk-cap silk bbox."""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
BULK = ['C1', 'C2', 'C3', 'C4']


def silk_bbox_mm(fp):
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


def main():
    board = pcbnew.LoadBoard(PCB)
    fps = list(board.GetFootprints())
    fp_by_ref = {fp.GetReference(): fp for fp in fps}

    for ref in BULK:
        c = fp_by_ref.get(ref)
        if c is None:
            print(f"{ref}: NOT FOUND"); continue
        bbox = silk_bbox_mm(c)
        pos = c.GetPosition()
        cx = pcbnew.ToMM(pos.x); cy = pcbnew.ToMM(pos.y)
        lib = c.GetFPID().GetUniStringLibId()
        layer = "F" if c.GetLayer() == pcbnew.F_Cu else "B"
        print(f"\n=== {ref} [{layer}.Cu] {lib} ===")
        print(f"  Center: ({cx:.2f}, {cy:.2f})  Silk bbox: "
              f"x[{bbox[0]:.2f}-{bbox[2]:.2f}] y[{bbox[1]:.2f}-{bbox[3]:.2f}] "
              f"size {bbox[2]-bbox[0]:.2f}×{bbox[3]-bbox[1]:.2f}mm")

        xmin, ymin, xmax, ymax = bbox
        invaders = []
        for other in fps:
            oref = other.GetReference()
            if oref == ref: continue
            if other.GetLayer() != c.GetLayer(): continue  # different layer = OK
            ox = pcbnew.ToMM(other.GetPosition().x)
            oy = pcbnew.ToMM(other.GetPosition().y)
            pads_in = 0
            for pad in other.Pads():
                p = pad.GetPosition()
                px = pcbnew.ToMM(p.x); py = pcbnew.ToMM(p.y)
                if xmin <= px <= xmax and ymin <= py <= ymax:
                    pads_in += 1
            ctr_in = xmin <= ox <= xmax and ymin <= oy <= ymax
            if pads_in > 0 or ctr_in:
                olib = other.GetFPID().GetUniStringLibId()
                invaders.append((oref, ox, oy, pads_in, ctr_in, olib))
        if not invaders:
            print(f"  Invaders: NONE — clean")
        else:
            print(f"  Invaders: {len(invaders)} (FAB BLOCKING)")
            for r, x, y, p, c_in, lib in invaders:
                m = "CTR+PADS" if c_in else "PADS"
                print(f"    {r:<6} ({x:.2f},{y:.2f}) pads_in={p} {m:<10} {lib}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
