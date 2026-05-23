#!/usr/bin/env python3
"""route_s2.py — Phase 5b Task #81b: §S2 bulk caps plane stitching.

Adds high-density stitching vias from bulk cap F.Cu pads to In3.Cu (VMOTOR)
and In1.Cu + In5.Cu (GND) inner planes. 4 vias per pad (pad bbox 4.4×2.5mm,
generous spacing for 100A burst current path).

S2 is plane-served (no inter-cap F.Cu tracks needed — the plane bus does
it). This PR only adds vias.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

VIA_DIA = 0.6
VIA_DRILL = 0.3


def mm_to_iu(x):
    return pcbnew.FromMM(x)


def add_via(board, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm_to_iu(x), mm_to_iu(y)))
    v.SetWidth(mm_to_iu(VIA_DIA))
    v.SetDrill(mm_to_iu(VIA_DRILL))
    v.SetTopLayer(pcbnew.F_Cu)
    v.SetBottomLayer(pcbnew.B_Cu)
    v.SetNet(net)
    board.Add(v)


def main():
    board = pcbnew.LoadBoard(PCB)
    NET_VMOTOR = board.GetNetInfo().GetNetItem("+VMOTOR")
    NET_GND = board.GetNetInfo().GetNetItem("GND")
    if not NET_VMOTOR or not NET_GND:
        print("Missing +VMOTOR or GND net")
        return 1

    # C1 (32.5, 28): pad 1 +VMOTOR bbox (26.1, 26.75)-(30.5, 29.25); pad 2 GND bbox (34.5, 26.75)-(38.9, 29.25)
    # C2 (75, 31): pad 1 bbox (68.6, 29.75)-(73.0, 32.25); pad 2 (77.0, 29.75)-(81.4, 32.25)
    # C3 (26, 44): pad 1 bbox (19.6, 42.75)-(24.0, 45.25); pad 2 (28.0, 42.75)-(32.4, 45.25)
    # C4 (71.5, 40.5): pad 1 bbox (65.1, 39.25)-(69.5, 41.75); pad 2 (73.5, 39.25)-(77.9, 41.75)
    # Each pad gets a 4-via grid inside its bbox.
    CAP_PADS = [
        # (pad bbox x1, y1, x2, y2, net)
        (26.1, 26.75, 30.5, 29.25, NET_VMOTOR),  # C1.1
        (34.5, 26.75, 38.9, 29.25, NET_GND),     # C1.2
        (68.6, 29.75, 73.0, 32.25, NET_VMOTOR),  # C2.1
        (77.0, 29.75, 81.4, 32.25, NET_GND),     # C2.2
        (19.6, 42.75, 24.0, 45.25, NET_VMOTOR),  # C3.1
        (28.0, 42.75, 32.4, 45.25, NET_GND),     # C3.2
        (65.1, 39.25, 69.5, 41.75, NET_VMOTOR),  # C4.1
        (73.5, 39.25, 77.9, 41.75, NET_GND),     # C4.2
    ]

    vias_added = 0
    for x1, y1, x2, y2, net in CAP_PADS:
        # 4-via grid: 0.7mm inset from each corner
        for dx, dy in ((0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)):
            cx = (x1 + x2) / 2 + dx
            cy = (y1 + y2) / 2 + dy
            # Skip if too close to existing via (S1 added 1 center via per pad)
            if abs(dx) < 0.5 and abs(dy) < 0.5:
                continue
            add_via(board, cx, cy, net)
            vias_added += 1

    board.Save(PCB)
    print(f"S2 routing: 0 tracks + {vias_added} plane stitching vias added")
    print(f"  4 bulk caps × 2 pads × 4 vias = {vias_added} total")
    print(f"Saved {PCB}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
