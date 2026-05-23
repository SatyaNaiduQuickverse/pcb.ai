#!/usr/bin/env python3
"""route_s5.py — Phase 5b Task #81d: §S5 BEC subsystem routing.

5 buck converters (J2-J6) + LDO (J13). Each buck: VIN, SW, L, Cout, FB,
BST, catch diode, GND. Critical: SW node short, input cap close to VIN.

Bucks 1-4 placed in spine pocket Y=72-80, mirror X=43↔57.
Buck 5 (V9_VTX2) asymmetric SW corner at (12, 22) — single instance.
LDO J13 at (49, 76) central, supervisor J10 at (51, 77) B.Cu.

Inductors on B.Cu directly under buck ICs for short SW path through
F↔B via.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
W_PWR = 1.0
W_BUCK_RAIL = 0.4    # buck output rails (V_BUCK*_OUT) ~2-3A
W_SIG = 0.2
VIA_DIA = 0.6
VIA_DRILL = 0.3


def mm_to_iu(x): return pcbnew.FromMM(x)
def vec(x, y): return pcbnew.VECTOR2I(mm_to_iu(x), mm_to_iu(y))


def add_track(board, x1, y1, x2, y2, layer, width_mm, net):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(vec(x1, y1))
    t.SetEnd(vec(x2, y2))
    t.SetLayer(layer)
    t.SetWidth(mm_to_iu(width_mm))
    t.SetNet(net)
    board.Add(t)


def add_via(board, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(x, y))
    v.SetWidth(mm_to_iu(VIA_DIA))
    v.SetDrill(mm_to_iu(VIA_DRILL))
    v.SetTopLayer(pcbnew.F_Cu)
    v.SetBottomLayer(pcbnew.B_Cu)
    v.SetNet(net)
    board.Add(v)


def route_buck(board, NI, buck_n, buck_ic_xy, ind_xy, ind_pad1, ind_pad2,
               fb_r1, fb_r2, bst_cap, cout_cap, vout_net_name):
    """Route one buck loop.
    buck_n: 1..5
    buck_ic_xy: (x, y) of buck IC (e.g., J2 at 43,72)
    ind_xy: (x, y) of inductor center (B.Cu)
    ind_pad1, ind_pad2: (x, y) of L.1 (SW input) and L.2 (V_OUT)
    fb_r1, fb_r2: FB divider resistors (R-top to VOUT, R-bot to GND)
    bst_cap: bootstrap cap position
    cout_cap: output cap position
    vout_net_name: name of buck output rail (+V5_FC etc) — note: maps from
                   V_BUCK*_OUT net which then connects to +V5_FC plane.
    """
    t = 0; v = 0
    ix, iy = buck_ic_xy
    # Per S5 dict pinout: pad 1 BST, 2/3 VIN, 4 FB, 5/8 GND, 6/7 SW
    p_bst = (ix - 2.48, iy - 1.91)
    p_vin_a = (ix - 2.48, iy - 0.64)
    p_vin_b = (ix - 2.48, iy + 0.64)
    p_fb = (ix - 2.48, iy + 1.91)
    p_gnd_a = (ix + 2.48, iy + 1.91)
    p_sw_a = (ix + 2.48, iy + 0.64)
    p_sw_b = (ix + 2.48, iy - 0.64)
    p_gnd_b = (ix + 2.48, iy - 1.91)

    sw_net = NI.GetNetItem(f"BUCK{buck_n}_SW")
    bst_net = NI.GetNetItem(f"BUCK{buck_n}_BST")
    fb_net = NI.GetNetItem(f"BUCK{buck_n}_FB")
    vin_net = NI.GetNetItem("+VMOTOR")
    gnd_net = NI.GetNetItem("GND")
    vout_net = NI.GetNetItem(f"V_BUCK{buck_n}_OUT")

    if not all((sw_net, bst_net, fb_net, vin_net, gnd_net, vout_net)):
        print(f"  Buck #{buck_n}: missing nets — skip")
        return 0, 0

    # VIN: pads 2/3 → +VMOTOR plane (In3.Cu) via stitching
    add_via(board, p_vin_a[0], p_vin_a[1], vin_net); v += 1
    add_via(board, p_vin_b[0], p_vin_b[1], vin_net); v += 1

    # GND: pads 5/8 → GND plane (In1/In5)
    add_via(board, p_gnd_a[0], p_gnd_a[1], gnd_net); v += 1
    add_via(board, p_gnd_b[0], p_gnd_b[1], gnd_net); v += 1

    # SW: pads 6/7 → L inductor pad 1 (B.Cu)
    # F.Cu pad → via → B.Cu trace to L1.pad1
    add_via(board, p_sw_a[0], p_sw_a[1], sw_net); v += 1
    add_track(board, p_sw_a[0], p_sw_a[1], ind_pad1[0], ind_pad1[1],
              pcbnew.B_Cu, W_PWR, sw_net); t += 1
    # short F.Cu jumper to second SW pad
    add_track(board, p_sw_a[0], p_sw_a[1], p_sw_b[0], p_sw_b[1],
              pcbnew.F_Cu, W_PWR, sw_net); t += 1

    # L output: L.pad2 → V_BUCK_OUT (B.Cu trace to cout_cap)
    if cout_cap:
        add_track(board, ind_pad2[0], ind_pad2[1], cout_cap[0], cout_cap[1],
                  pcbnew.B_Cu, W_BUCK_RAIL, vout_net); t += 1
        # cout F→B via at output cap location for distribution to F.Cu loads
        add_via(board, cout_cap[0], cout_cap[1], vout_net); v += 1

    # FB sense: pad 4 → FB divider (Kelvin from Cout)
    if fb_r1 and fb_r2:
        # FB pad → R_top
        add_track(board, p_fb[0], p_fb[1], fb_r1[0], fb_r1[1],
                  pcbnew.F_Cu, W_SIG, fb_net); t += 1
        # R_top to V_BUCK_OUT (Kelvin from Cout) — V_BUCK net needs ≥0.3mm
        if cout_cap:
            add_track(board, fb_r1[0], fb_r1[1], cout_cap[0], cout_cap[1],
                      pcbnew.F_Cu, W_BUCK_RAIL, vout_net); t += 1
            add_via(board, cout_cap[0], cout_cap[1], vout_net); v += 1

    # BST cap: pad 1 → BST cap pad
    if bst_cap:
        add_track(board, p_bst[0], p_bst[1], bst_cap[0], bst_cap[1],
                  pcbnew.F_Cu, W_SIG, bst_net); t += 1

    return t, v


def main():
    board = pcbnew.LoadBoard(PCB)
    NI = board.GetNetInfo()

    total_t = 0; total_v = 0

    # Buck #1 V5_FC
    t, v = route_buck(board, NI, 1,
                      buck_ic_xy=(43, 72),
                      ind_xy=(35, 73),
                      ind_pad1=(31.98, 73), ind_pad2=(38.02, 73),
                      fb_r1=(40, 69), fb_r2=(40, 70.5),
                      bst_cap=(45.5, 72),
                      cout_cap=(49, 72),  # C8 at (49, 72)
                      vout_net_name="+V5_FC")
    total_t += t; total_v += v

    # Buck #2 V5_PI5
    t, v = route_buck(board, NI, 2,
                      buck_ic_xy=(43, 80),
                      ind_xy=(48, 84.5),
                      ind_pad1=(44.98, 84.5), ind_pad2=(51.02, 84.5),
                      fb_r1=(40, 78), fb_r2=(40, 79.5),
                      bst_cap=(45.5, 80),
                      cout_cap=(51, 80),  # C12 at (51, 80)
                      vout_net_name="+V5_PI5")
    total_t += t; total_v += v

    # Buck #3 V5_AI
    t, v = route_buck(board, NI, 3,
                      buck_ic_xy=(57, 72),
                      ind_xy=(62, 67),
                      ind_pad1=(59.95, 67), ind_pad2=(64.05, 67),
                      fb_r1=(60, 69), fb_r2=(60, 70.5),
                      bst_cap=(54.5, 72),
                      cout_cap=(22, 85),  # C15 V5_AI C_OUT at top strip W
                      vout_net_name="+V5_AI")
    total_t += t; total_v += v

    # Buck #4 V9_VTX1
    t, v = route_buck(board, NI, 4,
                      buck_ic_xy=(57, 80),
                      ind_xy=(63.5, 73.5),
                      ind_pad1=(61.45, 73.5), ind_pad2=(65.55, 73.5),
                      fb_r1=(60, 78), fb_r2=(60, 79.5),
                      bst_cap=(54.5, 80),
                      cout_cap=(86.5, 83),  # C18 V9_VTX1 C_OUT at top strip E
                      vout_net_name="+V9_VTX1")
    total_t += t; total_v += v

    # Buck #5 V9_VTX2 — SW asymmetric corner. Different geometry.
    # J6 at (12, 22), L5 at (20, 38), no convenient bst/cout placed close.
    # For Buck#5, only route VIN/GND/SW (skip BST/FB tracing — defer to
    # final routing PR where Buck#5 components are accessible).
    p_vin_5a = (12 - 2.47, 21.36)
    p_vin_5b = (12 - 2.47, 22.64)
    p_gnd_5a = (12 + 2.47, 20.09)
    p_gnd_5b = (12 + 2.47, 23.91)
    p_sw_5a = (12 + 2.47, 22.64)
    p_sw_5b = (12 + 2.47, 21.36)
    vin5 = NI.GetNetItem("+VMOTOR")
    gnd = NI.GetNetItem("GND")
    sw5 = NI.GetNetItem("BUCK5_SW")
    add_via(board, p_vin_5a[0], p_vin_5a[1], vin5); total_v += 1
    add_via(board, p_vin_5b[0], p_vin_5b[1], vin5); total_v += 1
    add_via(board, p_gnd_5a[0], p_gnd_5a[1], gnd); total_v += 1
    add_via(board, p_gnd_5b[0], p_gnd_5b[1], gnd); total_v += 1
    # SW: J6 (F.Cu pads) → L5 (F.Cu inductor at 20, 38) — F.Cu trace
    add_track(board, p_sw_5a[0], p_sw_5a[1], 17.95, 38.0,
              pcbnew.F_Cu, W_PWR, sw5); total_t += 1
    add_track(board, p_sw_5a[0], p_sw_5a[1], p_sw_5b[0], p_sw_5b[1],
              pcbnew.F_Cu, W_PWR, sw5); total_t += 1
    # L5 output (V_BUCK5_OUT) → distribution via
    vout5 = NI.GetNetItem("V_BUCK5_OUT")
    if vout5:
        add_via(board, 22.05, 38.0, vout5); total_v += 1

    # ─── LDO J13 (49, 76) ───
    # Per pinout: pad 1 (+V5_FC IN), pad 2 (GND), pad 3 (+V5_FC IN duplicate),
    # pad 5 (+3V3 OUT). No bypass caps routed here explicitly (deferred).
    v5fc = NI.GetNetItem("+V5_FC")
    v3v3 = NI.GetNetItem("+3V3")
    # +V5_FC plane stitching at LDO input pads
    add_via(board, 48.11, 75.35, v5fc); total_v += 1
    add_via(board, 48.11, 76.65, v5fc); total_v += 1
    # GND via
    add_via(board, 48.11, 76.0, gnd); total_v += 1
    # +3V3 plane stitching at LDO output
    add_via(board, 49.89, 76.0, v3v3); total_v += 1

    board.Save(PCB)
    print(f"S5 routing: {total_t} tracks + {total_v} vias added")
    print(f"Saved {PCB}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
