#!/usr/bin/env python3
"""place_subsystem_ch2_mirror.py — Phase 4-v2 Step 2 CH2 placement.

Per master 2026-05-24 preference (b): CH2 = pure geometric mirror_X(CH1)
about board centerline X=50. No fudge per `feedback-symmetry-preserves-work`.

Algorithm:
  1. Load merged-PR-A pcbai_fpv4in1.kicad_pcb (CH1 in locked v3 positions)
  2. Build CH1 ref → CH2 ref mapping from net-suffix parallel
     (e.g., CH1: Q5 → CH2: Q11, MOTOR_A_CH1 ↔ MOTOR_A_CH2)
  3. For each CH2 component, set position = (100 - CH1.x, CH1.y)
  4. Mirror text positions identically
  5. Save

CH1 IC anchors (from PR-A locked):
  Q5/Q6 (12/30, 54), Q7/Q8 (12/30, 66), Q9/Q10 (12/30, 78)
  J18 (26, 72), J19 (22, 60), J20/21/22 (3, 54/66/78)
  U3 (17, 72), U4 (8, 70)

CH2 partners (mirror_X about X=50):
  Q11/Q12 (88/70, 54), Q13/Q14 (88/70, 66), Q15/Q16 (88/70, 78)
  J28 (74, 72), J29 (78, 60), J30/31/32 (97, 54/66/78)
  U5 (83, 72), U6 (92, 70)
"""
import math
import sys
import re
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from place_subsystem_ch1_v3 import reset_text_to_body

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
BOARD_CENTER_X = 50.0   # mm

# CH1 IC → CH2 IC mapping (per schematic naming convention)
IC_PARTNERS = {
    'Q5':  'Q11',  'Q6':  'Q12',
    'Q7':  'Q13',  'Q8':  'Q14',
    'Q9':  'Q15',  'Q10': 'Q16',
    'J18': 'J28',  'J19': 'J29',
    'J20': 'J30',  'J21': 'J31',  'J22': 'J32',
    'U3':  'U5',   'U4':  'U6',
    'TP19': 'TP26', 'TP20': 'TP27', 'TP21': 'TP28',
}


def get_ch2_refs(board, zone):
    """Identify CH2 components: IC partner list + _CH2 net suffix + physically
    in CH2 zone (x=65-100, y=50-82)."""
    refs = set(IC_PARTNERS.values())
    zx0, zy0, zx1, zy1 = zone
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith('H') or ref.startswith('FID'): continue
        if ref in refs: continue
        # _CH2 net suffix
        if any(re.search(r'_CH2(_|$)', pad.GetNetname() or '') for pad in fp.Pads()):
            refs.add(ref); continue
        # Physically in zone
        p = fp.GetPosition()
        x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
        if zx0 <= x <= zx1 and zy0 <= y <= zy1:
            refs.add(ref)
    return refs


def ch1_partner_ref(ch2_ref):
    """Find CH1 ref by inverting net suffix (_CH2 → _CH1) or IC mapping."""
    for ch1, ch2 in IC_PARTNERS.items():
        if ch2 == ch2_ref:
            return ch1
    # For passives: ref naming pattern doesn't carry suffix; use net-share
    return None


def main():
    board = pcbnew.LoadBoard(PCB)
    ch2_zone = (65.0, 50.0, 100.0, 82.0)
    ch2_refs = get_ch2_refs(board, ch2_zone)
    print(f"CH2 components: {len(ch2_refs)}")

    # Build net-share map: for each non-IC CH2 component, find CH1 partner by
    # comparing nets (cap C99 with MOTOR_A_CH2 ↔ cap C59 with MOTOR_A_CH1)
    def ch2_to_ch1_net(net):
        return re.sub(r'_CH2(_|$)', '_CH1', net)

    ch1_by_net_signature = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in ch2_refs: continue
        # Build a tuple of sorted unique non-power nets
        sig = tuple(sorted(set(pad.GetNetname() or '' for pad in fp.Pads())))
        if any('_CH1' in n for n in sig):
            ch1_by_net_signature.setdefault(sig, []).append(fp)

    def is_anon(n):
        return n.startswith('N$') or n == ''
    def strip_anon(sig):
        return tuple(n for n in sig if not is_anon(n))

    moved = 0
    failed = []
    skipped_non_ch_only = []
    for ref in sorted(ch2_refs):
        fp = board.FindFootprintByReference(ref)
        if fp is None: continue
        # IC mapping first
        partner_ref = ch1_partner_ref(ref)
        if partner_ref:
            partner = board.FindFootprintByReference(partner_ref)
        else:
            # Check: does this CH2 component actually have _CH2-suffixed nets?
            ch2_nets = [pad.GetNetname() or '' for pad in fp.Pads()]
            has_ch2 = any(re.search(r'_CH2(_|$)', n) for n in ch2_nets)
            if not has_ch2:
                # No CH suffix — cross-channel/global component, leave in place
                skipped_non_ch_only.append(ref)
                continue
            # Match by EXACT non-anon net set (R96 BEMF_A+MOTOR_A must match
            # CH1 BEMF_A+MOTOR_A, not any single-overlap CH1 fp)
            ch2_set = frozenset(strip_anon(sorted(set(
                ch2_to_ch1_net(pad.GetNetname() or '') for pad in fp.Pads()))))
            ch2_letter = ''.join(c for c in ref if not c.isdigit())
            candidates = []
            for sig, fps in ch1_by_net_signature.items():
                ch1_set = frozenset(strip_anon(sig))
                if ch1_set == ch2_set and len(ch2_set) > 0:
                    for f in fps:
                        cref = f.GetReference()
                        cletter = ''.join(c for c in cref if not c.isdigit())
                        if cletter == ch2_letter:
                            candidates.append(f)
            partner = candidates[0] if candidates else None
        if partner is None:
            # Ref-prefix neighborhood heuristic: find CH1 fp with same ref prefix
            # whose CURRENT XY is at mirror_X of THIS CH2 fp's current XY (within 5mm).
            # Catches N$-anonymous-net components where sig match fails.
            ch2_cur_x = pcbnew.ToMM(fp.GetPosition().x)
            ch2_cur_y = pcbnew.ToMM(fp.GetPosition().y)
            ch2_expected_ch1_x = 2 * BOARD_CENTER_X - ch2_cur_x
            ref_letter = ''.join(c for c in ref if not c.isdigit())
            best = None; best_d = 5.0
            for cand_fp in board.GetFootprints():
                cref = cand_fp.GetReference()
                if cref == ref: continue
                cletter = ''.join(c for c in cref if not c.isdigit())
                if cletter != ref_letter: continue
                # CH1 candidate must be on CH1 side (x < 50)
                cp = cand_fp.GetPosition()
                cx, cy = pcbnew.ToMM(cp.x), pcbnew.ToMM(cp.y)
                if cx >= 50: continue
                # match CH1 fp at expected mirror XY
                d = math.hypot(ch2_expected_ch1_x - cx, ch2_cur_y - cy)
                if d < best_d:
                    best = cand_fp; best_d = d
            if best is not None:
                partner = best
            else:
                failed.append(ref)
                continue
        p = partner.GetPosition()
        new_x = 2 * BOARD_CENTER_X - pcbnew.ToMM(p.x)
        new_y = pcbnew.ToMM(p.y)
        fp.SetPosition(pcbnew.VECTOR2I(int(new_x * 1e6), int(new_y * 1e6)))
        # Pure mirror about vertical X=50 axis: orientation flips horizontal
        # component (180 - orig). Vertical pads (90°/270°) unchanged.
        orig_orient = partner.GetOrientation().AsDegrees()
        fp.SetOrientationDegrees((180 - orig_orient) % 360)
        # Layer inheritance: CH2 partner MUST live on the same layer as its CH1
        # source (R23 symmetry + §8 #9 shunt-overlap require same-layer pair).
        # Without this, CH1 R57 on B.Cu would still leave CH2 R93 on F.Cu after
        # mirror (audit bbox-XY is layer-blind, so passes — but R23/G_SHUNT
        # intent is for shunt-FET copper merge, not cross-layer via-only).
        if fp.IsFlipped() != partner.IsFlipped():
            fp.Flip(fp.GetPosition(), False)
        reset_text_to_body(fp)
        moved += 1
    if skipped_non_ch_only:
        print(f"Skipped {len(skipped_non_ch_only)} non-CH-suffixed components (left in place): {skipped_non_ch_only[:10]}")

    print(f"Mirrored CH2 components: {moved}/{len(ch2_refs)}")
    if failed:
        print(f"Failed mirror lookup ({len(failed)}): {failed[:10]}")
    board.Save(PCB)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
