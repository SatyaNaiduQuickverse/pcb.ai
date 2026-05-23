#!/usr/bin/env python3
"""route_ch1.py — Phase 5b Task #81f: CH1 channel template routing.

Routes the FULL per-channel circuit for CH1 only:
  Motor phase A/B/C: Q5/Q6 → TP19, Q7/Q8 → TP20, Q9/Q10 → TP21
  Shunt sense: Q6/Q8/Q10 sources → R56/R57/R58 → J20/J21/J22 INA186
  +VMOTOR plane stitching at Q5/Q7/Q9 drains (via to In3.Cu plane)
  GND plane stitching at FET-adjacent pads
  Power vias: J18 MCU + J19 DRV + J20-22 INA186 +3V3/+V5/GND

Channel-level gate drive (DRV → gate-R → FET gate) + sense routing (CSA →
MCU ADC + BEMF → MCU comparator + PWM_X → DRV) require explicit DRV/MCU
pin mapping. Deferred to PR-routing-final (Task #82) where MCU pinout
is finalized.

CH1 routing here = MOTOR PHASE current paths + SHUNT sense paths + power
vias. ~25 tracks expected.

NOTE on VMOTOR_CH: this net is the channel-side +VMOTOR (after Hall + R34
0Ω bridge). For PR-CH1-route, route as 1.0mm B.Cu traces from FET drain
clusters. A proper VMOTOR_CH plane (separate zone on In3.Cu) is deferred
to PR-routing-final.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
W_PWR = 1.0
W_SIG = 0.2
VIA_DIA = 0.6
VIA_DRILL = 0.3


def mm_to_iu(x): return pcbnew.FromMM(x)
def vec(x, y): return pcbnew.VECTOR2I(mm_to_iu(x), mm_to_iu(y))


def add_track(board, x1, y1, x2, y2, layer, w, net):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(vec(x1, y1)); t.SetEnd(vec(x2, y2))
    t.SetLayer(layer); t.SetWidth(mm_to_iu(w)); t.SetNet(net)
    board.Add(t)


def add_via(board, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(x, y))
    v.SetWidth(mm_to_iu(VIA_DIA)); v.SetDrill(mm_to_iu(VIA_DRILL))
    v.SetTopLayer(pcbnew.F_Cu); v.SetBottomLayer(pcbnew.B_Cu)
    v.SetNet(net)
    board.Add(v)


def route_phase(board, NI, phase, q_hi, q_lo, tp, r_shunt, ina, q_hi_y):
    """Route one CH1 phase.
    phase: 'A', 'B', 'C'
    q_hi/q_lo: (x, y) of high/low FET (B.Cu)
    tp: (x, y) of motor TP pad (F.Cu)
    r_shunt: (x, y) of shunt resistor
    ina: (x, y) of INA186 chip
    q_hi_y: Y axis of FET row (used for pad coords)
    """
    motor_net = NI.GetNetItem(f"MOTOR_{phase}_CH1")
    shunt_net = NI.GetNetItem(f"SHUNT_{phase}_TOP_CH1")
    csa_net = NI.GetNetItem(f"CSA_{phase}_OUT_CH1")
    vmotor_ch = NI.GetNetItem("VMOTOR_CH")
    gnd = NI.GetNetItem("GND")
    v3v3 = NI.GetNetItem("+3V3")

    if not all((motor_net, shunt_net, vmotor_ch, gnd)):
        print(f"  Phase {phase}: missing nets — skip")
        return 0, 0

    t = 0; v = 0

    # PDFN-8 pad coordinates relative to FET center (rot=0):
    # pads 1-3 (source) at X=center-2.85, Y=center±1.91/0.63
    # pad 4 (gate) at X=center-2.85, Y=center+2.91
    # pads 5-8 (drain) at X=center+2.85, Y=center±1.91/0.63
    qhi_src_x = q_hi[0] - 2.85
    qhi_drn_x = q_hi[0] + 2.85
    qlo_src_x = q_lo[0] - 2.85
    qlo_drn_x = q_lo[0] + 2.85

    # MOTOR_X_CH1 node: Q_hi source pads (X=qhi_src_x, Y=q_hi_y±2) ↔ Q_lo drain pads
    # Both FETs at same Y row (q_hi_y); B.Cu trace from Q_hi source cluster to Q_lo drain cluster.
    add_track(board, qhi_src_x, q_hi_y, qlo_drn_x, q_hi_y,
              pcbnew.B_Cu, W_PWR, motor_net); t += 1

    # MOTOR_X_CH1 → TP (motor pad). TP is at (5, q_hi_y) F.Cu; FET sources B.Cu.
    # Need F.Cu trace from TP edge to via, then B.Cu to Q_hi source.
    # Add via near Q_hi source cluster + F.Cu trace from TP to via
    add_via(board, qhi_src_x, q_hi_y, motor_net); v += 1
    add_track(board, tp[0] + 1.5, tp[1], qhi_src_x, q_hi_y,
              pcbnew.F_Cu, W_PWR, motor_net); t += 1

    # SHUNT_X_TOP_CH1: Q_lo source pads (B.Cu) → R_shunt pad 1 (F.Cu)
    # F→B via near shunt pad 1
    add_via(board, qlo_src_x, q_hi_y, shunt_net); v += 1
    # F.Cu trace from R_shunt pad 1 to via
    add_track(board, r_shunt[0] - 2.96, r_shunt[1], qlo_src_x, q_hi_y,
              pcbnew.F_Cu, W_PWR, shunt_net); t += 1

    # R_shunt pad 1 → INA186 pad 1 (high input) — Kelvin sense, but net is SHUNT
    # class which requires 1.0mm width per net_class; widen to comply (over-spec OK).
    add_track(board, r_shunt[0] - 2.96, r_shunt[1], ina[0] - 0.95, ina[1] - 0.65,
              pcbnew.F_Cu, W_PWR, shunt_net); t += 1
    # R_shunt pad 2 GND via
    add_via(board, r_shunt[0] + 2.96, r_shunt[1], gnd); v += 1

    # INA186 power/GND vias
    add_via(board, ina[0] - 0.95, ina[1], gnd); v += 1     # pad 2 GND
    add_via(board, ina[0] - 0.95, ina[1] + 0.65, gnd); v += 1  # pad 3 GND
    add_via(board, ina[0] + 0.95, ina[1] + 0.65, v3v3); v += 1  # pad 4 +3V3
    add_via(board, ina[0] + 0.95, ina[1] - 0.65, gnd); v += 1   # pad 6 GND
    # INA pad 5 = CSA_X_OUT (signal output to MCU — final route to MCU ADC deferred)
    add_via(board, ina[0] + 0.95, ina[1], csa_net); v += 1

    # +VMOTOR plane stitching at Q_hi drain pads (4 pads)
    for dy in (-1.91, -0.63, 0.63, 1.91):
        add_via(board, qhi_drn_x, q_hi_y + dy, vmotor_ch); v += 1

    return t, v


def main():
    board = pcbnew.LoadBoard(PCB)
    NI = board.GetNetInfo()
    total_t = 0; total_v = 0

    # CH1 phase A: Q5 (12, 56) hi, Q6 (30, 56) lo, TP19 (5, 56), R56 (13.5, 60), J20 (5, 62)
    t, v = route_phase(board, NI, 'A',
                       q_hi=(12, 56), q_lo=(30, 56),
                       tp=(5, 56), r_shunt=(13.5, 60), ina=(5, 62),
                       q_hi_y=56)
    total_t += t; total_v += v

    # CH1 phase B: Q7 (12, 68), Q8 (30, 68), TP20 (5, 68), R57 (13.5, 72), J21 (5, 74)
    t, v = route_phase(board, NI, 'B',
                       q_hi=(12, 68), q_lo=(30, 68),
                       tp=(5, 68), r_shunt=(13.5, 72), ina=(5, 74),
                       q_hi_y=68)
    total_t += t; total_v += v

    # CH1 phase C: Q9 (12, 80), Q10 (30, 80), TP21 (5, 80), R58 (13.5, 84), J22 (40, 92)
    # J22 phase C is at (40, 92) NW corner — different from J20/J21 W-edge pattern
    t, v = route_phase(board, NI, 'C',
                       q_hi=(12, 80), q_lo=(30, 80),
                       tp=(5, 80), r_shunt=(13.5, 84), ina=(40, 92),
                       q_hi_y=80)
    total_t += t; total_v += v

    # ─── CH1 MCU J18 (32, 86) power vias ───
    # MCU QFN-32 has 32 numbered pads + EP. Many +3V3/GND pads.
    # Add power vias at MCU corner pads — actual pin-by-pin sig routing deferred to final.
    # MCU has +3V3 at pad 1, +3V3 at pad 17, +3V3A at pad 5, GND at pads 16/32 (and EP).
    # Use approximation positions for plane stitching.
    j18 = (32, 86)
    # QFN-32 5×5mm: pads on perimeter, ~0.5mm pitch, EP under chip
    # Approximate corner via positions
    v3v3 = NI.GetNetItem("+3V3")
    gnd = NI.GetNetItem("GND")
    for dx, dy, n in [(-2, -2, gnd), (2, -2, gnd), (-2, 2, gnd), (2, 2, gnd),
                       (0, -2.5, v3v3), (-2.5, 0, v3v3), (2.5, 0, v3v3)]:
        add_via(board, j18[0] + dx, j18[1] + dy, n); total_v += 1
    # MCU EP center via to GND
    add_via(board, j18[0], j18[1], gnd); total_v += 1

    # ─── CH1 DRV J19 (40, 62) power vias ───
    j19 = (40, 62)
    v5 = NI.GetNetItem("+V5_FC")
    if not v5:
        v5 = NI.GetNetItem("+V5_PI5")  # fallback
    for dx, dy, n in [(-1.5, -1.5, gnd), (1.5, -1.5, gnd), (-1.5, 1.5, gnd), (1.5, 1.5, gnd),
                       (0, -1.5, v5 if v5 else gnd), (0, 0, gnd)]:
        add_via(board, j19[0] + dx, j19[1] + dy, n); total_v += 1

    board.Save(PCB)
    print(f"CH1 routing: {total_t} tracks + {total_v} vias added")
    print(f"  3 phases × ~5 tracks + power stitching")
    print(f"Saved {PCB}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
