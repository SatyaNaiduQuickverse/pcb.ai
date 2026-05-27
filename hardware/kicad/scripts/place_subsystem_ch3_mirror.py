#!/usr/bin/env python3
"""place_subsystem_ch3_mirror.py — Phase 4-v2 Step 2 CH3 = mirror_Y(CH2).

Per master 2026-05-24 + R19 + L9 4-tier match cascade.

CH3 zone (SE): (65, 18, 100, 50) = mirror_Y(CH2 zone NE 65, 50, 100, 82) about Y=50.

For each CH3 component, find CH2 partner via:
  1. IC partner ref-list (Q11→Q17, J28→J38, U5→U7, etc.)
  2. EXACT net-set match (strip N$) + same ref-prefix letter
  3. Geometric-position fallback within 2mm

Apply: SetPosition((CH2.x, 100 - CH2.y)) + SetOrientationDegrees((180 - ch2_orient) % 360)
"""
import math
import sys
import re
from pathlib import Path
import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from place_subsystem_ch1_v3 import reset_text_to_body

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
BOARD_CENTER_Y = 50.0

# CH2 → CH3 IC partner mapping (per schematic). Based on prior session info:
# CH3: Q17-Q22 + J38 + J39 + J40-42 + U7 + U8
IC_PARTNERS = {
    'Q11': 'Q17', 'Q12': 'Q18',
    'Q13': 'Q19', 'Q14': 'Q20',
    'Q15': 'Q21', 'Q16': 'Q22',
    'J28': 'J38', 'J29': 'J39',
    'J30': 'J40', 'J31': 'J41', 'J32': 'J42',
    'U5': 'U7', 'U6': 'U8',
    'TP26': 'TP33', 'TP27': 'TP34', 'TP28': 'TP35',
}


def get_ch3_refs(board, zone):
    refs = set(IC_PARTNERS.values())
    zx0, zy0, zx1, zy1 = zone
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith('H') or ref.startswith('FID'): continue
        if ref in refs: continue
        if any(re.search(r'_CH3(_|$)', pad.GetNetname() or '') for pad in fp.Pads()):
            refs.add(ref); continue
        p = fp.GetPosition()
        x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
        if zx0 <= x <= zx1 and zy0 <= y <= zy1:
            refs.add(ref)
    return refs


def main():
    board = pcbnew.LoadBoard(PCB)
    zone = (65.0, 18.0, 100.0, 50.0)
    ch3_refs = get_ch3_refs(board, zone)
    print(f"CH3 components: {len(ch3_refs)}")

    def ch3_to_ch2_net(net):
        return re.sub(r'_CH3(_|$)', r'_CH2\1', net)
    def is_anon(n):
        return n.startswith('N$') or n == ''
    def strip_anon(sig):
        return frozenset(n for n in sig if not is_anon(n))

    ch2_by_sig = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in ch3_refs: continue
        sig = strip_anon(set(pad.GetNetname() or '' for pad in fp.Pads()))
        if any('_CH2' in n for n in sig):
            ch2_by_sig.setdefault(sig, []).append(fp)

    moved = 0
    failed = []
    for ref in sorted(ch3_refs):
        fp = board.FindFootprintByReference(ref)
        if fp is None: continue
        # IC mapping
        partner = None
        for ch2_r, ch3_r in IC_PARTNERS.items():
            if ch3_r == ref:
                partner = board.FindFootprintByReference(ch2_r); break
        # Net-sig match
        if partner is None:
            ch3_set = strip_anon({ch3_to_ch2_net(pad.GetNetname() or '') for pad in fp.Pads()})
            ch3_letter = ''.join(c for c in ref if not c.isdigit())
            for sig, fps in ch2_by_sig.items():
                if sig == ch3_set and len(ch3_set) > 0:
                    for f in fps:
                        cletter = ''.join(c for c in f.GetReference() if not c.isdigit())
                        if cletter == ch3_letter:
                            partner = f; break
                if partner: break
        # Geometric fallback
        if partner is None:
            ch3_cur_y = pcbnew.ToMM(fp.GetPosition().y)
            ch3_cur_x = pcbnew.ToMM(fp.GetPosition().x)
            expected_ch2_y = 2 * BOARD_CENTER_Y - ch3_cur_y
            ch3_letter = ''.join(c for c in ref if not c.isdigit())
            best = None; best_d = 2.0
            for cand_fp in board.GetFootprints():
                cref = cand_fp.GetReference()
                if cref == ref: continue
                cletter = ''.join(c for c in cref if not c.isdigit())
                if cletter != ch3_letter: continue
                cp = cand_fp.GetPosition()
                cx, cy = pcbnew.ToMM(cp.x), pcbnew.ToMM(cp.y)
                if cy >= 50: continue   # CH2 side y > 50
                # Wait — CH2 is at y=50-82 (north), CH3 south y=18-50; expected partner at y>50
                # Fix: CH2 has y >= 50
            best_d = 2.0; best = None
            for cand_fp in board.GetFootprints():
                cref = cand_fp.GetReference()
                if cref == ref: continue
                cletter = ''.join(c for c in cref if not c.isdigit())
                if cletter != ch3_letter: continue
                cp = cand_fp.GetPosition()
                cx, cy = pcbnew.ToMM(cp.x), pcbnew.ToMM(cp.y)
                if cy < 50: continue
                d = math.hypot(ch3_cur_x - cx, expected_ch2_y - cy)
                if d < best_d:
                    best = cand_fp; best_d = d
            partner = best
        if partner is None:
            failed.append(ref); continue

        p = partner.GetPosition()
        new_x = pcbnew.ToMM(p.x)
        new_y = 2 * BOARD_CENTER_Y - pcbnew.ToMM(p.y)
        fp.SetPosition(pcbnew.VECTOR2I(int(new_x * 1e6), int(new_y * 1e6)))
        # Y-mirror: orient inverts vertical component → new = -orig
        orig = partner.GetOrientation().AsDegrees()
        fp.SetOrientationDegrees((-orig) % 360)
        # Layer inheritance — see CH2 mirror script. R23 symmetry + §8 #9 shunt
        # overlap require the CH3 partner to live on the same layer as its CH2
        # source (B.Cu for shunts R129/R130/R131).
        if fp.IsFlipped() != partner.IsFlipped():
            fp.Flip(fp.GetPosition(), False)
        reset_text_to_body(fp)
        moved += 1

    print(f"CH3 mirrored: {moved}/{len(ch3_refs)}")
    if failed:
        print(f"Failed ({len(failed)}): {failed[:10]}")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
