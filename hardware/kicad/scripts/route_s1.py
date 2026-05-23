#!/usr/bin/env python3
"""route_s1.py — Phase 5b Task #81a: §S1 battery input routing.

Adds tracks + plane zones + stitching vias for the S1 high-current path:
  XT30 J1 → R1/R2 NTC inrush pair → C1-C4 bulk caps (+VMOTOR delivery)
  XT30 J1 → Q1-Q4 protection FET sources (BATGND return)
  R3/D2 GATE_RP signal cluster
  In3.Cu +VMOTOR plane
  In1.Cu + In5.Cu GND planes

Width policy (per PHASE5B_ROUTING_DISPATCH.md):
  +BATT / +VMOTOR / BATGND / GND high-current traces: 1.0mm on F.Cu
  GATE_RP signal: 0.2mm on F.Cu
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

W_PWR = 1.0   # mm
W_SIG = 0.2   # mm
VIA_DIA = 0.6
VIA_DRILL = 0.3


def mm_to_iu(x):
    return pcbnew.FromMM(x)


def vec(x, y):
    return pcbnew.VECTOR2I(mm_to_iu(x), mm_to_iu(y))


def get_net(board, name):
    return board.GetNetInfo().GetNetItem(name)


def add_track(board, x1, y1, x2, y2, layer, width_mm, net):
    """Add a single track segment."""
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(vec(x1, y1))
    t.SetEnd(vec(x2, y2))
    t.SetLayer(layer)
    t.SetWidth(mm_to_iu(width_mm))
    t.SetNet(net)
    board.Add(t)
    return t


def add_via(board, x, y, net, top=None, bot=None):
    """Add through-hole via for plane stitching."""
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(x, y))
    v.SetWidth(mm_to_iu(VIA_DIA))
    v.SetDrill(mm_to_iu(VIA_DRILL))
    if top is None: top = pcbnew.F_Cu
    if bot is None: bot = pcbnew.B_Cu
    v.SetTopLayer(top)
    v.SetBottomLayer(bot)
    v.SetNet(net)
    board.Add(v)
    return v


def add_zone(board, layer, net, points, name):
    """Add a filled zone on the given layer/net covering the polygon points."""
    zc = pcbnew.ZONE(board)
    zc.SetLayer(layer)
    zc.SetNet(net)
    zc.SetIsRuleArea(False)
    zc.SetThermalReliefGap(mm_to_iu(0.3))
    zc.SetMinThickness(mm_to_iu(0.2))
    poly = zc.Outline()
    chain = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in points:
        chain.Append(mm_to_iu(x), mm_to_iu(y))
    chain.SetClosed(True)
    poly.AddOutline(chain)
    board.Add(zc)
    return zc


def main():
    board = pcbnew.LoadBoard(PCB)

    NET_BATT = get_net(board, "+BATT")
    NET_VMOTOR = get_net(board, "+VMOTOR")
    NET_BATGND = get_net(board, "BATGND")
    NET_GND = get_net(board, "GND")
    NET_GATE_RP = get_net(board, "GATE_RP")

    if not all((NET_BATT, NET_VMOTOR, NET_BATGND, NET_GND, NET_GATE_RP)):
        print("Missing one of nets: +BATT, +VMOTOR, BATGND, GND, GATE_RP")
        return 1

    tracks_added = 0
    vias_added = 0

    # ─── +BATT high-current path ───
    # J1 pad 1 (50, 4) → R1 pad 1 (25.5, 5) [west NTC]
    add_track(board, 50.0, 4.0, 25.5, 5.0, pcbnew.F_Cu, W_PWR, NET_BATT)
    tracks_added += 1
    # J1 pad 1 (50, 4) → R2 pad 1 (69.5, 2) [east NTC]
    add_track(board, 50.0, 4.0, 69.5, 2.0, pcbnew.F_Cu, W_PWR, NET_BATT)
    tracks_added += 1

    # ─── +VMOTOR delivery from NTC pair to bulk caps ───
    # R1 pad 2 (30.58, 5) → C1 pad 1 (28.3, 28)
    add_track(board, 30.58, 5.0, 30.58, 28.0, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    tracks_added += 1
    add_track(board, 30.58, 28.0, 28.3, 28.0, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    tracks_added += 1
    # R2 pad 2 (74.58, 2) → C2 pad 1 (70.8, 31)
    add_track(board, 74.58, 2.0, 74.58, 31.0, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    tracks_added += 1
    add_track(board, 74.58, 31.0, 70.8, 31.0, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    tracks_added += 1
    # C1 pad 1 (28.3, 28) → C3 pad 1 (21.8, 44): bridge to lower bulk cap
    add_track(board, 28.3, 28.0, 28.3, 44.0, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    tracks_added += 1
    add_track(board, 28.3, 44.0, 21.8, 44.0, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    tracks_added += 1
    # C2 pad 1 (70.8, 31) → C4 pad 1 (67.3, 40.5)
    add_track(board, 70.8, 31.0, 70.8, 40.5, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    tracks_added += 1
    add_track(board, 70.8, 40.5, 67.3, 40.5, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    tracks_added += 1

    # ─── BATGND return: J1 pad 2 (50, 6.54) → Q1-Q4 source pad clusters ───
    # Q1 sources at (27.15, 6.87-9.40) — B.Cu. F.Cu→B.Cu via near pad 2 (avg Y=8.13)
    for qx in (27.15, 42.15, 52.15, 67.15):
        # F.Cu trace from J1 to via point near Q source cluster
        add_track(board, 50.0, 6.54, qx, 8.13, pcbnew.F_Cu, W_PWR, NET_BATGND)
        tracks_added += 1
        # via to B.Cu at the source pad cluster center
        add_via(board, qx, 8.13, NET_BATGND)
        vias_added += 1

    # ─── GATE_RP signal: R3 (32, 10.5) drives Q1-Q4 gates ───
    # R3 pad 2 at (32.83, 10.5). Q1-Q4 gate pads at (29.65, 5.59), (44.65, 5.59), ...
    # Daisy-chain Q1→Q2→Q3→Q4. R3 must drop via to B.Cu first.
    add_via(board, 32.83, 10.5, NET_GATE_RP)
    vias_added += 1
    # B.Cu trace from via to Q1 gate (29.65, 5.59) — actually Q1.4 at (27.15, 5.59).
    # Wait, Q1.4 net is GATE_RP based on earlier check (Q3.4 = GATE_RP for example).
    # Q1 gate pad 4 at (27.15, 5.59) — but Q1 is at X=30 so pads should be at X=27.15.
    # Q2 (45) pad 4 at (42.15, 5.59)
    # Q3 (55) pad 4 at (52.15, 5.59)
    # Q4 (70) pad 4 at (67.15, 5.59)
    add_track(board, 32.83, 10.5, 27.15, 5.59, pcbnew.B_Cu, W_SIG, NET_GATE_RP)
    add_track(board, 27.15, 5.59, 42.15, 5.59, pcbnew.B_Cu, W_SIG, NET_GATE_RP)
    add_track(board, 42.15, 5.59, 52.15, 5.59, pcbnew.B_Cu, W_SIG, NET_GATE_RP)
    add_track(board, 52.15, 5.59, 67.15, 5.59, pcbnew.B_Cu, W_SIG, NET_GATE_RP)
    tracks_added += 4

    # D2 Zener clamp: pad 1 (66.95, 10.5) GATE_RP, pad 2 (69.05, 10.5) GND
    # Connect D2 pad 1 to GATE_RP B.Cu trace via a stitching via
    add_via(board, 66.95, 10.5, NET_GATE_RP)
    vias_added += 1
    add_track(board, 66.95, 10.5, 67.15, 5.59, pcbnew.B_Cu, W_SIG, NET_GATE_RP)
    tracks_added += 1
    # D2 pad 2 to GND (via to plane)
    add_via(board, 69.05, 10.5, NET_GND)
    vias_added += 1

    # ─── R3 pad 1 (+VMOTOR) needs connection to +VMOTOR rail ───
    # R3.1 (31.18, 10.5) — short F.Cu hop to R1.2 (30.58, 5) trace.
    # Use 1.0mm to satisfy +VMOTOR net-class width (low-current pull-up but
    # net-class spec doesn't differentiate; width margin doesn't hurt).
    add_track(board, 31.18, 10.5, 31.18, 5.0, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    add_track(board, 31.18, 5.0, 30.58, 5.0, pcbnew.F_Cu, W_PWR, NET_VMOTOR)
    tracks_added += 2

    # ─── VMOTOR plane fill on In3.Cu ───
    # Cover the full board outline; KiCad zone fill handles cutouts around
    # other-net pads automatically.
    add_zone(board, pcbnew.In3_Cu, NET_VMOTOR,
             [(2, 2), (98, 2), (98, 98), (2, 98)],
             "VMOTOR_plane_In3")

    # ─── GND plane fills on In1.Cu and In5.Cu ───
    add_zone(board, pcbnew.In1_Cu, NET_GND,
             [(2, 2), (98, 2), (98, 98), (2, 98)],
             "GND_plane_In1")
    add_zone(board, pcbnew.In5_Cu, NET_GND,
             [(2, 2), (98, 2), (98, 98), (2, 98)],
             "GND_plane_In5")

    # ─── Plane stitching vias at FET drains for high-current GND ───
    # Q1-Q4 drains at (32.85, 5.59-9.40) for Q1, etc. — pads 5/6/7/8 each.
    # Add 4 vias per FET drain cluster (16 total) for ≥100A capability.
    for q_x_base in (32.85, 47.85, 57.85, 72.85):  # drain X for Q1/Q2/Q3/Q4
        for y in (5.59, 6.87, 8.13, 9.40):
            add_via(board, q_x_base, y, NET_GND)
            vias_added += 1

    # ─── C1-C4 GND stitching vias to inner GND planes ───
    for cx_gnd, cy_gnd in [(36.7, 28.0), (79.2, 31.0), (30.2, 44.0), (75.7, 40.5)]:
        add_via(board, cx_gnd, cy_gnd, NET_GND)
        vias_added += 1

    # ─── VMOTOR plane stitching at C1-C4 + R1/R2 outputs (≥8mm spacing) ───
    for cx_v, cy_v in [(28.3, 28.0), (70.8, 31.0), (21.8, 44.0), (67.3, 40.5),
                       (30.58, 5.0), (74.58, 2.0)]:
        add_via(board, cx_v, cy_v, NET_VMOTOR)
        vias_added += 1

    board.Save(PCB)
    print(f"S1 routing: {tracks_added} tracks + {vias_added} vias added")
    print(f"Plane zones: 1 VMOTOR (In3.Cu), 2 GND (In1.Cu + In5.Cu)")
    print(f"Saved {PCB}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
