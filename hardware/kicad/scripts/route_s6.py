#!/usr/bin/env python3
"""route_s6.py — Phase 5b Task #81e: §S6 connectors + USBLC6 + LEDs.

Adds power delivery + GND vias + LED + USBLC6 routing. Signal routes
to/from MCUs deferred to channel PRs.

Components:
  J14 FC header (50, 90) F.Cu — main FC connector
  J12 AUX header (15, 90) F.Cu — auxiliary connector
  J15 USBLC6 (40, 85) B.Cu — ESD for M1/M2/+V5_FC
  J16 USBLC6 (60, 85) B.Cu — ESD for M3/M4/+V5_FC
  J17 USBLC6 (75, 85) F.Cu — ESD for TLM/+V5_FC/spare
  D3 PWR LED (15, 96) + R4 (18, 96) — green power indicator
  D4 RPOL LED (85, 96) + R5 (82, 96) — red reverse-polarity indicator
  R36/R37 VBAT divider + C49 filter (around J14 area)
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
W_PWR = 0.4
W_SIG = 0.2
W_LED = 0.15
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


def main():
    board = pcbnew.LoadBoard(PCB)
    NI = board.GetNetInfo()

    GND = NI.GetNetItem("GND")
    V3V3 = NI.GetNetItem("+3V3")
    V5_FC = NI.GetNetItem("+V5_FC")
    VMOTOR = NI.GetNetItem("+VMOTOR")
    BATT = NI.GetNetItem("+BATT")
    BATGND = NI.GetNetItem("BATGND")
    VBAT_SENSE = NI.GetNetItem("VBAT_SENSE_OUT")
    LED_PWR = NI.GetNetItem("LED_PWR_NODE")
    LED_RPOL = NI.GetNetItem("LED_RPOL_NODE")

    t = 0; v = 0

    # ─── J14 FC header power/GND ───
    # J14 pad 1 GND, pad 2 VBAT_SENSE_OUT (rest deferred to channel PRs)
    add_via(board, 46.5, 88.0, GND); v += 1  # J14.1 GND
    # J14.2 → R36.2/R37.1/C49.1 VBAT_SENSE_OUT cluster (50.51, 91.5)/(49.99, 84)/(46.52, 84)
    add_track(board, 47.5, 88.0, 50.51, 91.5, pcbnew.F_Cu, W_SIG, VBAT_SENSE); t += 1

    # R36 (50, 91.5): pad 1 +BATT → trace + via; pad 2 → J14.2 (already routed above)
    # +BATT routing from R36.1 — defer long trace to final PR; stub via
    add_via(board, 49.49, 91.5, BATT); v += 1

    # R37 (50.5, 84): pad 1 VBAT_SENSE → R37.1 (49.99, 84) — already part of VBAT div net
    # pad 2 GND → plane via
    add_via(board, 51.01, 84.0, GND); v += 1
    # Connect VBAT_SENSE cluster: R37.1 → C49.1 → R36.2 — short F.Cu hops
    add_track(board, 49.99, 84.0, 46.52, 84.0, pcbnew.F_Cu, W_SIG, VBAT_SENSE); t += 1
    add_track(board, 49.99, 84.0, 50.51, 91.5, pcbnew.F_Cu, W_SIG, VBAT_SENSE); t += 1

    # C49 (47, 84): pad 1 VBAT_SENSE (already linked), pad 2 GND
    add_via(board, 47.48, 84.0, GND); v += 1

    # ─── J12 AUX header power/GND ───
    add_via(board, 12.5, 88.0, GND); v += 1     # J12.1 GND
    add_via(board, 13.5, 88.0, V3V3); v += 1    # J12.2 +3V3

    # ─── J17 USBLC6 (75, 85) F.Cu — power/GND ───
    add_via(board, 73.86, 85.0, GND); v += 1    # J17.2 GND
    add_via(board, 76.14, 85.0, GND); v += 1    # J17.5 GND
    add_via(board, 73.86, 85.95, V5_FC); v += 1 # J17.3 +V5_FC

    # ─── J15 USBLC6 (40, 85) B.Cu — power/GND ───
    add_via(board, 38.86, 85.0, GND); v += 1    # J15.2 GND
    add_via(board, 41.14, 85.0, GND); v += 1    # J15.5 GND
    add_via(board, 38.86, 84.05, V5_FC); v += 1 # J15.3 +V5_FC

    # ─── J16 USBLC6 (60, 85) B.Cu — power/GND ───
    add_via(board, 58.86, 85.0, GND); v += 1    # J16.2 GND
    add_via(board, 61.14, 85.0, GND); v += 1    # J16.5 GND
    add_via(board, 58.86, 84.05, V5_FC); v += 1 # J16.3 +V5_FC

    # ─── D3 PWR LED (15, 96) + R4 (18, 96) ───
    # D3.2 (LED_PWR_NODE) ↔ R4.2 (LED_PWR_NODE)
    add_track(board, 15.79, 96.0, 18.82, 96.0, pcbnew.F_Cu, W_LED, LED_PWR); t += 1
    # R4.1 +VMOTOR → plane via
    add_via(board, 17.18, 96.0, VMOTOR); v += 1
    # D3.1 GND → plane via
    add_via(board, 14.21, 96.0, GND); v += 1

    # ─── D4 RPOL LED (85, 96) + R5 (82, 96) ───
    # D4.2 (LED_RPOL_NODE) ↔ R5.2 (LED_RPOL_NODE)
    add_track(board, 84.21, 96.0, 82.83, 96.0, pcbnew.F_Cu, W_LED, LED_RPOL); t += 1
    # Actually D4.1 is BATGND not LED_RPOL — let me re-check
    # D4: pad 1 BATGND, pad 2 LED_RPOL_NODE. R5: pad 1 +BATT, pad 2 LED_RPOL_NODE
    # So D4.2 ↔ R5.2 is LED_RPOL_NODE — correct
    # D4.1 BATGND → stub via (final routing PR will run BATGND from S1)
    add_via(board, 84.21, 96.0, BATGND); v += 1
    # R5.1 +BATT → stub via (final routing PR will run +BATT trace from S1)
    add_via(board, 81.17, 96.0, BATT); v += 1

    board.Save(PCB)
    print(f"S6 routing: {t} tracks + {v} vias added")
    print(f"Saved {PCB}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
