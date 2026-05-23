#!/usr/bin/env python3
"""route_s3.py — Phase 5b Task #81c: §S3 supervisor + Hall routing.

Adds tracks/vias for Hall sense cluster + supervisor divider network.
Inter-subsystem buses (+V5_FC source, +3V3 rail, +VMOTOR plane access)
use existing plane network via stitching vias.

HALL cluster (around U1 @ 86, 8):
  R30 → U1.1 (HALL_VCC_5V short hop)
  C42/C43 bypass tied to U1.1 (already adjacent via shared net pads)
  U1.2 → GND plane via
  U1.3 → R31/R32 divider → BUS_CURR_HALL_OUT (deferred final route to MCU)
  C44 filter to BUS_CURR_HALL_OUT
  R33/R34 0Ω VMOTOR bridges connect U1.4/U1.5 (F.Cu) to plane via F→B vias

SUPERVISOR cluster (around J11 @ 50, 38):
  R19/R20 VMOTOR_DIV ↔ J11 THR pins
  C41 inrush cap ↔ J11.6
  R21 PG_VMOTOR pull-up
  J11.1/7/8 +3V3 + J11.2 GND → plane vias
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
W_PWR = 1.0
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


def main():
    board = pcbnew.LoadBoard(PCB)
    NI = board.GetNetInfo()
    nets = {n: NI.GetNetItem(n) for n in (
        '+VMOTOR', 'GND', '+3V3', '+V5_FC', 'HALL_VCC_5V', 'HALL_VOUT_RAW',
        'BUS_CURR_HALL_OUT', 'VMOTOR_HALL_HI', 'VMOTOR_HALL_LO',
        'VMOTOR_DIV', 'PG_VMOTOR', 'VMOTOR_SUPER_CT'
    )}

    t = 0; v = 0

    # ─── Hall cluster (around U1 @ 86, 8) ───
    # R30 (84, 8) pad 2 → U1 pad 1 (86, 8) HALL_VCC_5V — 1.5mm hop
    add_track(board, 84.51, 8.0, 86.0, 8.0, pcbnew.F_Cu, W_SIG, nets['HALL_VCC_5V']); t+=1
    # C43 (84, 6) pad 1 (HALL_VCC) → U1 pad 1 (86, 8) — diagonal
    add_track(board, 83.52, 6.0, 84.51, 8.0, pcbnew.F_Cu, W_SIG, nets['HALL_VCC_5V']); t+=1
    # C42 (83, 9) pad 1 (HALL_VCC) → U1 pad 1
    add_track(board, 82.52, 9.0, 86.0, 8.0, pcbnew.F_Cu, W_SIG, nets['HALL_VCC_5V']); t+=1
    # U1 pad 2 (GND) → via to GND plane (In1/In5)
    add_via(board, 86.0, 6.73, nets['GND']); v+=1
    # C42/C43 GND vias
    add_via(board, 83.48, 6.0, nets['GND']); v+=1  # C43 GND
    add_via(board, 83.48, 9.0, nets['GND']); v+=1  # C42 GND
    # U1 pad 3 (HALL_VOUT_RAW) → R31 pad 1 (83.49, 4)
    add_track(board, 86.0, 5.46, 86.0, 4.0, pcbnew.F_Cu, W_SIG, nets['HALL_VOUT_RAW']); t+=1
    add_track(board, 86.0, 4.0, 83.49, 4.0, pcbnew.F_Cu, W_SIG, nets['HALL_VOUT_RAW']); t+=1
    # R31 pad 2 → R32 pad 1 + C44 pad 1 (BUS_CURR_HALL_OUT short cluster)
    # R31.2 (84.51, 4) → R32.1 (82.49, 5) — diagonal
    add_track(board, 84.51, 4.0, 82.49, 5.0, pcbnew.F_Cu, W_SIG, nets['BUS_CURR_HALL_OUT']); t+=1
    # C44.1 (82.52, 7) → R32.1 (82.49, 5)
    add_track(board, 82.52, 7.0, 82.49, 5.0, pcbnew.F_Cu, W_SIG, nets['BUS_CURR_HALL_OUT']); t+=1
    # R32 GND, C44 GND → vias
    add_via(board, 83.51, 5.0, nets['GND']); v+=1
    add_via(board, 83.48, 7.0, nets['GND']); v+=1
    # +V5_FC at R30.1 → via to bring +V5_FC plane signal (deferred to S5 — for now stub via)
    add_via(board, 83.49, 8.0, nets['+V5_FC']); v+=1

    # ─── Hall primary current path (U1 pad 4/5 ↔ R33/R34 B.Cu jumpers) ───
    # U1.4 (78.5, 10.3) F.Cu → via → R33.2 (81.46, 14.5) B.Cu — VMOTOR_HALL_HI
    add_via(board, 78.5, 10.3, nets['VMOTOR_HALL_HI']); v+=1
    add_track(board, 78.5, 10.3, 81.46, 14.5, pcbnew.B_Cu, W_PWR, nets['VMOTOR_HALL_HI']); t+=1
    # R33.1 (75.54, 14.5) → via to +VMOTOR plane (In3.Cu)
    add_via(board, 75.54, 14.5, nets['+VMOTOR']); v+=1
    # U1.5 (78.5, 3.16) F.Cu → via → R34.1 (75.54, 6) B.Cu — VMOTOR_HALL_LO
    add_via(board, 78.5, 3.16, nets['VMOTOR_HALL_LO']); v+=1
    add_track(board, 78.5, 3.16, 75.54, 6.0, pcbnew.B_Cu, W_PWR, nets['VMOTOR_HALL_LO']); t+=1
    # R34.2 (81.46, 6) → via to VMOTOR_CH plane (channel-side; deferred final to routing-final PR)
    add_via(board, 81.46, 6.0, NI.GetNetItem('VMOTOR_CH')); v+=1

    # ─── Supervisor cluster (around J11 @ 50, 38) ───
    # R19 (47, 36) pad 1 +VMOTOR → via to +VMOTOR plane (In3.Cu)
    add_via(board, 46.17, 36.0, nets['+VMOTOR']); v+=1
    # R19 pad 2 → R20 pad 1 (VMOTOR_DIV cluster, both at Y=36)
    add_track(board, 47.83, 36.0, 52.49, 36.0, pcbnew.F_Cu, W_SIG, nets['VMOTOR_DIV']); t+=1
    # VMOTOR_DIV → J11 pad 3/4 (THR pins at 48.86, 38.33-38.98)
    add_track(board, 47.83, 36.0, 48.86, 38.33, pcbnew.F_Cu, W_SIG, nets['VMOTOR_DIV']); t+=1
    # R20 pad 2 GND → via
    add_via(board, 53.51, 36.0, nets['GND']); v+=1
    # C41 (55, 40) pad 1 VMOTOR_SUPER_CT → J11.6 (51.14, 38.33)
    add_track(board, 54.52, 40.0, 51.14, 38.33, pcbnew.F_Cu, W_SIG, nets['VMOTOR_SUPER_CT']); t+=1
    # C41 GND via
    add_via(board, 55.48, 40.0, nets['GND']); v+=1
    # R21 (53, 40) pad 1 PG_VMOTOR → J11.5 (51.14, 38.98)
    add_track(board, 52.49, 40.0, 51.14, 38.98, pcbnew.F_Cu, W_SIG, nets['PG_VMOTOR']); t+=1
    # R21 pad 2 +3V3 → via
    add_via(board, 53.51, 40.0, nets['+3V3']); v+=1
    # J11 pad 1/7/8 +3V3 → vias
    add_via(board, 48.86, 37.02, nets['+3V3']); v+=1
    add_via(board, 51.14, 37.67, nets['+3V3']); v+=1
    add_via(board, 51.14, 37.02, nets['+3V3']); v+=1
    # J11 pad 2 GND → via
    add_via(board, 48.86, 37.67, nets['GND']); v+=1

    board.Save(PCB)
    print(f"S3 routing: {t} tracks + {v} vias added")
    print(f"Saved {PCB}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
