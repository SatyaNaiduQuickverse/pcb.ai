#!/usr/bin/env python3
"""route_signals_role_aware.py — PR-routing-final manual router.

Per master 2026-05-24 F2 dispatch: Freerouting v2.2.4 incompatible with this
dense 8L board (4 attempts: 51min/30min/30min/15min all stuck post-init,
no SES produced, only init messages in log). Pivoting to manual routing.

Strategy (role-aware, ref-stability immune):

1. POWER-NET STUB STITCHING (303 of 499 unconnected items):
   Pad → 0.3mm F.Cu/B.Cu stub trace → via at offset position → plane on inner layer.
   This makes KiCad see: pad ↔ trace ↔ via ↔ plane = connected.
   - GND/BATGND: via crosses In1.Cu and In5.Cu GND planes
   - +VMOTOR: via crosses In3.Cu +VMOTOR plane
   - +3V3/+3V3A/+5V/+V5_*/+V9_*: no dedicated plane; pads need explicit
     trace routing to a nearby already-connected pad on same net within
     8mm (MST/greedy across the net's pad set)

2. CHANNEL-INTERNAL SIGNAL NETS (per-channel CSA/BEMF/KILL/VREF/PWM/etc.):
   For each unconnected pad-pair on the net within the channel zone:
   - L-shape route on F.Cu (primary) or In2.Cu (secondary) signal layer
   - 0.15mm trace width (signal) or 0.2mm (control)
   - Add vias only when changing layer

3. CH1 ROUTE FIRST, THEN MIRROR via route_mirror_ch1_to_ch234.py
   - Preserve R19 channel symmetry

4. AUDIT AFTER EACH PASS: audit_routing.py 6 checks
"""
import pcbnew
import re
import math
from collections import defaultdict

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Power-plane net → primary stub side (F.Cu by default)
GND_NETS = {'GND', 'BATGND'}
VMOTOR_NETS = {'+VMOTOR'}
POWER_TRACE_NETS = {'+3V3', '+3V3A', '+5V', '+V5_FC', '+V5_PI5', '+V5_AI',
                    '+V9_VTX1', '+V9_VTX2', 'V9_VTX1_PROTECT_OUT',
                    'V9_VTX2_PROTECT_OUT', 'VMOTOR_CH', 'HALL_VCC_5V',
                    'HALL_VOUT_RAW'}

W_STUB = 0.3
W_SIG = 0.15
W_POWER_TRACE = 0.5
VIA_DIA = 0.6
VIA_DRILL = 0.3
STUB_OFFSET = 0.5  # mm offset of via from pad center


def find_net(board, name):
    for n in board.GetNetsByName().values():
        if n.GetNetname() == name:
            return n
    return None


def add_track(board, x1, y1, x2, y2, layer, width, net):
    if abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01:
        return None  # zero-length, skip
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
    t.SetLayer(layer)
    t.SetWidth(pcbnew.FromMM(width))
    t.SetNet(net)
    board.Add(t)
    return t


def add_via(board, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetDrill(pcbnew.FromMM(VIA_DRILL))
    v.SetWidth(pcbnew.FromMM(VIA_DIA))
    v.SetNet(net)
    board.Add(v)


def collect_pads_by_net(board):
    """Return dict: net_name → list of (ref, pad_name, x_mm, y_mm, layer, has_existing_track)."""
    nets = defaultdict(list)
    # Track-served pads (set of (net, x, y))
    track_endpoints = set()
    for t in board.GetTracks():
        for p in (t.GetStart(), t.GetEnd()):
            track_endpoints.add((t.GetNetname(),
                                  round(p.x / 1e6, 2),
                                  round(p.y / 1e6, 2)))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net_obj = pad.GetNet()
            if net_obj is None: continue
            n = net_obj.GetNetname()
            if not n: continue
            p = pad.GetPosition()
            xy = (round(p.x / 1e6, 2), round(p.y / 1e6, 2))
            ls = pad.GetLayerSet()
            layers = []
            if ls.Contains(pcbnew.F_Cu): layers.append('F')
            if ls.Contains(pcbnew.B_Cu): layers.append('B')
            if not layers: continue
            has_track = (n, xy[0], xy[1]) in track_endpoints
            nets[n].append({
                'ref': fp.GetReference(),
                'pad': pad.GetPadName(),
                'x': xy[0], 'y': xy[1],
                'layers': layers,
                'has_track': has_track,
            })
    return nets


def stub_via_route(board, pad, net_obj):
    """For a power-net pad, add stub trace + via to bring connectivity to plane.
    Offset direction: prefer N/E/S/W based on which side is least crowded.
    Default: 0.5mm east (positive X) for now."""
    px = pad['x']
    py = pad['y']
    via_x = px + STUB_OFFSET
    via_y = py
    # Pick layer for stub based on pad layer
    layer = pcbnew.F_Cu if 'F' in pad['layers'] else pcbnew.B_Cu
    add_track(board, px, py, via_x, via_y, layer, W_STUB, net_obj)
    add_via(board, via_x, via_y, net_obj)


def route_pad_pair(board, pa, pb, net_obj, width=W_SIG):
    """L-shape route between two pads on F.Cu (primary)."""
    layer = pcbnew.F_Cu if 'F' in pa['layers'] and 'F' in pb['layers'] else pcbnew.In2_Cu
    # Pick corner: align with longer axis
    dx = abs(pa['x'] - pb['x'])
    dy = abs(pa['y'] - pb['y'])
    if dx > dy:
        cx, cy = pb['x'], pa['y']
    else:
        cx, cy = pa['x'], pb['y']
    # If routing on inner, add vias at endpoints
    needs_vias = layer != pcbnew.F_Cu
    if needs_vias:
        add_via(board, pa['x'], pa['y'], net_obj)
        add_via(board, pb['x'], pb['y'], net_obj)
    add_track(board, pa['x'], pa['y'], cx, cy, layer, width, net_obj)
    add_track(board, cx, cy, pb['x'], pb['y'], layer, width, net_obj)


def main():
    board = pcbnew.LoadBoard(PCB)
    nets = collect_pads_by_net(board)

    n_power_stub = 0
    n_power_trace = 0
    n_signal_route = 0

    for net_name, pads in nets.items():
        if len(pads) < 2: continue
        # Skip pads that already have a track endpoint at their position
        unrouted = [p for p in pads if not p['has_track']]
        if not unrouted: continue

        if net_name in GND_NETS or net_name in VMOTOR_NETS:
            # Plane-stitch: stub trace + via for each unrouted pad
            for pad in unrouted:
                stub_via_route(board, pad, find_net(board, net_name))
                n_power_stub += 1
        elif net_name in POWER_TRACE_NETS:
            # No dedicated plane; route greedily from each unrouted pad to
            # nearest already-routed pad (or first pad)
            routed = [p for p in pads if p['has_track']]
            for pad in unrouted:
                if routed:
                    # Find nearest routed
                    nearest = min(routed,
                                  key=lambda r: math.hypot(r['x'] - pad['x'],
                                                           r['y'] - pad['y']))
                    if math.hypot(nearest['x'] - pad['x'],
                                  nearest['y'] - pad['y']) <= 15.0:
                        route_pad_pair(board, pad, nearest,
                                       find_net(board, net_name),
                                       width=W_POWER_TRACE)
                        n_power_trace += 1
                        # Add this pad to routed list
                        routed.append({**pad, 'has_track': True})
                        continue
                # No routed yet — pair to next unrouted (MST)
                others = [p for p in unrouted if p is not pad]
                if not others: continue
                nearest = min(others,
                              key=lambda r: math.hypot(r['x'] - pad['x'],
                                                       r['y'] - pad['y']))
                if math.hypot(nearest['x'] - pad['x'],
                              nearest['y'] - pad['y']) <= 15.0:
                    route_pad_pair(board, pad, nearest,
                                   find_net(board, net_name),
                                   width=W_POWER_TRACE)
                    n_power_trace += 1
                    routed.append({**pad, 'has_track': True})
                    routed.append({**nearest, 'has_track': True})
        else:
            # Channel-internal or other signal net
            # Sort by ref + pad for deterministic ordering
            up = sorted(unrouted, key=lambda p: (p['ref'], p['pad']))
            # Pair adjacent in sorted order, route as L-shape
            for i in range(len(up) - 1):
                pa = up[i]; pb = up[i + 1]
                d = math.hypot(pa['x'] - pb['x'], pa['y'] - pb['y'])
                if d > 30: continue  # too far, skip
                route_pad_pair(board, pa, pb, find_net(board, net_name),
                               width=W_SIG)
                n_signal_route += 1

    board.Save(PCB)
    print(f"Power stub-vias: {n_power_stub}")
    print(f"Power trace routes: {n_power_trace}")
    print(f"Signal routes: {n_signal_route}")


if __name__ == "__main__":
    main()
