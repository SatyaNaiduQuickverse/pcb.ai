#!/usr/bin/env python3
"""route_ch1_bemf_complete.py — Ensure ALL CH1 BEMF pads are MST-connected.

For each BEMF_*_CH1 net, find all pads, build MST by Euclidean distance,
add L-shape on each pad's layer (F.Cu) for each MST edge. This gives a
COMPLETE CH1 BEMF that mirror_bemf_clean can faithfully reproduce on CH2/3/4.

Width: 0.15mm (signal).
"""
import pcbnew
import math
import re


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
W_MM = 0.15


def find_net(board, name):
    for n in board.GetNetsByName().values():
        if n.GetNetname() == name: return n
    return None


def main():
    b = pcbnew.LoadBoard(PCB)
    # For each BEMF_*_CH1 net, collect pads + build MST
    for nname, n in b.GetNetsByName().items():
        nm = str(nname)
        if not re.match(r'BEMF_[ABC]_CH1$', nm): continue
        net_obj = n
        # Find pads
        pads = []
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNet() is None: continue
                if pad.GetNet().GetNetCode() != n.GetNetCode(): continue
                p = pad.GetPosition()
                pads.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), pad.GetLayerSet()))
        if len(pads) < 2: continue
        # MST: connect 0 to all others by shortest
        used = {0}
        edges = []
        while len(used) < len(pads):
            best = None; best_d = 1e9
            for i in used:
                xi, yi, _ = pads[i]
                for j in range(len(pads)):
                    if j in used: continue
                    xj, yj, _ = pads[j]
                    d = math.hypot(xi-xj, yi-yj)
                    if d < best_d:
                        best_d = d; best = (i, j)
            if best is None: break
            i, j = best
            edges.append((i, j))
            used.add(j)
        # Add tracks
        for (i, j) in edges:
            xi, yi, li = pads[i]
            xj, yj, lj = pads[j]
            # L-shape on F.Cu
            t1 = pcbnew.PCB_TRACK(b)
            t1.SetStart(pcbnew.VECTOR2I(int(xi*1e6), int(yi*1e6)))
            t1.SetEnd(pcbnew.VECTOR2I(int(xi*1e6), int(yj*1e6)))
            t1.SetLayer(pcbnew.F_Cu)
            t1.SetWidth(pcbnew.FromMM(W_MM))
            t1.SetNet(net_obj)
            b.Add(t1)
            t2 = pcbnew.PCB_TRACK(b)
            t2.SetStart(pcbnew.VECTOR2I(int(xi*1e6), int(yj*1e6)))
            t2.SetEnd(pcbnew.VECTOR2I(int(xj*1e6), int(yj*1e6)))
            t2.SetLayer(pcbnew.F_Cu)
            t2.SetWidth(pcbnew.FromMM(W_MM))
            t2.SetNet(net_obj)
            b.Add(t2)
        print(f"  {nm}: MST edges={len(edges)} added")
    b.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
