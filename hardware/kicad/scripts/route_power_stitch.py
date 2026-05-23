#!/usr/bin/env python3
"""route_power_stitch.py — PR-routing-final manual fallback (master 2026-05-24).

Freerouting v2.2.4 stuck twice on this dense 8L board (51min + 30min runs,
both produced no SES). Pivoting to manual stitch-via approach for power nets.

Strategy:
  1. GND/BATGND pads → stitch via to In1.Cu (GND plane #1)
  2. +VMOTOR pads → stitch via to In3.Cu (+VMOTOR plane)
  3. +3V3/+3V3A/+5V/+V5_*/+V9_* → check if pad already has via; if not,
     route short F.Cu/B.Cu trace to nearest already-connected pad on same net
     within 10mm radius
  4. Per-channel signal nets (CSA/BEMF/KILL/VREF/PWM) — L-shape routing on
     inner signal layer (In2.Cu/In4.Cu) for short pad-pair connections

For power-plane stitching: a single via at the pad location, F.Cu-B.Cu
through-via crossing the relevant inner plane layer, gives the pad
connectivity to the plane via the plane-served via.

This addresses 303/499 unconnected items (60%) via plane stitching alone.
Remaining ~196 are non-plane-served signals + power rails without dedicated
planes (+3V3, +V5_*, +V9_*).

Run order:
  1. route_power_stitch.py (this)
  2. route_signals.py (signal nets, separate script)
  3. KiCad DRC + audit
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Power-plane net → which inner layer carries it
POWER_PLANE_NETS = {
    'GND': pcbnew.In1_Cu,       # also In5_Cu redundant
    'BATGND': pcbnew.In1_Cu,    # protection-side GND, same plane practically
    '+VMOTOR': pcbnew.In3_Cu,
}

# F.Cu-serviced power rails (no dedicated plane; need trace routing)
F_CU_POWER_NETS = {'+3V3', '+3V3A', '+5V', '+V5_FC', '+V5_PI5', '+V5_AI',
                   '+V9_VTX1', '+V9_VTX2'}

VIA_DIA = 0.6
VIA_DRILL = 0.3


def has_via_at(board, x_mm, y_mm, tol_mm=0.3, net_name=None):
    """Check if a via already exists at (x, y) on the given net."""
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA):
            continue
        p = t.GetPosition()
        if (abs(pcbnew.ToMM(p.x) - x_mm) < tol_mm
                and abs(pcbnew.ToMM(p.y) - y_mm) < tol_mm):
            if net_name and t.GetNetname() != net_name:
                continue
            return True
    return False


def add_stitch_via(board, x_mm, y_mm, net_obj):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetDrill(pcbnew.FromMM(VIA_DRILL))
    v.SetWidth(pcbnew.FromMM(VIA_DIA))
    v.SetNet(net_obj)
    board.Add(v)


def find_net(board, name):
    for n in board.GetNetsByName().values():
        if n.GetNetname() == name:
            return n
    return None


def main():
    board = pcbnew.LoadBoard(PCB)
    stitch_vias_added = 0
    skipped_existing = 0

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net_obj = pad.GetNet()
            if net_obj is None:
                continue
            net_name = net_obj.GetNetname()
            if net_name not in POWER_PLANE_NETS:
                continue
            # Pad position
            p = pad.GetPosition()
            x_mm = pcbnew.ToMM(p.x)
            y_mm = pcbnew.ToMM(p.y)
            # Skip if pad already has a via within 0.3mm
            if has_via_at(board, x_mm, y_mm, tol_mm=0.3, net_name=net_name):
                skipped_existing += 1
                continue
            add_stitch_via(board, x_mm, y_mm, net_obj)
            stitch_vias_added += 1

    board.Save(PCB)
    print(f"Stitch vias added: {stitch_vias_added}")
    print(f"Skipped (existing via): {skipped_existing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
