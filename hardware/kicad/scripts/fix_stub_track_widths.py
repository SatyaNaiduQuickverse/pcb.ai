#!/usr/bin/env python3
"""fix_stub_track_widths.py — Widen Phase A offset-via stub tracks per net class.

Phase A route_power_plane_stitch.py creates 0.3mm-wide stub traces from pad
to offset-via on power nets (GND/BATGND/+VMOTOR). For VMOTOR + BATGND high-
current paths, audit_routing requires ≥1.0mm. This script widens those.

Net-class widths (from audit_routing):
  +VMOTOR, BATGND: 1.0mm
  GND: stub width acceptable at 0.3mm (audit only flags VMOTOR/BATGND)
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

import re


def class_min_width(netname):
    if not netname: return 0
    if netname in ('+VMOTOR', 'VMOTOR_CH', 'VMOTOR_HALL_HI', 'VMOTOR_HALL_LO', 'BATGND'):
        return 1.0
    if 'MOTOR_' in netname and not any(x in netname for x in ('_DIV', '_SUPER', 'PG_', 'SENSE')):
        return 1.0
    if 'SHUNT_' in netname:
        return 1.0
    if re.match(r'\+V5', netname) or 'V_BUCK' in netname:
        return 0.3
    if re.match(r'\+V9', netname):
        return 0.3
    if re.match(r'\+3V3', netname) or netname.startswith('V3V3'):
        return 0.25
    return 0  # signal — no enforcement here


def main():
    b = pcbnew.LoadBoard(PCB)
    widened = 0
    by_class = {}
    for t in b.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA): continue
        net = t.GetNetname()
        target = class_min_width(net)
        if target <= 0: continue
        cur_w_mm = pcbnew.ToMM(t.GetWidth())
        if cur_w_mm < target:
            t.SetWidth(pcbnew.FromMM(target))
            widened += 1
            by_class[target] = by_class.get(target, 0) + 1
    print(f"Widened {widened} tracks to net-class minimum")
    for w, n in sorted(by_class.items()):
        print(f"  → {w}mm: {n} tracks")
    b.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
