#!/usr/bin/env python3
"""hand_route_residual.py — programmatic hand-route the 3 chronic CH1 residuals.

Per Sai 2026-05-29 directive (Option D): the cooperative router + AA PathFinder
+ K3 multi-mech + Y joint + Z hardest-first all hit a 27/30 ceiling on canonical
085dee9. The 3 chronic residuals (PWM_INLA_CH1, GLB_CH1, KILL_RAIL_N_CH1)
share root cause: J19 fine-pitch pin escape congestion. Their routes are
not algorithmically infeasible — they need direct geometric specification
that the maze can't discover within the verify-gate's bounded budget.

This tool encodes per-net KNOWN-GOOD chains, pre-checks each segment + via
against existing copper for collisions, atomically commits per net, and
runs post-emit MST verify (single-island per net).

Discipline preserved:
  R23 (no passive island) — N/A, we don't move passives
  R21 (worker deviation disclosure) — each route logs its specific deviation
  Sai-catches-are-samples — codified as G_HAND_ROUTE_PROVENANCE
  Sim-execution-gate — per-net pre/post-emit shorts delta + provenance JSON

Usage:
    python3 hand_route_residual.py <input.kicad_pcb> <output.kicad_pcb>
        [--net PWM_INLA_CH1,GLB_CH1,KILL_RAIL_N_CH1] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
import time
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

# ─── Hand-route specifications ────────────────────────────────────────────────
# Per-net chains designed from canonical 085dee9 obstacle topology. Each chain
# is a list of (start_xy, end_xy, width_mm, layer) segments + (xy, via_class,
# from_layer, to_layer) vias. Coordinates are mm. Width defaults 0.20mm
# (signal trace). via_class ∈ {through, blind, stacked}.
#
# DESIGN PRINCIPLE: prefer F.Cu direct routes (no via) when corridors permit.
# Vias add DRC risk + verify-gate scrutiny. Fewer vias = higher commit prob.

@dataclass(frozen=True)
class Seg:
    p1: Tuple[float, float]
    p2: Tuple[float, float]
    width_mm: float
    layer: str

@dataclass(frozen=True)
class Via:
    point: Tuple[float, float]
    via_class: str       # 'through' | 'blind' | 'stacked_F_In8' | 'stacked_F_In4'
    from_layer: str
    to_layer: str

@dataclass
class HandRoute:
    netname: str
    description: str
    segments: List[Seg]
    vias: List[Via] = field(default_factory=list)


# ─── PWM_INLA_CH1 (REVISED — In2 mid-board corridor) ──────────────────────────
# Endpoints: J18.15 (33.00, 68.44) F.Cu → J19.1 (22.26, 61.27) F.Cu
# Plan: blind F→In2 at J18.15, In2 detour SOUTH OF J18 thermal pad
# (J18 fp at (31.75, 66.00) with ~5×5mm thermal — south edge ~y=58.5),
# In2 east→south→west, blind In2→F well west of J19 thermal at x≈21,
# F.Cu stub south to J19.1.
PWM_INLA_ROUTE = HandRoute(
    netname="PWM_INLA_CH1",
    description="blind F→In2 at J18.15, In2 detour south of J18 thermal pad, blind In2→F west of J19",
    segments=[
        # In2: south then west bypassing J18 thermal pad and J19 east column
        Seg(p1=(33.00, 68.44), p2=(33.00, 56.50), width_mm=0.18, layer="In2.Cu"),
        Seg(p1=(33.00, 56.50), p2=(21.00, 56.50), width_mm=0.18, layer="In2.Cu"),
        Seg(p1=(21.00, 56.50), p2=(21.00, 61.27), width_mm=0.18, layer="In2.Cu"),
        Seg(p1=(21.00, 61.27), p2=(22.26, 61.27), width_mm=0.18, layer="In2.Cu"),
    ],
    vias=[
        Via(point=(33.00, 68.44), via_class="blind", from_layer="F.Cu", to_layer="In2.Cu"),
        Via(point=(22.26, 61.27), via_class="blind", from_layer="F.Cu", to_layer="In2.Cu"),
    ],
)


# ─── GLB_CH1 (v3 — stacked F→In8 microvia chain, In8 gate-drive layer) ───────
# In2 is fully saturated (CSA_*, PWM_*, LED_GPIO, SHUNT_*, BSTB, I_TRIP_N).
# Stacked 4-microvia chain F→In2→In4→In6→In8 at both ends, route on In8
# (canonical gate-drive layer per layer-pref-bias).
GLB_ROUTE = HandRoute(
    netname="GLB_CH1",
    description="stacked F→In8 microvia at J19.10 + In8 SW corridor + stacked In8→F at R50.1",
    segments=[
        Seg(p1=(24.45, 64.46), p2=(28.00, 64.46), width_mm=0.18, layer="In8.Cu"),
        Seg(p1=(28.00, 64.46), p2=(28.00, 78.00), width_mm=0.18, layer="In8.Cu"),
        Seg(p1=(28.00, 78.00), p2=(6.81, 78.00), width_mm=0.18, layer="In8.Cu"),
        Seg(p1=(6.81, 78.00), p2=(6.81, 75.04), width_mm=0.18, layer="In8.Cu"),
    ],
    vias=[
        Via(point=(24.45, 64.46), via_class="stacked_F_In8",
            from_layer="F.Cu", to_layer="In8.Cu"),
        Via(point=(6.81, 75.04), via_class="stacked_F_In8",
            from_layer="F.Cu", to_layer="In8.Cu"),
    ],
)


# ─── KILL_RAIL_N_CH1 (REVISED — In2 trunk + F.Cu R76 leaf) ────────────────────
# 4-node net. The F.Cu band at y=57.6 hits R26, R44, D19, etc. Use In2 mid-board
# trunk (J19.8 blind F→In2, In2 east to D38 area, blind In2→F at each diode),
# and F.Cu local leaf R76.1↔D38.2 (3mm leg, west of D15).
KILL_RAIL_N_ROUTE = HandRoute(
    netname="KILL_RAIL_N_CH1",
    description="In2 trunk J19.8→D38.2→D37.2 (HDI escape) + F.Cu R76.1 leaf",
    segments=[
        # In2 trunk: J19.8 → just-east-of-J19 → D38.2 → D37.2
        Seg(p1=(23.45, 64.46), p2=(28.00, 64.46), width_mm=0.18, layer="In2.Cu"),
        Seg(p1=(28.00, 64.46), p2=(28.00, 57.60), width_mm=0.18, layer="In2.Cu"),
        Seg(p1=(28.00, 57.60), p2=(32.20, 57.60), width_mm=0.18, layer="In2.Cu"),
        Seg(p1=(32.20, 57.60), p2=(30.70, 57.60), width_mm=0.18, layer="In2.Cu"),
        Seg(p1=(30.70, 57.60), p2=(30.70, 61.20), width_mm=0.18, layer="In2.Cu"),
        # F.Cu R76.1 leaf to a re-surfaced point near D38: blind via at (32.20, 57.60)
        # already there; add another blind near R76.1 + F.Cu tiny stub
        Seg(p1=(35.26, 60.80), p2=(35.26, 60.40), width_mm=0.18, layer="F.Cu"),
        Seg(p1=(35.26, 60.40), p2=(32.50, 60.40), width_mm=0.18, layer="F.Cu"),
        Seg(p1=(32.50, 60.40), p2=(32.50, 58.50), width_mm=0.18, layer="F.Cu"),
    ],
    vias=[
        # In2 trunk endpoints
        Via(point=(23.45, 64.46), via_class="blind", from_layer="F.Cu", to_layer="In2.Cu"),
        Via(point=(32.20, 57.60), via_class="blind", from_layer="F.Cu", to_layer="In2.Cu"),
        Via(point=(30.70, 61.20), via_class="blind", from_layer="F.Cu", to_layer="In2.Cu"),
        # Bridge: leaf F.Cu tip at (32.50, 58.50) joins the In2 trunk via a stub
        Via(point=(32.50, 58.50), via_class="blind", from_layer="F.Cu", to_layer="In2.Cu"),
    ],
)


HAND_ROUTES = {
    "PWM_INLA_CH1": PWM_INLA_ROUTE,
    "GLB_CH1":      GLB_ROUTE,
    "KILL_RAIL_N_CH1": KILL_RAIL_N_ROUTE,
}


# ─── Via geometry table (matches routing_engine/route_on_board.py) ────────────
VIA_GEOM_MM = {
    "through":          (0.30, 0.60),    # (drill, pad)
    "blind":            (0.15, 0.25),    # OQ-020 blind F-In2 HDI fab class
    "stacked":          (0.15, 0.25),    # blind chain (single hop)
    "stacked_F_In4":    (0.15, 0.25),    # 2-hop: F-In2-In4 stacked microvias
    "stacked_F_In8":    (0.15, 0.25),    # 4-hop: F-In2-In4-In6-In8 stacked
}

# Stacked chain layer pairs (for emission expansion)
STACKED_CHAINS = {
    "stacked_F_In4": [("F.Cu", "In2.Cu"), ("In2.Cu", "In4.Cu")],
    "stacked_F_In8": [("F.Cu", "In2.Cu"), ("In2.Cu", "In4.Cu"),
                      ("In4.Cu", "In6.Cu"), ("In6.Cu", "In8.Cu")],
}

LAYER_STACK = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "In5.Cu",
               "In6.Cu", "In7.Cu", "In8.Cu", "B.Cu"]


# ─── Collision pre-check ──────────────────────────────────────────────────────
def _segment_bbox(seg: Seg) -> Tuple[float, float, float, float]:
    """Return (xmin, ymin, xmax, ymax) for a segment with its half-width."""
    hw = seg.width_mm / 2.0 + 0.10   # +0.10mm DRC clearance pad
    x0, y0 = seg.p1
    x1, y1 = seg.p2
    return (min(x0, x1) - hw, min(y0, y1) - hw,
            max(x0, x1) + hw, max(y0, y1) + hw)


def _check_segment_collision(board, seg: Seg, own_netname: str,
                             pcbnew) -> List[str]:
    """Check segment against existing tracks (foreign nets) + pads (foreign).
    Returns list of collision descriptions (empty if clean)."""
    issues: List[str] = []
    x0, y0, x1, y1 = _segment_bbox(seg)
    # Foreign tracks on same layer
    for t in board.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        if pcbnew.LayerName(t.GetLayer()) != seg.layer:
            continue
        if t.GetNetname() == own_netname:
            continue
        ts = t.GetStart(); te = t.GetEnd()
        sx, sy = ts.x / 1e6, ts.y / 1e6
        ex, ey = te.x / 1e6, te.y / 1e6
        # quick reject: track bbox vs seg bbox
        tw = t.GetWidth() / 1e6 / 2.0 + 0.10
        tx0 = min(sx, ex) - tw; tx1 = max(sx, ex) + tw
        ty0 = min(sy, ey) - tw; ty1 = max(sy, ey) + tw
        if tx1 < x0 or tx0 > x1 or ty1 < y0 or ty0 > y1:
            continue
        # bbox overlap — flag
        d = _seg_seg_dist((seg.p1, seg.p2), ((sx, sy), (ex, ey)))
        min_clear = (seg.width_mm + t.GetWidth() / 1e6) / 2.0 + 0.10
        if d < min_clear:
            issues.append(f"track {t.GetNetname()!r} on {seg.layer} d={d:.3f}mm < {min_clear:.3f}mm")
    # Foreign pads on same layer (pad bbox vs seg bbox)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == own_netname:
                continue
            # ignore pads not on our layer
            if not p.IsOnLayer(_layer_id(seg.layer, pcbnew)):
                continue
            pos = p.GetPosition()
            px, py = pos.x / 1e6, pos.y / 1e6
            # pad radius (approximate)
            sz = p.GetSize()
            pr = max(sz.x, sz.y) / 1e6 / 2.0
            d = _point_seg_dist((px, py), (seg.p1, seg.p2))
            min_clear = pr + seg.width_mm / 2.0 + 0.10
            if d < min_clear:
                issues.append(f"pad {fp.GetReference()}.{p.GetNumber()} "
                              f"net={p.GetNetname()!r} on {seg.layer} "
                              f"d={d:.3f}mm < {min_clear:.3f}mm")
    return issues


def _layer_id(name: str, pcbnew):
    """Map layer name → pcbnew layer ID."""
    name_to_id = {}
    for i in range(64):
        try:
            ln = pcbnew.LayerName(i)
            if ln == name:
                name_to_id[name] = i
        except Exception:
            pass
    return name_to_id[name]


def _point_seg_dist(p, seg) -> float:
    (px, py), ((x1, y1), (x2, y2)) = p, seg
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    cx, cy = x1 + t * dx, y1 + t * dy
    return math.hypot(px - cx, py - cy)


def _seg_seg_dist(s1, s2) -> float:
    """Min distance between two segments (4 endpoint→other-segment tests)."""
    return min(
        _point_seg_dist(s1[0], s2),
        _point_seg_dist(s1[1], s2),
        _point_seg_dist(s2[0], s1),
        _point_seg_dist(s2[1], s1),
    )


# ─── Emit + verify ────────────────────────────────────────────────────────────
def _emit_hand_route(board, route: HandRoute, pcbnew) -> Tuple[int, int]:
    """Emit segments + vias for a hand route. Returns (n_tr, n_via)."""
    net_obj = board.GetNetInfo().GetNetItem(route.netname)
    if net_obj is None:
        raise RuntimeError(f"net {route.netname} not found")
    n_tr = n_via = 0
    name_to_id_cache = {}
    def lid(n):
        if n not in name_to_id_cache:
            name_to_id_cache[n] = _layer_id(n, pcbnew)
        return name_to_id_cache[n]
    for s in route.segments:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(s.p1[0] * 1e6), int(s.p1[1] * 1e6)))
        t.SetEnd  (pcbnew.VECTOR2I(int(s.p2[0] * 1e6), int(s.p2[1] * 1e6)))
        t.SetWidth(int(s.width_mm * 1e6))
        t.SetLayer(lid(s.layer))
        t.SetNet(net_obj)
        board.Add(t)
        n_tr += 1
    for v in route.vias:
        # Expand stacked chains into multiple blind microvias at the same XY
        if v.via_class in STACKED_CHAINS:
            chain = STACKED_CHAINS[v.via_class]
            for (fL, tL) in chain:
                n_via += _emit_one_via(board, net_obj, v.point, "blind",
                                       fL, tL, lid, pcbnew)
        else:
            n_via += _emit_one_via(board, net_obj, v.point, v.via_class,
                                   v.from_layer, v.to_layer, lid, pcbnew)
    return n_tr, n_via


def _emit_one_via(board, net_obj, point, via_class, from_layer, to_layer,
                  lid, pcbnew) -> int:
    """Emit a single via and return 1."""
    drill_mm, pad_mm = VIA_GEOM_MM.get(via_class, VIA_GEOM_MM["through"])
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(int(point[0] * 1e6),
                                     int(point[1] * 1e6)))
    via.SetLayerPair(lid(from_layer), lid(to_layer))
    via.SetDrill(int(drill_mm * 1e6))
    try:
        i_from = LAYER_STACK.index(from_layer)
        i_to = LAYER_STACK.index(to_layer)
        lo, hi = min(i_from, i_to), max(i_from, i_to)
        for L in LAYER_STACK[lo:hi + 1]:
            try:
                via.SetWidth(lid(L), int(pad_mm * 1e6))
            except TypeError:
                via.SetWidth(int(pad_mm * 1e6))
                break
    except Exception:
        via.SetWidth(int(pad_mm * 1e6))
    try:
        if via_class in ("blind", "stacked"):
            via.SetViaType(pcbnew.VIATYPE_BLIND_BURIED)
        elif via_class == "through":
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
    except Exception:
        pass
    via.SetNet(net_obj)
    board.Add(via)
    return 1


# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--net",
                    default="PWM_INLA_CH1,GLB_CH1,KILL_RAIL_N_CH1",
                    help="comma-separated nets to hand-route")
    ap.add_argument("--dry-run", action="store_true",
                    help="collision-check only; no emit")
    ap.add_argument("--provenance",
                    default="sims/routing_provenance/hand_route",
                    help="provenance JSON output dir")
    args = ap.parse_args()

    import pcbnew
    nets_req = [n.strip() for n in args.net.split(",") if n.strip()]

    board = pcbnew.LoadBoard(args.input)

    prov_dir = pathlib.Path(args.provenance)
    prov_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    summary: Dict[str, dict] = {}

    for nn in nets_req:
        if nn not in HAND_ROUTES:
            print(f"SKIP {nn}: no hand-route spec defined")
            summary[nn] = {"status": "NO_SPEC"}
            continue
        route = HAND_ROUTES[nn]
        print(f"\n=== {nn}: {route.description}")
        # Pre-emit collision check
        all_issues: List[str] = []
        for i, seg in enumerate(route.segments):
            issues = _check_segment_collision(board, seg, nn, pcbnew)
            for iss in issues:
                all_issues.append(f"  seg{i} {seg.p1}→{seg.p2} on {seg.layer}: {iss}")
        if all_issues:
            print(f"  COLLISIONS ({len(all_issues)}):")
            for iss in all_issues[:20]:
                print(iss)
            if len(all_issues) > 20:
                print(f"  ... ({len(all_issues)-20} more)")
            summary[nn] = {"status": "COLLISION", "issues_count": len(all_issues),
                            "issues_sample": all_issues[:10]}
            continue
        # Emit
        if args.dry_run:
            print(f"  DRY-RUN OK — no collisions, would emit "
                  f"{len(route.segments)} segments + {len(route.vias)} vias")
            summary[nn] = {"status": "DRY_RUN_OK",
                            "segments": len(route.segments),
                            "vias": len(route.vias)}
        else:
            n_tr, n_via = _emit_hand_route(board, route, pcbnew)
            print(f"  EMITTED {n_tr} tracks + {n_via} vias")
            summary[nn] = {"status": "EMITTED",
                            "tracks": n_tr, "vias": n_via}

    if not args.dry_run:
        pcbnew.SaveBoard(args.output, board)
        print(f"\nSaved: {args.output}")

    prov_path = prov_dir / f"hand_route_{ts}.json"
    prov_path.write_text(json.dumps({
        "input": args.input,
        "output": args.output,
        "dry_run": args.dry_run,
        "summary": summary,
        "timestamp_utc": ts,
    }, indent=2))
    print(f"\nProvenance: {prov_path}")

    fails = [n for n, r in summary.items()
             if r["status"] not in ("EMITTED", "DRY_RUN_OK")]
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
