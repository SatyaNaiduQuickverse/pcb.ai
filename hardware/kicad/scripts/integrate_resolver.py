#!/usr/bin/env python3
"""integrate_resolver.py — PR-A4-integrate: iteratively resolve pad overlaps by
displacing the SMALLER component in each conflict pair (typically auto-anchored
passives).

Only modifies refs in ch234_passives_dict.py (auto-anchored set);
never touches FETs, ICs, mount holes, or hand-placed S1-S6 components.
"""
import pcbnew, re, sys
from pathlib import Path
import collections

CH234_DICT = Path("hardware/kicad/scripts/ch234_passives_dict.py")
PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
MARGIN = 0.4  # mm clearance — larger to break local minima
MAX_ITER = 12

def load_dict():
    d = {}
    txt = CH234_DICT.read_text()
    m = re.search(r"CH234_PASSIVES\s*=\s*\{(.*?)\n\}", txt, re.DOTALL)
    if m:
        for em in re.finditer(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)", m.group(1)):
            d[em.group(1)] = (float(em.group(2)), float(em.group(3)), em.group(4), float(em.group(5)))
    return d

def save_dict(d):
    with open(CH234_DICT, "w") as f:
        f.write('"""Auto-anchored + mirrors + integrate-resolver outputs.\n"""\n')
        f.write("CH234_PASSIVES = {\n")
        for ref in sorted(d.keys()):
            x, y, layer, rot = d[ref]
            f.write(f"    '{ref}': ({x:.2f}, {y:.2f}, '{layer}', {rot:.1f}),\n")
        f.write("}\n")

def get_overlaps():
    b = pcbnew.LoadBoard(PCB)
    pads = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            bb = p.GetBoundingBox(); ls = p.GetLayerSet()
            pads.append((ref, p.GetPadName(), bb.GetLeft()/1e6, bb.GetTop()/1e6, bb.GetRight()/1e6, bb.GetBottom()/1e6, ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu)))
    out = []
    for i in range(len(pads)):
        for j in range(i+1, len(pads)):
            ar, ap, ax1, ay1, ax2, ay2, aF, aB = pads[i]
            cr, cp, bx1, by1, bx2, by2, cF, cB = pads[j]
            if ar == cr: continue
            if not ((aF and cF) or (aB and cB)): continue
            if ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1:
                out.append((ar, ax1, ay1, ax2, ay2, cr, bx1, by1, bx2, by2))
    return out

def main():
    placements = load_dict()
    for it in range(MAX_ITER):
        overlaps = get_overlaps()
        if not overlaps:
            print(f"Iter {it}: 0 overlaps — CONVERGED"); break
        print(f"Iter {it}: {len(overlaps)} overlaps")
        moved = set()
        for ar, ax1, ay1, ax2, ay2, cr, bx1, by1, bx2, by2 in overlaps:
            # Pick movable ref (must be in placements dict, and small bbox)
            a_in = ar in placements
            c_in = cr in placements
            a_size = (ax2-ax1)*(ay2-ay1)
            c_size = (bx2-bx1)*(by2-by1)
            if a_in and c_in:
                # Pick smaller
                if a_size <= c_size:
                    mv = ar; mv_pad = (ax1, ay1, ax2, ay2); fx_pad = (bx1, by1, bx2, by2)
                else:
                    mv = cr; mv_pad = (bx1, by1, bx2, by2); fx_pad = (ax1, ay1, ax2, ay2)
            elif a_in:
                mv = ar; mv_pad = (ax1, ay1, ax2, ay2); fx_pad = (bx1, by1, bx2, by2)
            elif c_in:
                mv = cr; mv_pad = (bx1, by1, bx2, by2); fx_pad = (ax1, ay1, ax2, ay2)
            else:
                continue
            if mv in moved: continue
            mx1, my1, mx2, my2 = mv_pad
            fx1, fy1, fx2, fy2 = fx_pad
            ox = min(mx2, fx2) - max(mx1, fx1)
            oy = min(my2, fy2) - max(my1, fy1)
            mcx = (mx1+mx2)/2; mcy = (my1+my2)/2
            fcx = (fx1+fx2)/2; fcy = (fy1+fy2)/2
            if ox < oy:
                dx = ox + MARGIN
                if mcx < fcx: dx = -dx
                dy = 0
            else:
                dy = oy + MARGIN
                if mcy < fcy: dy = -dy
                dx = 0
            old = placements[mv]
            nx = max(1.5, min(98.5, old[0] + dx))
            ny = max(1.5, min(98.5, old[1] + dy))
            placements[mv] = (nx, ny, old[2], old[3])
            moved.add(mv)
        save_dict(placements)
        # Re-run place_board to apply
        import subprocess
        subprocess.run(["python3", "hardware/kicad/setup_board.py"], capture_output=True)
        subprocess.run(["python3", "hardware/kicad/scripts/place_board.py"], capture_output=True)
    print(f"Final: {len(get_overlaps())} overlaps")

if __name__ == "__main__":
    main()
