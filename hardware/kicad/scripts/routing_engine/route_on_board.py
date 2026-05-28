#!/usr/bin/env python3
"""route_on_board.py — live-board harness wrapping routing_engine.maze_router.

Bridges maze_router.route() to a real .kicad_pcb. For each net in --nets,
extracts pins + obstacles from the board, calls route() per pin-pair
(star-from-root for multi-pin), and emits the result via direct pcbnew calls
(PCB_TRACK + PCB_VIA with the correct via_type + layer_pair + drill + per-layer
width — emit_to_kicad in geometry_primitives is incomplete for vias).

Why this exists
---------------
maze_router.solve() handles T13 fixture only; phase_c._fill_escape is
intentionally no-route ("heroic_route_attempted: False", §0b T9 honesty test);
run_on_board.py is verdict-only. Wire-laying needs glue between the maze
primitives and a live board — that glue is this file (Phase 3 lever B per
master's GO, PR #227 follow-up).

Worker scope (lever B): single-layer F.Cu routes for GLB / KILL_RAIL_N + a
through-via at destination (for B.Cu destinations). The 4 OQ-020 blind-F-In2
nets stay with the cooperative router (lever A, master-domain patch).

Constraints honored
-------------------
- maze_router obstacles are layer-agnostic → the harness IS the per-layer
  filter (pass only foreign copper on the configured routing layers).
- Via emission: explicit pcbnew via_type + layer_pair + drill + width per class
  (the maze router gives us via_class + from_layer + to_layer; we map them
  to pcbnew attributes from BOARD_INVARIANTS / DRU).
- clearance_fos: 0.20mm above JLC fab min (§5c "above fab min, never at it").
- grid_pitch: 0.10mm default (HDI fab pitch ballpark + maze router default).
- No plane_split obstacles in MVP (planes continuous in CH1 per engine §6).
- No heroic re-route on NotRoutable; verdict carried forward verbatim in the
  per-net report row (ROUTING_METHODOLOGY §0b).
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# Self-import so the module works as a script OR as a package import (run_suite).
try:
    from .maze_router import (Obstacle, Pin, Route, Via as MazeVia, Segment,
                              NotRoutable, route, LAYER_STACK, VIA_CLASSES)
except ImportError:  # loose-script invocation
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from maze_router import (Obstacle, Pin, Route, Via as MazeVia, Segment,  # type: ignore
                             NotRoutable, route, LAYER_STACK, VIA_CLASSES)

# ─── via-class → fab geometry (BOARD_INVARIANTS + pcbai_fpv4in1.kicad_dru) ───
#
# Maze router emits via_class ∈ {"through","microvia","blind","stacked"}.
# Map each to (drill_mm, pad_mm). The DRU has explicit rules:
#   * standard non-HDI via:     drill 0.30, pad 0.60     (the board default)
#   * HDI microvia F↔In1 or B↔In8: drill 0.10, pad 0.25
#   * HDI blind F↔In2 (OQ-020): drill 0.15, pad 0.25     (whitelist 4 nets)
#
# For other blind classes (rare here) we default to the standard blind 0.15/0.25
# which matches the OQ-020 entry — JLC HDI Class 2 floor.
VIA_GEOM_MM: Dict[str, Tuple[float, float]] = {
    "through":  (0.30, 0.60),
    "microvia": (0.10, 0.25),
    "blind":    (0.15, 0.25),
    "stacked":  (0.10, 0.25),    # treated as adjacent microvia stack geometry
}

# ─── per-net routing config (caller-overridable; defaults from master's GO) ──
#
# Each entry: dict with
#   route_layers         : tuple of canonical KiCad layer names the maze may
#                          use. route_layers[0] is the PRIMARY — both pins are
#                          placed there for the maze; the maze may transit via
#                          via_classes to extras. obstacles are extracted from
#                          THIS set only (the maze itself is layer-agnostic so
#                          this is our per-layer filter).
#   via_classes          : in-route via classes (passed as allowed_via_classes)
#                          for layer transitions during the search. Empty tuple
#                          = single-layer route.
#   stitch_via_class     : added at any endpoint whose native pad layer differs
#                          from route_layers[0]. "" or None to skip.
#   width_mm             : trace width
#   clearance_fos_mm     : clearance above fab min (§5c)
#   grid_pitch_mm        : signal grid pitch
#   expansion_cap        : A* node cap (NotRoutable on excess)
#
# Anything not in NET_CONFIG falls back to DEFAULT_NET_CONFIG.
DEFAULT_NET_CONFIG = {
    "route_layers":       ("F.Cu",),
    "via_classes":        (),
    "stitch_via_class":   "through",
    "width_mm":           0.20,
    "clearance_fos_mm":   0.20,
    "grid_pitch_mm":      0.10,
    "expansion_cap":      200_000,
}

NET_CONFIG: Dict[str, dict] = {
    # Master GO Phase 3: GLB long path J19.10 → R50.1 (B.Cu). F.Cu primary +
    # In8 (the under-used "overflow" layer per master) as a relief lane via
    # in-route through-vias; one stitch through-via at R50.1.
    "GLB_CH1": {
        "route_layers":      ("F.Cu", "In8.Cu"),
        "via_classes":       ("through",),
        "stitch_via_class":  "through",
        "width_mm":          0.20,
        "clearance_fos_mm":  0.20,
        "grid_pitch_mm":     0.10,
        "expansion_cap":     500_000,
    },
    # KILL_RAIL_N: F.Cu try first (master); In8 as escape relief; 4 pads — star
    # J19.8 → each B.Cu pad, stitch through-via at each destination.
    "KILL_RAIL_N_CH1": {
        "route_layers":      ("F.Cu", "In8.Cu"),
        "via_classes":       ("through",),
        "stitch_via_class":  "through",
        "width_mm":          0.20,
        "clearance_fos_mm":  0.20,
        "grid_pitch_mm":     0.10,
        "expansion_cap":     500_000,
    },
}

# Subsystem zones (mirror of BOARD_INVARIANTS + the engine assumption set).
SUBSYSTEM_ZONES: Dict[str, Tuple[float, float, float, float]] = {
    "CH1": (0.0, 50.0, 35.0, 89.0),
    # CH2/3/4 cascade after STEP-8 PR; not relevant for Phase 3 graduation.
}

REGION_MARGIN_MM = 2.0   # maze_router.solve() pattern


# ─── pcbnew binding (lazy; pure-python fallback for tests) ───────────────────
#
# Layer-name translation: a board may RENAME its layers ("F.Cu 1oz — HS FETs,
# MCU pads, drivers, connectors") but the integer layer IDs are stable. The
# maze router operates on CANONICAL KiCad layer names (the LAYER_STACK
# constant); we translate at every pcbnew⇄maze boundary using these maps.
def _import_pcbnew():
    """Lazy import — keeps the harness importable on master env (no pcbnew)."""
    import pcbnew  # type: ignore
    return pcbnew


def _maze_name_to_pcb_id_map():
    """Build {canonical name → pcbnew layer ID} on first call. Lazy because
    pcbnew may be absent at import time on the master env."""
    pcbnew = _import_pcbnew()
    return {
        "F.Cu":   pcbnew.F_Cu,
        "In1.Cu": pcbnew.In1_Cu,
        "In2.Cu": pcbnew.In2_Cu,
        "In3.Cu": pcbnew.In3_Cu,
        "In4.Cu": pcbnew.In4_Cu,
        "In5.Cu": pcbnew.In5_Cu,
        "In6.Cu": pcbnew.In6_Cu,
        "In7.Cu": pcbnew.In7_Cu,
        "In8.Cu": pcbnew.In8_Cu,
        "B.Cu":   pcbnew.B_Cu,
    }


def _pcb_id_to_maze_name_map():
    return {v: k for k, v in _maze_name_to_pcb_id_map().items()}


# ─── data extraction from a live board ───────────────────────────────────────
@dataclass
class PadInfo:
    ref: str                          # footprint reference (J18, J19, R50, …)
    name: str                         # pad name ("10", "1", …)
    netname: str
    x_mm: float
    y_mm: float
    layers: Tuple[str, ...]           # KiCad layer name strings the pad sits on
    bbox: Tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max) — rotated


def _pad_bbox_mm(pad) -> Tuple[float, float, float, float]:
    """Rotation-aware bounding box in mm (KiCad provides this directly)."""
    bb = pad.GetBoundingBox()
    return (bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
            bb.GetRight() / 1e6, bb.GetBottom() / 1e6)


def _pad_layers(pad, board) -> Tuple[str, ...]:
    """Copper layers a pad sits on, as CANONICAL maze layer names.

    The board may RENAME its layers (a 10L board often suffixes user purpose).
    We translate by layer ID — stable — to the canonical KiCad names the maze
    router speaks (LAYER_STACK)."""
    id_to_maze = _pcb_id_to_maze_name_map()
    layers: List[str] = []
    ls = pad.GetLayerSet()
    for lid in ls.CuStack():
        canonical = id_to_maze.get(lid)
        if canonical is not None:
            layers.append(canonical)
    return tuple(layers)


def _hdi_whitelisted_ref(ref: str) -> bool:
    """The cooperative router's HDI whitelist (BOARD_INVARIANTS): J18 + J19 only.
    For maze-router routing we use this as a hint on the Pin (informational —
    the harness here does not auto-emit blind F-In2 for these; that's lever A,
    the cooperative-router patch's job)."""
    return ref in ("J18", "J19")


def extract_pads(board, netnames: Sequence[str]) -> Dict[str, List[PadInfo]]:
    """Group pads on the requested nets by netname."""
    out: Dict[str, List[PadInfo]] = {n: [] for n in netnames}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn not in out:
                continue
            pos = p.GetPosition()
            out[nn].append(PadInfo(
                ref=ref, name=p.GetPadName(), netname=nn,
                x_mm=pos.x / 1e6, y_mm=pos.y / 1e6,
                layers=_pad_layers(p, board),
                bbox=_pad_bbox_mm(p),
            ))
    return out


def extract_obstacles(board, layers: Sequence[str],
                      exclude_net: str = "") -> List[Obstacle]:
    """Foreign copper on the given layers, expressed as 'body' Obstacles.

    Maze router obstacles are layer-AGNOSTIC; this function IS the per-layer
    filter — only items whose layer is in `layers` produce an obstacle.

      foreign pads (on a layer in `layers`)  → AABB obstacle (pad bbox)
      foreign tracks (on a layer in `layers`) → AABB obstacle (segment bbox
                                                inflated by half-width)
      foreign vias (always)                   → AABB obstacle (square around
                                                via center; through vias span
                                                every layer)

    The maze router's _swept_track_clears uses the EXACT segment-AABB min
    distance (not just AABB containment), so inflated AABBs over-block by at
    most the AABB-vs-segment slop — safe on the conservative side.
    """
    obstacles: List[Obstacle] = []
    layer_set = set(layers)
    name_to_id = _maze_name_to_pcb_id_map()
    layer_ids = {name_to_id[L] for L in layers if L in name_to_id}

    # foreign pads on the allowed layers
    for fp in board.GetFootprints():
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn == exclude_net and nn != "":
                continue
            pad_layers = set(_pad_layers(p, board))
            if not (pad_layers & layer_set):
                continue
            l, t, r, b = _pad_bbox_mm(p)
            obstacles.append(Obstacle(x_min=l, y_min=t, x_max=r, y_max=b,
                                      kind="body"))

    # tracks + vias
    pcbnew = _import_pcbnew()
    for tk in board.GetTracks():
        if tk.GetNetname() == exclude_net and exclude_net != "":
            continue
        if tk.GetClass() == "PCB_VIA":
            # vias span multiple layers — block on any allowed-layer route.
            pos = tk.GetPosition()
            try:
                width = tk.GetWidth(pcbnew.F_Cu) / 1e6   # KiCad 9: per-layer width
            except Exception:
                width = 0.60                              # fallback to default via pad
            r = width / 2.0
            x = pos.x / 1e6; y = pos.y / 1e6
            obstacles.append(Obstacle(x_min=x - r, y_min=y - r,
                                      x_max=x + r, y_max=y + r, kind="body"))
        else:
            tk_lid = tk.GetLayer()
            if tk_lid not in layer_ids:
                continue
            s = tk.GetStart(); e = tk.GetEnd()
            sx, sy = s.x / 1e6, s.y / 1e6
            ex, ey = e.x / 1e6, e.y / 1e6
            half = (tk.GetWidth() / 2.0) / 1e6
            x_min = min(sx, ex) - half; x_max = max(sx, ex) + half
            y_min = min(sy, ey) - half; y_max = max(sy, ey) + half
            obstacles.append(Obstacle(x_min=x_min, y_min=y_min,
                                      x_max=x_max, y_max=y_max, kind="body"))

    return obstacles


# ─── per-net routing (star-from-root MST) ────────────────────────────────────
@dataclass
class NetResult:
    netname: str
    status: str                # "ROUTED" | "PARTIAL" | "NOT-ROUTABLE" | "SKIPPED"
    n_segments: int
    n_vias: int
    length_mm: float
    via_classes: Tuple[str, ...]
    routed_edges: int
    total_edges: int
    routes: List[Route] = field(default_factory=list)
    failure_reason: Optional[str] = None
    failed_pin_pair: Optional[Tuple[str, str]] = None


def _pad_to_pin(p: PadInfo, routing_layer: str) -> Pin:
    """Build a maze Pin at the pad's xy, placed on the routing layer.

    The maze runs SINGLE-LAYER (obstacles are layer-agnostic — would over-block
    if we tried multi-layer). If the pad's actual layer ≠ routing_layer, the
    harness emits a stitching via at the destination point post-route.
    """
    return Pin(point=(p.x_mm, p.y_mm), layer=routing_layer,
               is_hdi_whitelisted=_hdi_whitelisted_ref(p.ref))


def _pad_needs_stitch(p: PadInfo, routing_layer: str) -> bool:
    """True iff the pad sits on a layer DIFFERENT from the routing layer —
    we'll need a stitching via from routing_layer to the pad's native layer."""
    return routing_layer not in p.layers


def _region_bbox(pads: Sequence[PadInfo], zone: Tuple[float, float, float, float],
                 margin: float) -> Tuple[float, float, float, float]:
    """Region = pin-bounding rect clamped to the subsystem zone + margin."""
    if not pads:
        return zone
    xs = [p.x_mm for p in pads]; ys = [p.y_mm for p in pads]
    x_min = max(zone[0], min(xs) - margin)
    y_min = max(zone[1], min(ys) - margin)
    x_max = min(zone[2], max(xs) + margin)
    y_max = min(zone[3], max(ys) + margin)
    # If the pin-bbox is degenerate (single point), widen to at least 2×margin.
    if x_max - x_min < 2 * margin:
        cx = (x_min + x_max) / 2
        x_min, x_max = max(zone[0], cx - margin), min(zone[2], cx + margin)
    if y_max - y_min < 2 * margin:
        cy = (y_min + y_max) / 2
        y_min, y_max = max(zone[1], cy - margin), min(zone[3], cy + margin)
    return (x_min, y_min, x_max, y_max)


def _mst_pairs(root: PadInfo, others: Sequence[PadInfo]) -> List[Tuple[PadInfo, PadInfo]]:
    """STAR topology pairs (root → each other). For a 2-pad net this is just
    (root, others[0]). For N-pad it's (root, p_i) for each i — a star tree.

    Star is simpler than full MST and guarantees connectivity (all pads share
    the root point). Future enhancement: real MST with already-routed segments
    as 'own-net' free space so subsequent legs can attach to nearer points;
    for the Phase 3 graduation (KILL_RAIL_N's 4 pads, GLB's 2 pads) star is
    sufficient (the root J19.x sits central enough)."""
    return [(root, p) for p in others]


def route_net(board, net: str, pads: Sequence[PadInfo],
              config: dict, zone: Tuple[float, float, float, float]) -> NetResult:
    """Route one net via maze_router; return a NetResult.

    Single-layer routing on config['routing_layer'] (F.Cu by default). For
    destination pads on a different native layer, a stitching via of class
    config['stitch_via_class'] is added at the destination point post-route.
    """
    if len(pads) < 2:
        return NetResult(netname=net, status="SKIPPED",
                         n_segments=0, n_vias=0, length_mm=0.0,
                         via_classes=(), routed_edges=0, total_edges=0,
                         failure_reason="net has <2 pads")

    route_layers = tuple(config["route_layers"])
    primary_layer = route_layers[0]
    via_classes = tuple(config.get("via_classes", ()))
    stitch_class = config.get("stitch_via_class") or ""

    # Root selection: a pad on the primary layer is the natural root.
    root = next((p for p in pads if primary_layer in p.layers), pads[0])
    others = [p for p in pads if p is not root]
    pairs = _mst_pairs(root, others)

    # Obstacles only on the routing layers (vias still span all layers, so they
    # ARE included — see extract_obstacles).
    obstacles = extract_obstacles(board, route_layers, exclude_net=net)
    region = _region_bbox(pads, zone, REGION_MARGIN_MM)

    routes: List[Route] = []
    failure_reason: Optional[str] = None
    failed_pair: Optional[Tuple[str, str]] = None
    routed_edges = 0

    for src, dst in pairs:
        start = _pad_to_pin(src, primary_layer)
        end = _pad_to_pin(dst, primary_layer)
        try:
            r = route(start=start, end=end, region_bbox=region,
                      obstacles=obstacles,
                      allowed_layers=route_layers,
                      allowed_via_classes=via_classes,
                      width_mm=config["width_mm"],
                      clearance_fos_mm=config["clearance_fos_mm"],
                      expansion_cap=config["expansion_cap"],
                      grid_pitch_mm=config["grid_pitch_mm"])
        except NotRoutable as e:
            failure_reason = e.reason
            failed_pair = (f"{src.ref}.{src.name}", f"{dst.ref}.{dst.name}")
            break

        # If the destination is on a different native layer, stitch a via.
        # The maze's last-segment ends at dst.point on `primary_layer`; the
        # stitch via lands on the pad's actual layer.
        if stitch_class and _pad_needs_stitch(dst, primary_layer):
            dest_native = next((L for L in dst.layers if L != primary_layer),
                               dst.layers[0] if dst.layers else primary_layer)
            stitch = MazeVia(point=(dst.x_mm, dst.y_mm),
                             via_class=stitch_class,
                             from_layer=primary_layer,
                             to_layer=dest_native)
            r.vias.append(stitch)

        # Similarly for the SOURCE on the first pair only (rare — root usually
        # sits on the primary layer because we pick it that way above).
        if (routed_edges == 0 and stitch_class
                and _pad_needs_stitch(src, primary_layer)):
            src_native = next((L for L in src.layers if L != primary_layer),
                              src.layers[0] if src.layers else primary_layer)
            stitch = MazeVia(point=(src.x_mm, src.y_mm),
                             via_class=stitch_class,
                             from_layer=primary_layer,
                             to_layer=src_native)
            r.vias.append(stitch)

        routes.append(r)
        routed_edges += 1

    n_seg = sum(len(r.segments) for r in routes)
    n_via = sum(len(r.vias) for r in routes)
    length = sum(r.length_mm for r in routes)
    vc = tuple(sorted({v.via_class for r in routes for v in r.vias}))

    if routed_edges == len(pairs):
        status = "ROUTED"
    elif routed_edges > 0:
        status = "PARTIAL"
    else:
        status = "NOT-ROUTABLE"
    return NetResult(netname=net, status=status,
                     n_segments=n_seg, n_vias=n_via, length_mm=length,
                     via_classes=vc, routed_edges=routed_edges,
                     total_edges=len(pairs), routes=routes,
                     failure_reason=failure_reason,
                     failed_pin_pair=failed_pair)


# ─── pcbnew emission ─────────────────────────────────────────────────────────
def _vp(pt: Tuple[float, float], pcbnew):
    return pcbnew.VECTOR2I(pcbnew.FromMM(pt[0]), pcbnew.FromMM(pt[1]))


def _via_type_for_class(via_class: str, pcbnew):
    """Map maze-router via_class → pcbnew VIATYPE_*."""
    if via_class == "microvia":
        return pcbnew.VIATYPE_MICROVIA
    if via_class in ("blind", "stacked"):
        # KiCad models blind/buried under VIATYPE_BLIND_BURIED. A stacked-microvia
        # pair is emitted as two adjacent microvias — the maze router gives us
        # the from/to and we mark each as MICROVIA in that case (caller should
        # split into two vias if it wants a literal stack). Single blind via
        # spanning >1 layer pair uses BLIND_BURIED.
        return pcbnew.VIATYPE_BLIND_BURIED
    return pcbnew.VIATYPE_THROUGH


def emit_route_to_board(board, net_obj, routes: Sequence[Route]) -> Tuple[int, int]:
    """Add tracks + vias for one net's routes to the live board. Returns
    (n_tracks_added, n_vias_added). Sets net, layer, width, drill, via_type
    + per-layer width for vias (KiCad 9 SetWidth needs a layer)."""
    pcbnew = _import_pcbnew()
    name_to_id = _maze_name_to_pcb_id_map()
    n_tr = n_via = 0
    for r in routes:
        for seg in r.segments:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(_vp(seg.p1, pcbnew))
            t.SetEnd(_vp(seg.p2, pcbnew))
            t.SetWidth(pcbnew.FromMM(seg.width_mm))
            t.SetLayer(name_to_id[seg.layer])
            t.SetNet(net_obj)
            board.Add(t)
            n_tr += 1
        for v in r.vias:
            drill_mm, pad_mm = VIA_GEOM_MM.get(v.via_class, VIA_GEOM_MM["through"])
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(_vp(v.point, pcbnew))
            from_id = name_to_id[v.from_layer]
            to_id   = name_to_id[v.to_layer]
            via.SetLayerPair(from_id, to_id)
            via.SetDrill(pcbnew.FromMM(drill_mm))
            # KiCad 9: SetWidth(layer, width) — set on every Cu layer the via spans
            # (the maze gives us only the endpoints; the barrel spans all layers
            # between them in stackup order).
            try:
                i_from = LAYER_STACK.index(v.from_layer)
                i_to = LAYER_STACK.index(v.to_layer)
                lo, hi = (min(i_from, i_to), max(i_from, i_to))
                spanned = LAYER_STACK[lo:hi + 1]
                for L in spanned:
                    lid = name_to_id[L]
                    try:
                        via.SetWidth(lid, pcbnew.FromMM(pad_mm))
                    except TypeError:
                        # older KiCad: SetWidth(width) only
                        via.SetWidth(pcbnew.FromMM(pad_mm))
                        break
            except Exception:
                # absolute fallback
                via.SetWidth(pcbnew.FromMM(pad_mm))
            try:
                via.SetViaType(_via_type_for_class(v.via_class, pcbnew))
            except Exception:
                pass
            via.SetNet(net_obj)
            board.Add(via)
            n_via += 1
    return n_tr, n_via


# ─── top-level harness ───────────────────────────────────────────────────────
def run_harness(board_path: str, subsystem: str, nets: Sequence[str],
                output_path: str, report_path: Optional[str] = None,
                config_overrides: Optional[Dict[str, dict]] = None,
                ) -> List[NetResult]:
    """Load the board, route the requested nets, save to output_path."""
    pcbnew = _import_pcbnew()
    board = pcbnew.LoadBoard(board_path)
    if subsystem not in SUBSYSTEM_ZONES:
        raise ValueError(f"unknown subsystem {subsystem!r}; "
                         f"add it to SUBSYSTEM_ZONES")
    zone = SUBSYSTEM_ZONES[subsystem]

    pads_by_net = extract_pads(board, nets)
    net_info = board.GetNetInfo()

    results: List[NetResult] = []
    for net in nets:
        cfg = dict(DEFAULT_NET_CONFIG)
        if net in NET_CONFIG:
            cfg.update(NET_CONFIG[net])
        if config_overrides and net in config_overrides:
            cfg.update(config_overrides[net])

        pads = pads_by_net.get(net, [])
        if not pads:
            results.append(NetResult(netname=net, status="SKIPPED",
                                     n_segments=0, n_vias=0, length_mm=0.0,
                                     via_classes=(), routed_edges=0,
                                     total_edges=0,
                                     failure_reason="net has no pads on this board"))
            continue

        result = route_net(board, net, pads, cfg, zone)
        # Emit on success (or partial — we still bank what routed).
        if result.routes:
            ni = net_info.GetNetItem(net)
            if ni is None:
                result.status = "NOT-ROUTABLE"
                result.failure_reason = f"net {net} not found in board NetInfo"
            else:
                n_tr, n_via = emit_route_to_board(board, ni, result.routes)
                # cross-check (should match)
                assert n_tr == result.n_segments
                assert n_via == result.n_vias
        results.append(result)

    pcbnew.SaveBoard(output_path, board)

    if report_path:
        _write_report(report_path, results)

    return results


def _write_report(path: str, results: Sequence[NetResult]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["net", "status", "edges_routed", "edges_total",
                    "n_segments", "n_vias", "length_mm", "via_classes",
                    "failure_reason", "failed_pin_pair"])
        for r in results:
            w.writerow([r.netname, r.status, r.routed_edges, r.total_edges,
                        r.n_segments, r.n_vias, f"{r.length_mm:.3f}",
                        ";".join(r.via_classes) if r.via_classes else "",
                        r.failure_reason or "",
                        f"{r.failed_pin_pair[0]}→{r.failed_pin_pair[1]}"
                            if r.failed_pin_pair else ""])


def _print_summary(results: Sequence[NetResult]) -> None:
    print("=" * 72)
    print(f"route_on_board — {len(results)} net(s)")
    print("-" * 72)
    routed = sum(1 for r in results if r.status == "ROUTED")
    partial = sum(1 for r in results if r.status == "PARTIAL")
    nope = sum(1 for r in results if r.status == "NOT-ROUTABLE")
    skip = sum(1 for r in results if r.status == "SKIPPED")
    print(f"  ROUTED={routed}  PARTIAL={partial}  NOT-ROUTABLE={nope}  SKIPPED={skip}")
    print("-" * 72)
    for r in results:
        line = (f"  {r.netname:24s} {r.status:14s} "
                f"edges={r.routed_edges}/{r.total_edges} "
                f"seg={r.n_segments} via={r.n_vias} "
                f"L={r.length_mm:.2f}mm")
        if r.via_classes:
            line += f" via_classes={'/'.join(r.via_classes)}"
        if r.failure_reason:
            line += f"  fail={r.failure_reason}"
            if r.failed_pin_pair:
                line += f" @{r.failed_pin_pair[0]}→{r.failed_pin_pair[1]}"
        print(line)
    print("=" * 72)


# ─── CLI entry ───────────────────────────────────────────────────────────────
def _main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="route_on_board.py — wrap maze_router for a live .kicad_pcb"
    )
    ap.add_argument("--board", required=True, help="input .kicad_pcb path")
    ap.add_argument("--subsystem", default="CH1",
                    help="subsystem zone key (default CH1)")
    ap.add_argument("--nets", required=True,
                    help="comma-list of net names to route")
    ap.add_argument("--output", required=True, help="output .kicad_pcb path")
    ap.add_argument("--report", help="optional CSV report path")
    ap.add_argument("--route-layers",
                    help="comma-list to OVERRIDE route_layers (e.g. F.Cu,In8.Cu)")
    ap.add_argument("--via-classes",
                    help="comma-list to OVERRIDE in-route via classes "
                         "(empty for single-layer)")
    ap.add_argument("--stitch-via-class",
                    help="OVERRIDE stitching via class; empty to disable")
    args = ap.parse_args(argv)

    nets = [n.strip() for n in args.nets.split(",") if n.strip()]
    overrides: Dict[str, dict] = {}
    if (args.route_layers or args.via_classes is not None
            or args.stitch_via_class is not None):
        common: dict = {}
        if args.route_layers:
            common["route_layers"] = tuple(
                L.strip() for L in args.route_layers.split(",") if L.strip())
        if args.via_classes is not None:
            common["via_classes"] = tuple(
                c.strip() for c in args.via_classes.split(",") if c.strip())
        if args.stitch_via_class is not None:
            common["stitch_via_class"] = args.stitch_via_class.strip() or ""
        for n in nets:
            overrides[n] = dict(common)

    results = run_harness(args.board, args.subsystem, nets,
                          args.output, args.report, overrides)
    _print_summary(results)

    any_failed = any(r.status in ("NOT-ROUTABLE", "PARTIAL") for r in results)
    return 1 if any_failed else 0


# ─── self-test (pure-python; no pcbnew needed) ───────────────────────────────
def _self_test() -> int:
    """Smoke test the per-net wiring against synthetic fixtures (no pcbnew).

    Validates:
      - via-class → fab geometry table is consistent with the DRU
      - DEFAULT_NET_CONFIG via classes all live in VIA_CLASSES
      - star-from-root produces (root,p) pairs in canonical order
      - region bbox clamps to subsystem zone
    """
    print("=" * 72)
    print("route_on_board.py — self-test")
    print("=" * 72)

    # 1. via geom table sanity
    for cls, (drill, pad) in VIA_GEOM_MM.items():
        assert 0.05 <= drill <= 0.40, f"{cls} drill {drill} OOR"
        assert pad > drill, f"{cls} pad {pad} not > drill {drill}"
    assert VIA_GEOM_MM["blind"] == (0.15, 0.25), "OQ-020 blind geom mismatch"
    print("  ok via-class → geom table consistent")

    # 2. route_layers + via_classes + stitch_via_class valid
    all_cfgs = [DEFAULT_NET_CONFIG] + list(NET_CONFIG.values())
    for cfg in all_cfgs:
        rls = cfg["route_layers"]
        assert len(rls) >= 1, "route_layers must have ≥1 layer"
        for L in rls:
            assert L in LAYER_STACK, f"route_layer {L!r} not in LAYER_STACK"
        for vc in cfg.get("via_classes", ()):
            assert vc in VIA_CLASSES, f"unknown in-route via_class {vc!r}"
            assert vc in VIA_GEOM_MM, f"no fab geom for via_class {vc!r}"
        sv = cfg.get("stitch_via_class")
        if sv:
            assert sv in VIA_CLASSES, f"unknown stitch_via_class {sv!r}"
            assert sv in VIA_GEOM_MM, f"no fab geom for stitch class {sv!r}"
    print("  ok route_layers + via_classes + stitch_via_class valid")

    # 3. star-from-root pair order
    p_root = PadInfo("J19", "8", "KILL_RAIL_N_CH1", 23.45, 64.46,
                     ("F.Cu",), (23.32, 64.02, 23.57, 64.89))
    p1 = PadInfo("D37", "2", "KILL_RAIL_N_CH1", 30.7, 61.2,
                 ("B.Cu",), (30.5, 61.0, 30.9, 61.4))
    p2 = PadInfo("D38", "2", "KILL_RAIL_N_CH1", 32.2, 57.6,
                 ("B.Cu",), (32.0, 57.4, 32.4, 57.8))
    p3 = PadInfo("R76", "1", "KILL_RAIL_N_CH1", 35.26, 60.8,
                 ("B.Cu",), (35.1, 60.6, 35.4, 61.0))
    pairs = _mst_pairs(p_root, [p1, p2, p3])
    assert len(pairs) == 3 and all(s is p_root for s, _ in pairs)
    print("  ok star-from-root 4-pad MST produces 3 edges from root")

    # 4. region bbox clamping
    zone = SUBSYSTEM_ZONES["CH1"]
    pads = [PadInfo("J19", "10", "GLB_CH1", 24.45, 64.46, ("F.Cu",),
                    (24.32, 64.02, 24.57, 64.89)),
            PadInfo("R50", "1", "GLB_CH1", 6.81, 75.04, ("B.Cu",),
                    (6.5, 74.9, 7.1, 75.2))]
    r = _region_bbox(pads, zone, REGION_MARGIN_MM)
    assert r[0] >= zone[0] - 1e-6 and r[2] <= zone[2] + 1e-6
    assert r[1] >= zone[1] - 1e-6 and r[3] <= zone[3] + 1e-6
    # both pads inside the region
    for p in pads:
        assert r[0] - 1e-6 <= p.x_mm <= r[2] + 1e-6
        assert r[1] - 1e-6 <= p.y_mm <= r[3] + 1e-6
    print("  ok region bbox clamps to CH1 zone + contains both pads")

    # 5. degenerate (single point) region widens
    one = [PadInfo("X", "1", "DEMO", 17.5, 70.0, ("F.Cu",),
                   (17.3, 69.8, 17.7, 70.2))]
    r = _region_bbox(one, zone, REGION_MARGIN_MM)
    assert r[2] - r[0] >= 2 * REGION_MARGIN_MM - 1e-6
    assert r[3] - r[1] >= 2 * REGION_MARGIN_MM - 1e-6
    print("  ok degenerate single-pad region widens to >= 2x margin")

    print("=" * 72)
    print("route_on_board.py self-test: ALL PASS")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        sys.exit(_self_test())
    sys.exit(_main())
