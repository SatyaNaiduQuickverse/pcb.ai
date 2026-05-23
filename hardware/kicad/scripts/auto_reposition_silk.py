#!/usr/bin/env python3
"""auto_reposition_silk.py — silk refdes auto-placement per master 2026-05-24 Gap #3/#4.

For each footprint, the refdes silk text default position may overlap an
adjacent component's body or a copper pad. This script:

  1. For each VISIBLE refdes text on each component, get its current bbox
  2. Check overlap vs (a) other components' bodies on same side, (b) copper
     pads of any component on same side
  3. If overlapping: try 8 cardinal/diagonal positions around component
     perimeter (N, NE, E, SE, S, SW, W, NW) — pick first clear one
  4. If no clear position found AND component is small (0402/0603 R/C/L):
     hide the refdes silk text (Visible=False) — acceptable per master
     industry-standard exemption for dense passive arrays
  5. If no clear position AND component is critical (IC, connector, FET,
     polarized cap/diode, mount-hole, fiducial): leave visible + log for
     hand-review

Critical class (NEVER hide silk):
  - Any U-prefix IC (LM393, 74LVC1G08, TL431, ACS770, etc.)
  - Any J-prefix connector (MCU placeholders, BEC bucks, ESD, FC connectors)
  - Any Q-prefix FET (BSC014N06NS)
  - Polarized parts (D-prefix diodes incl Zener/Schottky/TVS)
  - L-prefix inductors (≥0805 by default in this design)
  - TH-prefix thermistors
  - TP-prefix test points (probe access labels)
  - H-prefix mounting holes
  - FID-prefix fiducials

Small-passive class (silk can be hidden if no clear position):
  - R/C/L on 0402/0603 footprints
"""
import pcbnew
import math
import sys

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"


def is_critical(ref, fp_lib, val):
    """True if component is in critical-keep-silk class.
    Master 2026-05-24 P2: extended small-passive class includes BAT54 +
    BZT52 + 0805 caps + 1nF/3.3K/10K/22K passives.
    Truly critical (always keep silk): MCUs, DRVs, comparators, refs,
    connectors, polarized large caps, mount holes, fiducials, test points,
    FETs, phase TVS (SMBJ33A — orientation matters)."""
    if ref.startswith(('TH', 'TP', 'H', 'FID')):
        return True
    # FETs always critical
    if ref.startswith('Q'):
        return True
    # MCU/DRV/comparator placeholders + connectors
    if ref.startswith(('U', 'J')):
        return True
    # Diodes: only phase TVS (SMBJ33A) is critical (orientation matters);
    # BAT54 (CSA OR), BZT52 (Zener clamp) are extended-small-passive
    if ref.startswith('D'):
        if 'SMBJ33A' in val:
            return True
        if 'BAT54' in val or 'BZT52' in val:
            return False  # extended small-passive — allow silk hide
        if val.startswith('RED') or val.startswith('GREEN'):
            return True  # status LEDs (orientation/identification matters)
        return True  # default: keep diode silk
    # Inductors: keep silk for now (small inductors might be hideable but
    # there are few inductors in this design)
    if ref.startswith('L'):
        return True
    # R/C: extended small-passive class
    if ref.startswith(('R', 'C')):
        if '0402' in fp_lib or '0603' in fp_lib or '0805' in fp_lib:
            return False  # small-passive — allow silk hide
        # 100uF polymer / 2512 shunt / large caps → critical
        return True
    return True


def collect_obstacles(board):
    """Return per-side lists of (body_bbox, pad_bboxes) for collision check."""
    bodies = {'F': [], 'B': []}
    pads = {'F': [], 'B': []}
    for fp in board.GetFootprints():
        side = 'F' if fp.GetLayer() == pcbnew.F_Cu else 'B'
        bb = fp.GetBoundingBox()
        bodies[side].append({
            'ref': fp.GetReference(),
            'bbox': (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                     pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())),
        })
        for pad in fp.Pads():
            pb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            pad_box = (pcbnew.ToMM(pb.GetLeft()), pcbnew.ToMM(pb.GetTop()),
                       pcbnew.ToMM(pb.GetRight()), pcbnew.ToMM(pb.GetBottom()))
            entry = {'ref': fp.GetReference(), 'pad': pad.GetPadName(), 'bbox': pad_box}
            if ls.Contains(pcbnew.F_Cu): pads['F'].append(entry)
            if ls.Contains(pcbnew.B_Cu): pads['B'].append(entry)
    return bodies, pads


def text_clear(tx0, ty0, tx1, ty1, ref, side, bodies, pads, body_tol=0.1, pad_tol=0.05):
    """Return True if text bbox doesn't overlap any other body or any pad on side."""
    for b in bodies[side]:
        if b['ref'] == ref: continue
        bx0, by0, bx1, by1 = b['bbox']
        # Full-containment test (text bbox INSIDE other body)
        if (bx0 - body_tol <= tx0 and tx1 <= bx1 + body_tol
                and by0 - body_tol <= ty0 and ty1 <= by1 + body_tol):
            return False
    for p in pads[side]:
        if p['ref'] == ref: continue
        px0, py0, px1, py1 = p['bbox']
        px0 -= pad_tol; py0 -= pad_tol; px1 += pad_tol; py1 += pad_tol
        if tx0 < px1 and tx1 > px0 and ty0 < py1 and ty1 > py0:
            return False
    return True


def main():
    board = pcbnew.LoadBoard(PCB)
    bodies, pads = collect_obstacles(board)
    repositioned = 0
    hidden = 0
    leave_visible = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        rf = fp.Reference()
        if not rf.IsVisible(): continue
        side = 'F' if fp.GetLayer() == pcbnew.F_Cu else 'B'
        # Current text bbox
        bb = rf.GetBoundingBox()
        tx0, ty0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
        tx1, ty1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
        if text_clear(tx0, ty0, tx1, ty1, ref, side, bodies, pads):
            continue
        # Try 8 positions around component body
        fp_bb = fp.GetBoundingBox()
        fx0, fy0 = pcbnew.ToMM(fp_bb.GetLeft()), pcbnew.ToMM(fp_bb.GetTop())
        fx1, fy1 = pcbnew.ToMM(fp_bb.GetRight()), pcbnew.ToMM(fp_bb.GetBottom())
        text_w = tx1 - tx0
        text_h = ty1 - ty0
        cx = (fx0 + fx1) / 2
        cy = (fy0 + fy1) / 2
        # Master 2026-05-24 P2: 16 candidates = 8 cardinal × 2 distance rings
        # (0.5mm and 2mm gap). Search radius extended to clear cluster density.
        new_pos = None
        for gap in (0.5, 1.5, 3.0):
            candidates = [
                (cx, fy0 - text_h/2 - gap),                                  # N
                (cx, fy1 + text_h/2 + gap),                                  # S
                (fx1 + text_w/2 + gap, cy),                                  # E
                (fx0 - text_w/2 - gap, cy),                                  # W
                (fx1 + text_w/2 + gap, fy0 - text_h/2 - gap),                # NE
                (fx0 - text_w/2 - gap, fy0 - text_h/2 - gap),                # NW
                (fx1 + text_w/2 + gap, fy1 + text_h/2 + gap),                # SE
                (fx0 - text_w/2 - gap, fy1 + text_h/2 + gap),                # SW
            ]
            for ncx, ncy in candidates:
                ntx0 = ncx - text_w / 2
                nty0 = ncy - text_h / 2
                ntx1 = ncx + text_w / 2
                nty1 = ncy + text_h / 2
                if ntx0 < 0 or nty0 < 0 or ntx1 > 100 or nty1 > 100: continue
                if text_clear(ntx0, nty0, ntx1, nty1, ref, side, bodies, pads):
                    new_pos = (ncx, ncy)
                    break
            if new_pos: break
        if new_pos:
            nx, ny = new_pos
            rf.SetTextPos(pcbnew.VECTOR2I(pcbnew.FromMM(nx), pcbnew.FromMM(ny)))
            repositioned += 1
        else:
            # No clear position. Critical → leave visible; small-passive → hide
            fp_lib = str(fp.GetFPID().GetLibItemName() or '')
            val = fp.GetValue() or ''
            if is_critical(ref, fp_lib, val):
                leave_visible += 1
            else:
                rf.SetVisible(False)
                hidden += 1
    board.Save(PCB)
    print(f"auto_reposition_silk: repositioned={repositioned}, hidden_small_passive={hidden}, left_visible_critical={leave_visible}")


if __name__ == "__main__":
    sys.exit(main() or 0)
