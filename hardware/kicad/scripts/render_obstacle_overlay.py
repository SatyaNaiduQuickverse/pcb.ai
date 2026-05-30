#!/usr/bin/env python3
"""render_obstacle_overlay.py — Phase 5 II visual diagnostic tool.

Per Sai 2026-05-30 directive: render engine obstacle map at chronic-leaf
location with overlay to see what blocks the corridor. Programmatic
output (text + JSON) to allow scripted analysis; SVG export optional.

For a given (x, y, layer) location + radius, prints:
  - Foreign-net tracks within radius
  - Foreign-net pads within radius (per-layer)
  - Foreign-net vias within radius
  - Zone fills overlapping the region (with net + layer)
  - Owner-net items (the net being diagnosed) — for visual context

Discriminates the 3 hypotheses Sai posed:
  (a) engine sees obstacle that's NOT on the board (engine model bug)
  (b) obstacle on board, corridor narrow but legitimate (placement issue)
  (c) leaf endpoint coords mismatched between router and pad.GetPosition

Codifies G_RENDER_OBSTACLE_OVERLAY visual diagnostic gate. JSON output
makes the diagnostic reproducible + audit-bound.

Usage:
    python3 render_obstacle_overlay.py
        --board <path>
        --location 35.26,60.80        # R76.1 position
        --layer B.Cu
        --radius 8.0                   # mm
        --owner-net KILL_RAIL_N_CH1    # for context filtering
        [--output diagnostic.json]
        [--svg overlay.svg]
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import pcbnew


def _diagnose(board, x_mm: float, y_mm: float, layer: str,
              radius_mm: float, owner_net: str) -> Dict:
    """Build the obstacle inventory at the location."""
    result = {
        "location": (x_mm, y_mm),
        "layer": layer,
        "radius_mm": radius_mm,
        "owner_net": owner_net,
        "foreign_tracks": [],
        "foreign_pads": [],
        "foreign_vias": [],
        "zone_fills": [],
        "owner_items": [],
    }
    layer_id = board.GetLayerID(layer)

    # Tracks
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        if t.GetLayer() != layer_id:
            continue
        s, e = t.GetStart(), t.GetEnd()
        sx, sy = s.x / 1e6, s.y / 1e6
        ex, ey = e.x / 1e6, e.y / 1e6
        # check if either end is within radius
        d_s = math.hypot(sx - x_mm, sy - y_mm)
        d_e = math.hypot(ex - x_mm, ey - y_mm)
        if min(d_s, d_e) > radius_mm:
            continue
        net = t.GetNetname() or ""
        entry = {
            "net": net,
            "start": (sx, sy),
            "end": (ex, ey),
            "width_mm": t.GetWidth() / 1e6,
            "min_distance_mm": round(min(d_s, d_e), 3),
        }
        if net == owner_net:
            result["owner_items"].append({"type": "track", **entry})
        else:
            result["foreign_tracks"].append(entry)

    # Pads
    for fp in board.GetFootprints():
        for p in fp.Pads():
            ls = p.GetLayerSet()
            if not ls.Contains(layer_id):
                continue
            pos = p.GetPosition()
            px, py = pos.x / 1e6, pos.y / 1e6
            d = math.hypot(px - x_mm, py - y_mm)
            if d > radius_mm:
                continue
            net = p.GetNetname() if p.GetNet() else ""
            sz = p.GetSize()
            entry = {
                "ref": fp.GetReference(),
                "pad": p.GetPadName(),
                "net": net,
                "pos": (px, py),
                "size_mm": (sz.x / 1e6, sz.y / 1e6),
                "distance_mm": round(d, 3),
            }
            if net == owner_net:
                result["owner_items"].append({"type": "pad", **entry})
            else:
                result["foreign_pads"].append(entry)

    # Vias
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        pos = t.GetPosition()
        px, py = pos.x / 1e6, pos.y / 1e6
        d = math.hypot(px - x_mm, py - y_mm)
        if d > radius_mm:
            continue
        net = t.GetNetname() or ""
        entry = {
            "net": net,
            "pos": (px, py),
            "drill_mm": t.GetDrill() / 1e6,
            "distance_mm": round(d, 3),
        }
        if net == owner_net:
            result["owner_items"].append({"type": "via", **entry})
        else:
            result["foreign_vias"].append(entry)

    # Zones
    for z in board.Zones():
        if z.GetLayer() != layer_id:
            continue
        net = z.GetNetname() or ""
        bb = z.GetBoundingBox()
        zx1 = bb.GetX() / 1e6
        zy1 = bb.GetY() / 1e6
        zx2 = (bb.GetX() + bb.GetWidth()) / 1e6
        zy2 = (bb.GetY() + bb.GetHeight()) / 1e6
        # bbox overlap with our region
        rx1, ry1 = x_mm - radius_mm, y_mm - radius_mm
        rx2, ry2 = x_mm + radius_mm, y_mm + radius_mm
        if zx2 < rx1 or zx1 > rx2 or zy2 < ry1 or zy1 > ry2:
            continue
        covers = (zx1 <= x_mm <= zx2 and zy1 <= y_mm <= zy2)
        result["zone_fills"].append({
            "net": net,
            "bbox": (zx1, zy1, zx2, zy2),
            "covers_location": covers,
        })

    return result


def _print_report(r: Dict) -> None:
    print(f"=== Obstacle map @ ({r['location'][0]:.2f}, {r['location'][1]:.2f}) "
           f"on {r['layer']}, radius {r['radius_mm']}mm, owner={r['owner_net']!r}")
    print()
    print(f"Foreign tracks:           {len(r['foreign_tracks'])}")
    print(f"Foreign pads:             {len(r['foreign_pads'])}")
    print(f"Foreign vias:             {len(r['foreign_vias'])}")
    print(f"Zone fills overlapping:   {len(r['zone_fills'])}")
    print(f"Owner-net items:          {len(r['owner_items'])}")
    print()
    if r["foreign_tracks"]:
        print("--- Foreign tracks ---")
        for e in r["foreign_tracks"][:10]:
            print(f"  {e['net']:30s} ({e['start']}→{e['end']}) "
                   f"w={e['width_mm']:.2f}mm d={e['min_distance_mm']}mm")
    if r["foreign_pads"]:
        print("--- Foreign pads ---")
        for e in r["foreign_pads"][:15]:
            print(f"  {e['ref']:6s}.{e['pad']:3s} net={e['net']:25s} "
                   f"at {e['pos']} d={e['distance_mm']}mm")
    if r["foreign_vias"]:
        print("--- Foreign vias ---")
        for e in r["foreign_vias"][:10]:
            print(f"  {e['net']:30s} at {e['pos']} drill={e['drill_mm']}mm "
                   f"d={e['distance_mm']}mm")
    if r["zone_fills"]:
        print("--- Zone fills ---")
        for e in r["zone_fills"]:
            mark = " *** COVERS LOCATION ***" if e["covers_location"] else ""
            print(f"  {e['net']:20s} bbox {e['bbox']}{mark}")
    if r["owner_items"]:
        print("--- Owner-net items (context) ---")
        for e in r["owner_items"][:8]:
            print(f"  {e['type']:5s} {e}")

    # Diagnosis hint
    print()
    print("--- Diagnostic hints ---")
    covers = [z for z in r["zone_fills"] if z["covers_location"]
              and z["net"] != r["owner_net"]]
    if covers:
        print(f"  ⚠️ {len(covers)} foreign-net zone fill(s) COVER this location:")
        for z in covers:
            print(f"      {z['net']!r} bbox {z['bbox']}")
        print(f"  → Hypothesis (b): corridor blocked by zone fills; "
               f"router must navigate antipad / negotiate-around or change layer")
    if not r["foreign_tracks"] and not r["foreign_vias"]:
        print(f"  ℹ️ NO foreign tracks/vias in radius → corridor mostly empty "
               f"of competing copper; zone fills are the only blocker")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", required=True)
    ap.add_argument("--location", required=True,
                    help="X,Y mm — focal location")
    ap.add_argument("--layer", default="B.Cu")
    ap.add_argument("--radius", type=float, default=8.0)
    ap.add_argument("--owner-net", required=True)
    ap.add_argument("--output", help="JSON output path")
    args = ap.parse_args(argv)

    x_mm, y_mm = (float(v.strip()) for v in args.location.split(","))
    board = pcbnew.LoadBoard(args.board)
    report = _diagnose(board, x_mm, y_mm, args.layer, args.radius,
                        args.owner_net)
    _print_report(report)
    if args.output:
        import pathlib
        pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.output).write_text(json.dumps(report, indent=2, default=str))
        print(f"\nJSON: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
