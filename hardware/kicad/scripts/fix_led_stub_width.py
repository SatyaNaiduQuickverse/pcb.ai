#!/usr/bin/env python3
"""fix_led_stub_width.py — codified per [[feedback-codify-not-patch]] master 2026-05-24.

route_s6.py uses W_LED=0.15mm for LED indicator stubs on +VMOTOR/BATGND nets.
These short tracks (D3 PWR LED + D4 RPOL LED) are signal-current-only (~10mA
through the LED + limit-R) but their NET is +VMOTOR (high-current power bus)
or BATGND. audit_routing check_track_width sees the net=+VMOTOR + width<1.0mm
and FAILS — false-positive because the track is functionally an LED indicator
stub, not the power bus.

PR #67 amendment fixed this manually by widening the stubs. That one-shot
patch wasn't codified, so Phase 3 re-import + route_s6 re-introduced them.

This codified fix:
  1. Finds tracks on (+VMOTOR, BATGND, +5V, +V5_FC, +V5_PI5, +V5_AI) nets
     that are LENGTH < 5mm AND WIDTH < 0.5mm (the LED indicator stub signature)
  2. Widens them to 1.0mm to match power-class minimum
  3. The widened stub still functions identically electrically (carries
     ~10mA, plenty of margin at any width)

Add to post_kinet2pcb_pipeline.py as step after route_s6.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

POWER_NETS = {'+VMOTOR', 'BATGND', '+5V', '+V5_FC', '+V5_PI5', '+V5_AI',
              '+3V3', '+3V3A', '+V9_VTX1', '+V9_VTX2'}
MIN_STUB_WIDTH_MM = 1.0
STUB_LEN_MAX_MM = 5.0
STUB_W_MAX_MM = 0.5


def main():
    board = pcbnew.LoadBoard(PCB)
    widened = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        net = t.GetNetname()
        if net not in POWER_NETS:
            continue
        s = t.GetStart()
        e = t.GetEnd()
        length = ((s.x - e.x) ** 2 + (s.y - e.y) ** 2) ** 0.5 / 1e6
        width = t.GetWidth() / 1e6
        if length < STUB_LEN_MAX_MM and width < STUB_W_MAX_MM:
            t.SetWidth(pcbnew.FromMM(MIN_STUB_WIDTH_MM))
            widened.append((net, length, width,
                            s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6))
    for net, length, width, x1, y1, x2, y2 in widened:
        print(f"  {net}: len={length:.2f}mm width={width:.3f}→{MIN_STUB_WIDTH_MM}mm "
              f"at ({x1:.1f},{y1:.1f})→({x2:.1f},{y2:.1f})")
    print(f"\nWidened {len(widened)} LED indicator stub track(s) to {MIN_STUB_WIDTH_MM}mm")
    board.Save(PCB)


if __name__ == "__main__":
    main()
