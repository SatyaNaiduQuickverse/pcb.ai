#!/usr/bin/env python3
"""fix_u1_hall_footprint.py — PR-A4-integrate Defect 1 fix.

KiCad's Sensor_Current:Allegro_CB_PFF library footprint is wrong for
ACS770ECB-200B (its own description says "!PADS 4-5 DO NOT MATCH DATASHEET!").
The library geometry represents ACS758-LCB-PFF (through-PCB edge-mount with
current bar 21mm offset from IC body) — our part is ACS770ECB-200B PFF which
is fully SMT with current tabs ADJACENT to body.

Per ACS770ECB-200B datasheet (Allegro):
  - Body overall: ~12.7 × 8.5mm
  - Signal pads 1,2,3 on one short edge, 1.27mm pitch
  - Current tabs 4,5 on opposite short edge, ~5.5 × 4.5mm each
  - Tab-to-tab gap: ~1.2mm
  - Pad 1 is reference origin

In-place fix: rebuild U1's pads to correct geometry. Footprint identity
stays as Allegro_CB_PFF (library binding preserved), but pad placements
are corrected to match the actual ACS770 part.

Master directive 2026-05-23 (Defect 1 fix before B-1 resume).
"""
import pcbnew

PCB = "hardware/kicad/pcbai_fpv4in1.kicad_pcb"


def main():
    board = pcbnew.LoadBoard(PCB)
    u1 = None
    for fp in board.GetFootprints():
        if fp.GetReference() == "U1":
            u1 = fp
            break
    if u1 is None:
        raise SystemExit("U1 not found")

    fp_pos = u1.GetPosition()
    fp_rot = u1.GetOrientationDegrees()
    fp_layer = u1.GetLayer()
    print(f"U1 current: pos=({pcbnew.ToMM(fp_pos.x):.2f}, {pcbnew.ToMM(fp_pos.y):.2f}) rot={fp_rot}")

    # Collect net assignments before deleting pads (preserve by pad number)
    net_by_padnum = {}
    for pad in u1.Pads():
        n = pad.GetNumber()
        net = pad.GetNet()
        if net and net.GetNetname() and n not in net_by_padnum:
            net_by_padnum[n] = net
    print(f"Captured nets: {[(n, net.GetNetname()) for n, net in net_by_padnum.items()]}")

    # Remove all existing pads
    pads_to_remove = list(u1.Pads())
    n_removed = 0
    for pad in pads_to_remove:
        u1.Remove(pad)
        n_removed += 1
    print(f"Removed {n_removed} old pads from U1")

    # Rebuild pads per ACS770ECB-200B datasheet (rot=0 reference frame).
    # Origin = pad 1 center.
    # Signal pads 1/2/3 at +Y row (1.27mm pitch), pads 1.27 × 1.6mm each.
    # Current tabs 4/5 at -Y row, each 5.5 × 4.5mm, gap 1.2mm.
    # Layout (rot=0, pad-1-origin frame):
    #   Pad 1 (VCC):    ( 0.00,  0.00)  1.27 × 1.6mm  pad 1
    #   Pad 2 (GND):    ( 1.27,  0.00)  1.27 × 1.6mm  pad 2
    #   Pad 3 (VIOUT):  ( 2.54,  0.00)  1.27 × 1.6mm  pad 3
    #   Pad 4 (IP+):    (-2.30, -7.50)  5.50 × 4.5mm  pad 4 (south-west)
    #   Pad 5 (IP-):    ( 4.84, -7.50)  5.50 × 4.5mm  pad 5 (south-east)
    # IC body extends from approx (-2.5, -8.5) to (5.0, 0.8).

    new_pad_specs = [
        # (number, local_x_mm, local_y_mm, size_x_mm, size_y_mm)
        ("1",  0.00,  0.00, 1.27, 1.6),
        ("2",  1.27,  0.00, 1.27, 1.6),
        ("3",  2.54,  0.00, 1.27, 1.6),
        ("4", -2.30, -7.50, 5.50, 4.5),
        ("5",  4.84, -7.50, 5.50, 4.5),
    ]

    for num, lx, ly, sx, sy in new_pad_specs:
        pad = pcbnew.PAD(u1)
        pad.SetNumber(num)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(sx), pcbnew.FromMM(sy)))
        # FP-relative position — KiCad applies fp rotation to convert to absolute
        pad.SetFPRelativePosition(pcbnew.VECTOR2I(pcbnew.FromMM(lx), pcbnew.FromMM(ly)))
        # F.Cu + F.Mask + F.Paste
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        ls.AddLayer(pcbnew.F_Mask)
        ls.AddLayer(pcbnew.F_Paste)
        pad.SetLayerSet(ls)
        if num in net_by_padnum:
            pad.SetNet(net_by_padnum[num])
        u1.Add(pad)

    # Re-apply position/orientation so Pos0 → absolute coords land correctly
    u1.SetPosition(fp_pos)
    u1.SetOrientationDegrees(fp_rot)
    print(f"Added {len(new_pad_specs)} new pads at correct ACS770 geometry")

    # Verify new pad positions
    print("New pad absolute positions:")
    for pad in u1.Pads():
        pos = pad.GetPosition()
        bb = pad.GetBoundingBox()
        print(f"  pad {pad.GetNumber()!r}: center=({pcbnew.ToMM(pos.x):.2f}, {pcbnew.ToMM(pos.y):.2f})  "
              f"bbox=({pcbnew.ToMM(bb.GetLeft()):.2f},{pcbnew.ToMM(bb.GetTop()):.2f})-"
              f"({pcbnew.ToMM(bb.GetRight()):.2f},{pcbnew.ToMM(bb.GetBottom()):.2f})  "
              f"net='{pad.GetNet().GetNetname()}'")

    new_bb = u1.GetBoundingBox()
    print(f"U1 new bbox: {pcbnew.ToMM(new_bb.GetWidth()):.2f} × {pcbnew.ToMM(new_bb.GetHeight()):.2f}mm")

    board.Save(PCB)
    print(f"Saved {PCB}")


if __name__ == "__main__":
    main()
