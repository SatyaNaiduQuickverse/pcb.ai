#!/usr/bin/env python3
"""move_critical_silk_text.py — Step 4c v2 (master M4 2026-05-24).

For critical-class components where silk text lands on pads after relocations:
search for a pad-clear silk text position near the body. Don't hide silk
(critical class per master Q1).
"""
import pcbnew
import math


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Refs whose silk text needs moving (any critical-class with SILK-ON-PAD)
CRITICAL_REFS = ['C4', 'J27', 'Q15', 'Q16', 'Q20', 'Q21', 'Q23', 'Q26']


def main():
    board = pcbnew.LoadBoard(PCB)
    fps = {f.GetReference(): f for f in board.GetFootprints()}

    # Collect all pad bboxes on F.Cu and B.Cu
    pads = []
    for fp in fps.values():
        ref = fp.GetReference()
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            pads.append((ref, pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                          pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                          ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu)))

    def text_clear(ref, tx, ty, text_w=2.5, text_h=1.6, fp_layer=pcbnew.F_Cu):
        """Check if a text bbox at (tx, ty) overlaps any other-fp pad on same side."""
        is_f = fp_layer == pcbnew.F_Cu
        for (pref, x1, y1, x2, y2, F, B) in pads:
            if pref == ref: continue
            if is_f and not F: continue
            if not is_f and not B: continue
            if tx-text_w/2 < x2 and tx+text_w/2 > x1 and ty-text_h/2 < y2 and ty+text_h/2 > y1:
                return False
        return True

    for ref in CRITICAL_REFS:
        fp = fps.get(ref)
        if not fp: continue
        pos = fp.GetPosition()
        cx = pcbnew.ToMM(pos.x); cy = pcbnew.ToMM(pos.y)
        layer = fp.GetLayer()
        # Search for clear silk text position
        # Try cardinal + diagonal at increasing radii
        chosen = None
        for r in (3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0):
            for ai in range(16):
                theta = 2 * math.pi * ai / 16
                tx = cx + r * math.cos(theta)
                ty = cy + r * math.sin(theta)
                if tx < 2 or tx > 98 or ty < 2 or ty > 98: continue
                if text_clear(ref, tx, ty, fp_layer=layer):
                    chosen = (tx, ty, r)
                    break
            if chosen: break
        if chosen:
            tx, ty, r = chosen
            fp.Reference().SetPosition(pcbnew.VECTOR2I(int(tx*1e6), int(ty*1e6)))
            print(f"  {ref}: silk text → ({tx:.2f}, {ty:.2f}) (r={r:.1f}mm)")
        else:
            print(f"  {ref}: NO clear silk position found")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
