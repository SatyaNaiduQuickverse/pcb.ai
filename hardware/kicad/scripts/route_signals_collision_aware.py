#!/usr/bin/env python3
"""route_signals_collision_aware.py — PR-routing-final G2 Phase B.

Routes remaining ~471 unconnected pad-pairs after Phase A power-stitch:
  - ~163 non-plane power (+3V3/+3V3A/+V5_*/+V9_*) — trace routing
  - ~100 MOTOR_X_CHn FET-source-to-INA Kelvin paths
  - ~32 CSA_X/CSA_MAX channel-internal signals
  - ~50 BEMF/SHUNT/gate-drive
  - ~80 PWM/KILL/VREF/NTC per-channel control
  - 28 GND/BATGND residual (no clean via spot)

Strategy:
  1. For each net with ≥2 unconnected pads, build MST by Euclidean distance
  2. For each MST edge: try L-shape on F.Cu / B.Cu / In2.Cu / In4.Cu
  3. Pre-route collision check: candidate trace segments must not intersect
     any existing pad bbox of a DIFFERENT net on the same layer
  4. Width by net class (auto-lookup from net name pattern)
  5. For per-channel _CHn nets: route CH1 first (CH2/3/4 mirrored later)
  6. After all routing: ZONE_FILLER save-reload-fill-save (per
     [[reference-pcbnew-zone-filler-save-pattern]])

Master 2026-05-24 G2 Phase B dispatch + collision-aware + topology-aware
+ net-pattern-aware refinements.
"""
import pcbnew
import re
import math
from collections import defaultdict

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Width by net pattern (regex → mm). First match wins.
WIDTH_RULES = [
    (re.compile(r'^MOTOR_[ABC]_CH\d+$'), 1.0),
    (re.compile(r'^SHUNT_[ABC]_TOP_CH\d+$'), 1.0),
    (re.compile(r'^\+?VMOTOR'), 1.0),  # +VMOTOR / VMOTOR_CH / VMOTOR_HALL_HI/LO
    (re.compile(r'^V_BUCK\d_(OUT|SW)$'), 0.4),
    (re.compile(r'^BUCK\d_(BST|FB|SW)$'), 0.3),
    (re.compile(r'^\+V5'), 0.3),
    (re.compile(r'^\+V9'), 0.3),
    (re.compile(r'^V9_VTX\d_PROTECT_OUT$'), 0.3),
    (re.compile(r'^HALL_VCC_5V$'), 0.3),
    (re.compile(r'^\+3V3'), 0.25),
    (re.compile(r'^BATGND$|^GND$'), 0.4),
    # signals (default 0.15)
]
DEFAULT_WIDTH = 0.15

# Per-channel net suffix (CH1 first, CH2/3/4 will be mirrored later)
PER_CHANNEL_RE = re.compile(r'_CH(\d+)$')

# Don't try to route these (handled in plane-stitch or already-routed)
SKIP_NETS = set()  # e.g., 'GND' if we want plane to handle. But we want stub routes for remaining.


def find_net(board, name):
    for n in board.GetNetsByName().values():
        if n.GetNetname() == name:
            return n
    return None


def width_for_net(name):
    for pat, w in WIDTH_RULES:
        if pat.match(name):
            return w
    return DEFAULT_WIDTH


def collect_pads_and_tracks(board):
    """Return:
      pads_by_net: net → list of pad dicts (ref, pad, x, y, layers, has_route)
      pad_bboxes_by_layer: layer ('F'/'B') → list of (net, x0, y0, x1, y1, ref)
      track_endpoints: set of (net, round(x,2), round(y,2)) for pad-served-by-track lookup
    """
    pads_by_net = defaultdict(list)
    pad_bboxes_by_layer = {'F': [], 'B': []}
    track_endpoints = set()

    for t in board.GetTracks():
        n = t.GetNetname()
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            track_endpoints.add((n, round(p.x / 1e6, 2), round(p.y / 1e6, 2)))
        else:
            for p in (t.GetStart(), t.GetEnd()):
                track_endpoints.add((n, round(p.x / 1e6, 2), round(p.y / 1e6, 2)))

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net_obj = pad.GetNet()
            if net_obj is None: continue
            net_name = net_obj.GetNetname()
            if not net_name: continue
            p = pad.GetPosition()
            x = round(p.x / 1e6, 2)
            y = round(p.y / 1e6, 2)
            ls = pad.GetLayerSet()
            layers = []
            if ls.Contains(pcbnew.F_Cu): layers.append('F')
            if ls.Contains(pcbnew.B_Cu): layers.append('B')
            if not layers: continue
            has_route = (net_name, x, y) in track_endpoints
            bb = pad.GetBoundingBox()
            x0 = pcbnew.ToMM(bb.GetLeft()); y0 = pcbnew.ToMM(bb.GetTop())
            x1 = pcbnew.ToMM(bb.GetRight()); y1 = pcbnew.ToMM(bb.GetBottom())
            entry = {
                'ref': fp.GetReference(),
                'pad': pad.GetPadName(),
                'x': x, 'y': y,
                'layers': layers,
                'bbox': (x0, y0, x1, y1),
                'has_route': has_route,
                'net': net_name,
            }
            pads_by_net[net_name].append(entry)
            for lay in layers:
                pad_bboxes_by_layer[lay].append({
                    'net': net_name, 'ref': fp.GetReference(),
                    'pad': pad.GetPadName(),
                    'bbox': (x0, y0, x1, y1),
                })
    return pads_by_net, pad_bboxes_by_layer, track_endpoints


def segment_intersects_bbox(x1, y1, x2, y2, w, bbox, tol=0.1):
    """Check if a track segment (x1,y1)→(x2,y2) of width w intersects bbox."""
    bx0, by0, bx1, by1 = bbox
    # Inflate bbox by half-width + tol
    bx0 -= w/2 + tol; by0 -= w/2 + tol
    bx1 += w/2 + tol; by1 += w/2 + tol
    # Segment bbox vs rect-bbox check (axis-aligned segments only)
    sx0, sx1 = min(x1, x2), max(x1, x2)
    sy0, sy1 = min(y1, y2), max(y1, y2)
    if sx1 < bx0 or sx0 > bx1: return False
    if sy1 < by0 or sy0 > by1: return False
    return True


def segment_collides(x1, y1, x2, y2, layer_str, width, exclude_net,
                     exclude_refs, pad_bboxes_by_layer):
    """True if segment collides with any pad of a different net on same layer."""
    for p in pad_bboxes_by_layer.get(layer_str, []):
        if p['net'] == exclude_net: continue
        if p['ref'] in exclude_refs: continue
        if segment_intersects_bbox(x1, y1, x2, y2, width, p['bbox']):
            return p['ref']
    return None


def try_l_shape(pa, pb, layer_str, width, exclude_net, exclude_refs, pads_idx):
    """Return (corner_x, corner_y) if an L-shape route works on this layer, else None.
    Two corner options: (pb.x, pa.y) or (pa.x, pb.y). Try each."""
    for corner in [(pb['x'], pa['y']), (pa['x'], pb['y'])]:
        cx, cy = corner
        c1 = segment_collides(pa['x'], pa['y'], cx, cy, layer_str, width,
                              exclude_net, exclude_refs, pads_idx)
        if c1: continue
        c2 = segment_collides(cx, cy, pb['x'], pb['y'], layer_str, width,
                              exclude_net, exclude_refs, pads_idx)
        if c2: continue
        return (cx, cy)
    return None


def add_track(board, x1, y1, x2, y2, layer, width, net):
    if abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01:
        return None
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
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    v.SetDrill(pcbnew.FromMM(0.3))
    v.SetWidth(pcbnew.FromMM(0.6))
    v.SetNet(net)
    board.Add(v)


def mst_edges(pads):
    """Prim's MST edges by Euclidean distance."""
    n = len(pads)
    if n < 2: return []
    in_tree = [False] * n
    in_tree[0] = True
    edges = []
    while sum(in_tree) < n:
        best = None
        for i in range(n):
            if not in_tree[i]: continue
            for j in range(n):
                if in_tree[j]: continue
                d = math.hypot(pads[i]['x'] - pads[j]['x'],
                                pads[i]['y'] - pads[j]['y'])
                if best is None or d < best[2]:
                    best = (i, j, d)
        if best is None: break
        i, j, _ = best
        edges.append((i, j))
        in_tree[j] = True
    return edges


def main():
    board = pcbnew.LoadBoard(PCB)
    pads_by_net, pad_bboxes_by_layer, track_endpoints = collect_pads_and_tracks(board)

    n_routed = 0
    n_skipped_no_layer = 0
    n_skipped_collision = 0

    layer_map = {'F': pcbnew.F_Cu, 'B': pcbnew.B_Cu,
                 'In2': pcbnew.In2_Cu, 'In4': pcbnew.In4_Cu}

    for net_name, pads in pads_by_net.items():
        if net_name in SKIP_NETS: continue
        if len(pads) < 2: continue
        # For per-channel nets: route only CH1 (others will mirror)
        m = PER_CHANNEL_RE.search(net_name)
        if m and int(m.group(1)) != 1:
            continue
        # Build MST over ALL pads (including routed ones — they're anchors)
        # Then for each MST edge, only add tracks if BOTH endpoints are in the
        # unrouted set (or one endpoint already track-served = anchor)
        edges = mst_edges(pads)
        net_obj = find_net(board, net_name)
        if net_obj is None: continue
        w = width_for_net(net_name)

        for i, j in edges:
            pa = pads[i]; pb = pads[j]
            # If both already routed (track endpoint at both pad centers), skip
            # If one routed and one unrouted: we need this segment
            # If both unrouted: this MST edge brings them into connected graph
            if pa['has_route'] and pb['has_route']:
                continue
            # Distance gate: skip very long routes (>30mm)
            dist = math.hypot(pa['x'] - pb['x'], pa['y'] - pb['y'])
            if dist > 30: continue
            # Pick layer: F if both pads on F, else B if both on B, else try inner
            tried_layer = None
            corner = None
            for try_layer in ['F', 'B', 'In2', 'In4']:
                # Pad layer must include try_layer for F/B; via for inner
                if try_layer in ('F', 'B'):
                    if try_layer not in pa['layers'] or try_layer not in pb['layers']:
                        continue
                else:
                    pass  # inner layer requires vias at endpoints
                c = try_l_shape(pa, pb, try_layer if try_layer in ('F', 'B') else 'F',
                                w, net_name, {pa['ref'], pb['ref']},
                                pad_bboxes_by_layer)
                if c is not None:
                    tried_layer = try_layer
                    corner = c
                    break
            if corner is None:
                n_skipped_collision += 1
                continue
            # Apply routes
            layer = layer_map[tried_layer]
            cx, cy = corner
            if tried_layer in ('In2', 'In4'):
                add_via(board, pa['x'], pa['y'], net_obj)
                add_via(board, pb['x'], pb['y'], net_obj)
            add_track(board, pa['x'], pa['y'], cx, cy, layer, w, net_obj)
            add_track(board, cx, cy, pb['x'], pb['y'], layer, w, net_obj)
            # Mark these pads as routed for downstream MST decisions
            pa['has_route'] = True
            pb['has_route'] = True
            n_routed += 1

    print(f"Routed: {n_routed} MST edges")
    print(f"Skipped (no compatible layer): {n_skipped_no_layer}")
    print(f"Skipped (collision): {n_skipped_collision}")

    print("Saving routes...")
    board.Save(PCB)
    print("Reload + zone-fill refresh...")
    board = pcbnew.LoadBoard(PCB)
    zones = [z for z in board.Zones()]
    try:
        pcbnew.ZONE_FILLER(board).Fill(zones)
        board.Save(PCB)
        print(f"Zones refilled ({len(zones)} zones). Saved.")
    except Exception as e:
        print(f"Zone-fill error: {e}")


if __name__ == "__main__":
    main()
