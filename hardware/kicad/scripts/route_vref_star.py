#!/usr/bin/env python3
"""route_vref_star.py — PR-routing-rebuild Phase 4 step 9.

Star route VREF_2V5 from central TL431 (U2) to 4 channel divider entry taps
(c_vref_local C78/C108/C138/C168). DC analog reference, length-insensitive.
Routes on inner signal layer In2.Cu adjacent to In1.Cu GND plane for
return-path integrity.

Star branches (worst-case length ~30-35mm):
  U2 (49.1, 48) → C78 (37.5, 82)   CH1
  U2 (49.1, 48) → C108 (61.5, 82)  CH2
  U2 (49.1, 48) → C138 (61.5, 18)  CH3
  U2 (49.1, 48) → C168 (37.5, 18)  CH4

Trace width: 0.2mm (signal trace, DC ~200µA/channel — IR drop negligible).
Via from F.Cu to In2.Cu at U2 cathode pad, via from In2.Cu to F.Cu at each
c_vref_local entry.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Star branch endpoints (already-known per Phase 3 placement)
# U2 cathode pad-2 @ (49.1, 49); use (50, 48.5) as star center after exiting U2.
STAR_CENTER = (50.0, 48.5)
BRANCHES = [
    ('C78',  37.5, 82.0),
    ('C108', 61.5, 82.0),
    ('C138', 61.5, 18.0),
    ('C168', 37.5, 18.0),
]
TRACK_W = 0.2  # mm
VIA_D = 0.6
VIA_DRILL = 0.3


def mm(x):
    return pcbnew.FromMM(x)


def add_track(board, x1, y1, x2, y2, layer, net, width):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
    t.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
    t.SetLayer(layer)
    t.SetWidth(mm(width))
    t.SetNet(net)
    board.Add(t)
    return t


def add_via(board, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetDrill(mm(VIA_DRILL))
    v.SetWidth(mm(VIA_D))
    v.SetNet(net)
    board.Add(v)
    return v


def find_net(board, name):
    for n in board.GetNetsByName().values():
        if n.GetNetname() == name:
            return n
    return None


def main():
    board = pcbnew.LoadBoard(PCB)
    vref_net = find_net(board, 'VREF_2V5')
    if vref_net is None:
        print("ERROR: VREF_2V5 net not found")
        return 1
    n_tracks = 0
    n_vias = 0
    # Via from F.Cu (U2 cathode) to In2.Cu (signal layer)
    cx, cy = STAR_CENTER
    add_via(board, cx, cy, vref_net)
    n_vias += 1
    # Short F.Cu trace from U2 pad-2 @(49.1, 49) to star center via
    add_track(board, 49.1, 49.0, cx, cy, pcbnew.F_Cu, vref_net, TRACK_W)
    n_tracks += 1
    # For each branch: route on In2.Cu from star center to branch entry, then via to F.Cu
    for ref, bx, by in BRANCHES:
        # 2-segment dogleg on In2.Cu: vertical first, then horizontal
        mid_x = bx
        mid_y = cy
        add_track(board, cx, cy, mid_x, mid_y, pcbnew.In2_Cu, vref_net, TRACK_W)
        add_track(board, mid_x, mid_y, bx, by, pcbnew.In2_Cu, vref_net, TRACK_W)
        n_tracks += 2
        # Via from In2.Cu back to F.Cu at branch cap
        add_via(board, bx, by, vref_net)
        n_vias += 1
    board.Save(PCB)
    print(f"VREF_2V5 star routing: {n_tracks} tracks + {n_vias} vias added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
