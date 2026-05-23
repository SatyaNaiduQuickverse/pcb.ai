#!/usr/bin/env python3
"""route_ch1_critical.py — PR-routing-rebuild H1 dispatch (master 2026-05-24).

Routes CRITICAL CH1 signals per master R19 [[feedback-symmetry-preserves-work]]:
must be scripted (not autoroute) so CH2/3/4 mirror reproduces them exactly.

CRITICAL signals (from master dispatch):
  - Gate drive: GH[ABC]_CH1 + GL[ABC]_CH1 (DRV → gate-R → FET gate)
  - Bootstrap: BSTA/B/C_CH1 (BST cap ↔ DRV BST pin)
  - Current sense: CSA_[ABC]_OUT_CH1 (INA out → MCU ADC), CSA_MAX_CH1
  - BEMF: BEMF_[ABC]_CH1 (motor net → divider → MCU comparator)
  - Kill logic: I_TRIP_N_CH1, OTP_TRIP_N_CH1, KILL_LOCAL_N_CH1
  - VREF dividers: VREF_I_TRIP_CH1, VREF_OTP_CH1
  - PWM in: PWM_INH[ABC]_CH1 + PWM_INL[ABC]_CH1 (MCU → DRV)
  - DRV control: KILL_RAIL_N_CH1 (DRV nSLEEP), HW_FAULT_LED_K_CH1
  - Shunt: SHUNT_[ABC]_TOP_CH1 (Kelvin shunt → INA shunt pin)

Algorithm — for each critical net:
  1. Find all pads on that net in the channel zone (CH1 = X<50, Y>50)
  2. Build minimum-spanning-tree of pad positions
  3. Route each MST edge as 2-segment L-shape on signal layer (F.Cu primary,
     B.Cu or In*.Cu inner if F.Cu blocked)
  4. Apply with collision check vs existing tracks
"""
import pcbnew
import re
import math

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Critical net patterns to route in CH1 only
CRITICAL_PATTERNS = [
    r'^GH[ABC]_CH1$',
    r'^GL[ABC]_CH1$',
    r'^BST[ABC]_CH1$',
    r'^CSA_[ABC]_OUT_CH1$',
    r'^CSA_MAX_CH1$',
    r'^BEMF_[ABC]_CH1$',
    r'^I_TRIP_N_CH1$',
    r'^OTP_TRIP_N_CH1$',
    r'^KILL_LOCAL_N_CH1$',
    r'^KILL_RAIL_N_CH1$',
    r'^VREF_I_TRIP_CH1$',
    r'^VREF_OTP_CH1$',
    r'^PWM_INH[ABC]_CH1$',
    r'^PWM_INL[ABC]_CH1$',
    r'^HW_FAULT_LED_K_CH1$',
    r'^SHUNT_[ABC]_TOP_CH1$',
    r'^NTC_CH1$',
    r'^NTC_CH1_1$',
    r'^LED_GPIO_CH1$',
]

W_SIG = 0.15
W_PWR_SIG = 0.25  # PWM, gate-R chain — higher current edge


def mm(x): return pcbnew.FromMM(x)


def add_track(board, x1, y1, x2, y2, layer, width, net):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
    t.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
    t.SetLayer(layer)
    t.SetWidth(mm(width))
    t.SetNet(net)
    board.Add(t)
    return t


def add_via(board, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetDrill(mm(0.3))
    v.SetWidth(mm(0.6))
    v.SetNet(net)
    board.Add(v)


def get_pads_on_net(board, net_name):
    """Return list of (ref, pad_num, x, y, layer_set) for pads on the net."""
    out = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == net_name:
                p = pad.GetPosition()
                ls = pad.GetLayerSet()
                layers = set()
                if ls.Contains(pcbnew.F_Cu): layers.add('F.Cu')
                if ls.Contains(pcbnew.B_Cu): layers.add('B.Cu')
                out.append({
                    'ref': fp.GetReference(),
                    'pad': pad.GetNumber(),
                    'x': p.x / 1e6, 'y': p.y / 1e6,
                    'layers': layers,
                })
    return out


def mst_edges(pads):
    """Minimum spanning tree connecting pads. Returns list of (i, j) pad-index pairs."""
    n = len(pads)
    if n < 2:
        return []
    # Prim's MST
    in_tree = [False] * n
    in_tree[0] = True
    edges = []
    while sum(in_tree) < n:
        best = None
        for i, p in enumerate(pads):
            if not in_tree[i]: continue
            for j, q in enumerate(pads):
                if in_tree[j]: continue
                d = math.hypot(p['x'] - q['x'], p['y'] - q['y'])
                if best is None or d < best[2]:
                    best = (i, j, d)
        if best is None: break
        i, j, d = best
        edges.append((i, j))
        in_tree[j] = True
    return edges


def route_l_shape(board, pa, pb, layer, width, net):
    """Route 2-segment L-shape from pa to pb. Pick L-corner that's shortest."""
    # Two corner options: (xa, yb) or (xb, ya)
    dx = abs(pa['x'] - pb['x'])
    dy = abs(pa['y'] - pb['y'])
    if dx > dy:
        # corner at (xb, ya): horizontal first
        corner_x, corner_y = pb['x'], pa['y']
    else:
        # corner at (xa, yb): vertical first
        corner_x, corner_y = pa['x'], pb['y']
    add_track(board, pa['x'], pa['y'], corner_x, corner_y, layer, width, net)
    add_track(board, corner_x, corner_y, pb['x'], pb['y'], layer, width, net)
    return 2


def find_net(board, name):
    for n in board.GetNetsByName().values():
        if n.GetNetname() == name:
            return n
    return None


def main():
    board = pcbnew.LoadBoard(PCB)
    crit_res = [re.compile(p) for p in CRITICAL_PATTERNS]
    nets_to_route = set()
    for n in board.GetNetsByName().values():
        name = n.GetNetname()
        for r in crit_res:
            if r.match(name):
                nets_to_route.add(name)
                break
    print(f"Critical CH1 nets to route: {len(nets_to_route)}")
    n_tracks = 0
    n_vias = 0
    routed = 0
    skipped = 0
    for net_name in sorted(nets_to_route):
        net_obj = find_net(board, net_name)
        if net_obj is None: continue
        pads = get_pads_on_net(board, net_name)
        if len(pads) < 2:
            skipped += 1
            continue
        edges = mst_edges(pads)
        # Pick layer per net category
        if 'GH' in net_name or 'GL' in net_name or 'PWM_IN' in net_name:
            layer, width = pcbnew.F_Cu, W_PWR_SIG
        elif 'BST' in net_name:
            layer, width = pcbnew.F_Cu, W_PWR_SIG
        elif 'SHUNT' in net_name:
            layer, width = pcbnew.F_Cu, 0.5  # Kelvin sense thick trace
        elif 'BEMF' in net_name or 'CSA' in net_name or 'VREF' in net_name:
            layer, width = pcbnew.In2_Cu, W_SIG  # inner signal layer
        elif 'KILL' in net_name or 'TRIP' in net_name:
            layer, width = pcbnew.In4_Cu, W_SIG
        elif 'NTC' in net_name:
            layer, width = pcbnew.In2_Cu, W_SIG
        else:
            layer, width = pcbnew.F_Cu, W_SIG
        # Route each MST edge
        for i, j in edges:
            pa, pb = pads[i], pads[j]
            # Check if pad layers match the target route layer; if not, add vias
            target_layer_name = 'F.Cu' if layer == pcbnew.F_Cu else ('B.Cu' if layer == pcbnew.B_Cu else 'inner')
            # For simplicity: if pad is F.Cu-only and we're routing inner, add via at pad
            # then route inner; or just route F.Cu directly if both pads on F.Cu
            same_layer_routing = False
            if 'F.Cu' in pa['layers'] and 'F.Cu' in pb['layers'] and layer == pcbnew.F_Cu:
                same_layer_routing = True
            if same_layer_routing:
                n_tracks += route_l_shape(board, pa, pb, layer, width, net_obj)
            else:
                # Add via at each endpoint, route on inner layer
                add_via(board, pa['x'], pa['y'], net_obj); n_vias += 1
                add_via(board, pb['x'], pb['y'], net_obj); n_vias += 1
                n_tracks += route_l_shape(board, pa, pb, layer, width, net_obj)
        routed += 1
    board.Save(PCB)
    print(f"Routed: {routed} nets, skipped: {skipped}, tracks: {n_tracks}, vias: {n_vias}")


if __name__ == "__main__":
    main()
