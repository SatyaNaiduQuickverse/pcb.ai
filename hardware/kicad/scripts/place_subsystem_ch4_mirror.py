#!/usr/bin/env python3
"""place_subsystem_ch4_mirror.py — Phase 4-v2 Step 2 CH4 = mirror_X(CH3).

Per master 2026-05-24 + R19 + L9 4-tier match cascade.

CH4 zone (SW): (0, 18, 35, 50) = mirror_X(CH3 zone SE 65, 18, 100, 50) about X=50.
"""
import math, sys, re
from pathlib import Path
import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from place_subsystem_ch1_v3 import reset_text_to_body

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
BOARD_CENTER_X = 50.0

IC_PARTNERS = {  # CH3 → CH4
    'Q17': 'Q23', 'Q18': 'Q24',
    'Q19': 'Q25', 'Q20': 'Q26',
    'Q21': 'Q27', 'Q22': 'Q28',
    'J38': 'J48', 'J39': 'J49',
    'J40': 'J50', 'J41': 'J51', 'J42': 'J52',
    'U7': 'U9', 'U8': 'U10',
    'TP33': 'TP40', 'TP34': 'TP41', 'TP35': 'TP42',
}


def get_ch4_refs(board, zone):
    refs = set(IC_PARTNERS.values())
    zx0, zy0, zx1, zy1 = zone
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith('H') or ref.startswith('FID'): continue
        if ref in refs: continue
        if any(re.search(r'_CH4(_|$)', pad.GetNetname() or '') for pad in fp.Pads()):
            refs.add(ref); continue
        p = fp.GetPosition()
        x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
        if zx0 <= x <= zx1 and zy0 <= y <= zy1:
            refs.add(ref)
    return refs


def main():
    board = pcbnew.LoadBoard(PCB)
    zone = (0.0, 18.0, 35.0, 50.0)
    ch4_refs = get_ch4_refs(board, zone)
    print(f"CH4 components: {len(ch4_refs)}")

    def ch4_to_ch3_net(net):
        return re.sub(r'_CH4(_|$)', r'_CH3\1', net)
    def is_anon(n):
        return n.startswith('N$') or n == ''
    def strip_anon(sig):
        return frozenset(n for n in sig if not is_anon(n))

    ch3_by_sig = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in ch4_refs: continue
        sig = strip_anon(set(pad.GetNetname() or '' for pad in fp.Pads()))
        if any('_CH3' in n for n in sig):
            ch3_by_sig.setdefault(sig, []).append(fp)

    moved, failed = 0, []
    for ref in sorted(ch4_refs):
        fp = board.FindFootprintByReference(ref)
        if fp is None: continue
        partner = None
        for ch3_r, ch4_r in IC_PARTNERS.items():
            if ch4_r == ref:
                partner = board.FindFootprintByReference(ch3_r); break
        if partner is None:
            ch4_set = strip_anon({ch4_to_ch3_net(pad.GetNetname() or '') for pad in fp.Pads()})
            ch4_letter = ''.join(c for c in ref if not c.isdigit())
            for sig, fps in ch3_by_sig.items():
                if sig == ch4_set and len(ch4_set) > 0:
                    for f in fps:
                        cletter = ''.join(c for c in f.GetReference() if not c.isdigit())
                        if cletter == ch4_letter:
                            partner = f; break
                if partner: break
        if partner is None:
            ch4_cur_x = pcbnew.ToMM(fp.GetPosition().x)
            ch4_cur_y = pcbnew.ToMM(fp.GetPosition().y)
            expected_ch3_x = 2 * BOARD_CENTER_X - ch4_cur_x
            ch4_letter = ''.join(c for c in ref if not c.isdigit())
            best = None; best_d = 2.0
            for cand_fp in board.GetFootprints():
                cref = cand_fp.GetReference()
                if cref == ref: continue
                cletter = ''.join(c for c in cref if not c.isdigit())
                if cletter != ch4_letter: continue
                cp = cand_fp.GetPosition()
                cx, cy = pcbnew.ToMM(cp.x), pcbnew.ToMM(cp.y)
                if cx < 50: continue
                d = math.hypot(expected_ch3_x - cx, ch4_cur_y - cy)
                if d < best_d:
                    best = cand_fp; best_d = d
            partner = best
        if partner is None:
            failed.append(ref); continue

        p = partner.GetPosition()
        new_x = 2 * BOARD_CENTER_X - pcbnew.ToMM(p.x)
        new_y = pcbnew.ToMM(p.y)
        fp.SetPosition(pcbnew.VECTOR2I(int(new_x * 1e6), int(new_y * 1e6)))
        orig_orient = partner.GetOrientation().AsDegrees()
        fp.SetOrientationDegrees((180 - orig_orient) % 360)
        reset_text_to_body(fp)
        moved += 1

    print(f"CH4 mirrored: {moved}/{len(ch4_refs)}")
    if failed:
        print(f"Failed ({len(failed)}): {failed[:10]}")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
