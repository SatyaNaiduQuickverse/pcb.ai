#!/usr/bin/env python3
"""route_power_plane_stitch.py — PR-routing-power-stitch (master 2026-05-24 G2 Phase A).

Adds plane-stitch vias for unconnected power-net pads + refreshes zone copper
so KiCad sees pad → trace → via → plane → connected.

Critical sequence (the bit my earlier attempt missed):
  1. Add via at pad center on F.Cu→B.Cu layer pair
  2. Add small same-layer stub trace from pad center to via center (if offset)
  3. After all vias added: pcbnew.ZONE_FILLER(board).Fill(zones)
     This refreshes the inner plane copper to include the new vias' net
  4. board.GetConnectivity().RecalculateRatsnest() — updates unconnected count

Power nets handled by inner planes:
  - GND, BATGND   → In1.Cu + In5.Cu (dual GND plane)
  - +VMOTOR       → In3.Cu

Power nets WITHOUT plane (left for Phase B/C signal routing):
  - +3V3, +3V3A, +5V, +V5_FC, +V5_PI5, +V5_AI, +V9_VTX1, +V9_VTX2

This Phase A handles the 138 GND + 18 BATGND + 26 +VMOTOR = 182 pads with
dedicated planes. Remaining ~117 power-net pads (+3V3 etc.) need explicit
trace routing in subsequent PR.

Idempotent — uses 'via already at pad' detection to skip already-routed pads.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Power nets with dedicated inner plane
PLANE_NETS = {'GND', 'BATGND', '+VMOTOR'}

VIA_DIA = 0.6
VIA_DRILL = 0.3
STUB_W = 0.3
VIA_PAD_TOL = 0.2  # treat via within 0.2mm of pad center as 'already there'


def pad_has_existing_via(board, pad_x, pad_y, net_name, tol=VIA_PAD_TOL):
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetNetname() != net_name:
            continue
        p = t.GetPosition()
        if (abs(pcbnew.ToMM(p.x) - pad_x) < tol
                and abs(pcbnew.ToMM(p.y) - pad_y) < tol):
            return True
    return False


def add_via(board, x_mm, y_mm, net_obj):
    v = pcbnew.PCB_VIA(board)
    # SetLayerPair MUST come before SetWidth (pcbnew 9.x requires layer context)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
    v.SetDrill(pcbnew.FromMM(VIA_DRILL))
    v.SetWidth(pcbnew.FromMM(VIA_DIA))
    v.SetNet(net_obj)
    board.Add(v)


def main():
    board = pcbnew.LoadBoard(PCB)
    pre_vias = sum(1 for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA))

    added = {'GND': 0, 'BATGND': 0, '+VMOTOR': 0}
    skipped = 0

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net_obj = pad.GetNet()
            if net_obj is None:
                continue
            net_name = net_obj.GetNetname()
            if net_name not in PLANE_NETS:
                continue
            # Only SMD pads need explicit via (THT pads already span layers)
            if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH,
                                       pcbnew.PAD_ATTRIB_NPTH):
                continue
            p = pad.GetPosition()
            px = pcbnew.ToMM(p.x)
            py = pcbnew.ToMM(p.y)
            # Skip if pad already has a via on same net at same position
            if pad_has_existing_via(board, px, py, net_name):
                skipped += 1
                continue
            # Add via at exact pad center (via lands on pad copper directly)
            add_via(board, px, py, net_obj)
            added[net_name] += 1

    # Refresh zone fills to incorporate new vias
    print(f"Vias added: GND={added['GND']}, BATGND={added['BATGND']}, "
          f"+VMOTOR={added['+VMOTOR']}, skipped(existing)={skipped}")
    # SAVE FIRST before zone-fill in case the latter segfaults
    print("Saving board (vias)...")
    board.Save(PCB)
    print("Reload + refresh zone fills...")
    board = pcbnew.LoadBoard(PCB)
    zones = [z for z in board.Zones()]
    print(f"  {len(zones)} zones to refresh")
    try:
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(zones)
        print("Zones filled. Saving...")
        board.Save(PCB)
        print("Saved.")
    except Exception as e:
        print(f"Zone fill ERROR: {e}")
    try:
        board.GetConnectivity().RecalculateRatsnest()
    except Exception as e:
        print(f"Ratsnest ERROR: {e}")
    post_vias = sum(1 for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA))
    print(f"\nVias before: {pre_vias}, after: {post_vias}")


if __name__ == "__main__":
    main()
