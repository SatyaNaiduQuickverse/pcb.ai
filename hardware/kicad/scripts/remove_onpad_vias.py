#!/usr/bin/env python3
"""remove_onpad_vias.py — delete on-pad vias on plane nets (Phase A leftover).

Per master 2026-05-24 O1 insight: on-pad vias don't actually route the pad —
they get absorbed by ZONE_FILLER or remain electrically isolated from pad.
Correct pattern is offset-via-with-stub-trace (separate script).

This is step 1 of the 2-step plane-stitch fix.
"""
import pcbnew
import math

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
PLANE_NETS = {'GND', 'BATGND', '+VMOTOR'}


def main():
    board = pcbnew.LoadBoard(PCB)
    # Collect pad positions per net
    pad_positions_by_net = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net_obj = pad.GetNet()
            if net_obj is None: continue
            n = net_obj.GetNetname()
            if n not in PLANE_NETS: continue
            if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH,
                                       pcbnew.PAD_ATTRIB_NPTH): continue
            p = pad.GetPosition()
            pad_positions_by_net.setdefault(n, []).append(
                (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))

    to_remove = []
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA): continue
        net = t.GetNetname()
        if net not in PLANE_NETS: continue
        p = t.GetPosition()
        vx = pcbnew.ToMM(p.x); vy = pcbnew.ToMM(p.y)
        for (px, py) in pad_positions_by_net.get(net, []):
            if math.hypot(vx - px, vy - py) < 0.3:
                to_remove.append(t)
                break

    for t in to_remove:
        board.Remove(t)
    board.Save(PCB)
    print(f"Removed {len(to_remove)} on-pad vias on plane nets")


if __name__ == "__main__":
    main()
