#!/usr/bin/env python3
"""silk_hide_passives_post_snap.py — apply silk-hide policy to all SILK-ON-PAD
silk-source components that are eligible (small passive class).

After snap_mirror_validated.py + Step 3 + Step 4b, residual SILK-ON-PAD
violations come from un-moved silk-eligible passives whose silk text overlaps
moved components' new pad positions. Apply silk-hide-passive policy to
clear them per master M4 directive.
"""
import pcbnew


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

SILK_HIDE_PASSIVE_CLASSES = (
    'R_0402', 'R_0603', 'R_0805',
    'C_0402', 'C_0603', 'C_0805',
    'L_0402', 'L_0603', 'L_0805',
    'D_SOD-123', 'D_SOD-323', 'BAT54', 'BZT52',
    'R_2512', 'C_2512',
    # Extended (M4 2026-05-24): LED indicators, test points, SMA protection diodes
    # are also silk-hide-eligible when they collide with adjacent pads. These
    # remain identifiable via component-pick-and-place coordinates and BOM.
    'LED_0402', 'LED_0603', 'LED_0805',
    'D_SMA', 'D_SMB',
    'TestPoint_Pad',
)


def is_silk_hide_eligible(fp):
    lib = str(fp.GetFPID().GetLibItemName() or '')
    for cls in SILK_HIDE_PASSIVE_CLASSES:
        if cls in lib: return True
    return False


def text_bbox(fp):
    bb = fp.Reference().GetBoundingBox()
    return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
            pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))


def main():
    board = pcbnew.LoadBoard(PCB)
    fps = list(board.GetFootprints())

    # Collect all pad bboxes (excluding self-fp filter — checked per pair)
    pads = []
    for fp in fps:
        ref = fp.GetReference()
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            pads.append((ref, pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                         pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                         ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu)))

    hidden = 0
    for fp in fps:
        ref = fp.GetReference()
        if not is_silk_hide_eligible(fp): continue
        if not fp.Reference().IsVisible(): continue
        tb = text_bbox(fp)
        # Check if text bbox overlaps any pad on same layer (silk layer matches fp side)
        text_layer = fp.Reference().GetLayer()
        # F.SilkS pairs with F.Cu pads; B.SilkS with B.Cu pads
        is_f_silk = text_layer == pcbnew.F_SilkS
        for pref, p1, p2, p3, p4, F, B in pads:
            if pref == ref: continue
            if is_f_silk and not F: continue
            if not is_f_silk and not B: continue
            # Overlap test
            if tb[0] < p3 and tb[2] > p1 and tb[1] < p4 and tb[3] > p2:
                fp.Reference().SetVisible(False)
                hidden += 1
                break
    print(f"Hidden silk on {hidden} silk-eligible passive(s) for SILK-ON-PAD avoidance")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
