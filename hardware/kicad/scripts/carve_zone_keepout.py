#!/usr/bin/env python3
"""carve_zone_keepout.py — Phase 5 Option A: carve a rule-area keepout
in a poured zone to open a routing corridor for a foreign net.

Per Sai 2026-05-30 Option A directive (post-II root cause): R76.1
KILL_RAIL_N leaf NO_PATH because the +VMOTOR poured zone covers the
B.Cu corridor. Carve a rectangular rule-area (keepout) covering the
corridor; when +VMOTOR refills, the rule area excludes copper, opening
the corridor for KILL_RAIL_N's leaf trace.

Discipline:
  R21 DEV-010: zone keepout added board-only; schematic edit not
    required (keepouts are board-mechanical). Reconciled with
    schematic via the DRC + DRU rule set.
  R37 audit-not-faith: each carve writes provenance with input/output
    MD5 + R21 disclosure.
  Sai-physics: keepout area lost to +VMOTOR is minimal (~10 mm² of
    ~9216mm² = 0.1%); no FoS ampacity impact.

KEEPOUT properties applied:
  - SetIsRuleArea(True)            — rule-area zone (not fill)
  - SetDoNotAllowCopperPour(True)   — exclude COPPER fill in this region
  - SetDoNotAllowTracks(False)     — allow tracks (we WANT routing here)
  - SetDoNotAllowVias(False)       — allow vias (chain transitions OK)
  - SetDoNotAllowPads(False)       — pads still exist (this is just a
                                       fill exclusion)

Usage:
    python3 carve_zone_keepout.py
        --board <input.kicad_pcb>
        --output <output.kicad_pcb>
        --rect 28.0,60.0,36.0,62.0  # x_min,y_min,x_max,y_max mm
        --layer B.Cu
        --net KILL_RAIL_N_CH1        # for naming + provenance
        [--ref KO_KILL_RAIL_N_CH1_B_CU]
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import sys
import time

import pcbnew


def _md5(path: str) -> str:
    return hashlib.md5(pathlib.Path(path).read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--rect", required=True,
                    help="x_min,y_min,x_max,y_max in mm")
    ap.add_argument("--layer", default="B.Cu",
                    choices=["F.Cu", "B.Cu"] +
                    [f"In{i}.Cu" for i in range(1, 9)])
    ap.add_argument("--net", required=True,
                    help="Net the keepout opens corridor for (provenance only)")
    ap.add_argument("--ref", default=None,
                    help="Keepout reference (default auto-generated)")
    ap.add_argument("--provenance",
                    default="sims/zone_keepout_provenance",
                    help="Provenance dir")
    args = ap.parse_args()

    try:
        x_min, y_min, x_max, y_max = (float(v.strip())
                                       for v in args.rect.split(","))
    except ValueError:
        print(f"FAIL: --rect must be 4 comma-sep mm values "
              f"(got {args.rect!r})", file=sys.stderr)
        return 2
    if x_min >= x_max or y_min >= y_max:
        print(f"FAIL: invalid rect — x_min<x_max and y_min<y_max required",
              file=sys.stderr)
        return 2

    ref = args.ref or f"KO_{args.net}_{args.layer.replace('.', '_')}"
    board = pcbnew.LoadBoard(args.board)

    # Build the keepout zone
    zone = pcbnew.ZONE(board)
    zone.SetLayer(board.GetLayerID(args.layer))
    zone.SetIsRuleArea(True)
    zone.SetDoNotAllowCopperPour(True)
    # Allow tracks/vias/pads — this rule area ONLY excludes copper fill
    try:
        zone.SetDoNotAllowTracks(False)
        zone.SetDoNotAllowVias(False)
        zone.SetDoNotAllowPads(False)
    except Exception:                                              # pragma: no cover
        pass
    # Optional: tag the keepout zone with a unique name via ZoneName().
    try:
        zone.SetZoneName(ref)
    except Exception:                                              # pragma: no cover
        pass

    # Build outline polygon (rectangle)
    outline = zone.Outline()
    outline.NewOutline()
    for (x_mm, y_mm) in [(x_min, y_min), (x_max, y_min),
                          (x_max, y_max), (x_min, y_max)]:
        outline.Append(pcbnew.VECTOR2I(int(x_mm * 1e6), int(y_mm * 1e6)))
    # Note: KiCad 9 ZONE doesn't expose SetPriority; rule-area zones take
    # precedence over fill zones automatically when IsRuleArea is True.

    board.Add(zone)
    pcbnew.SaveBoard(args.output, board)

    # Provenance
    prov_dir = pathlib.Path(args.provenance)
    prov_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    prov_path = prov_dir / f"{ref}_{ts}.json"
    prov = {
        "lever": "Phase 5 Option A: +VMOTOR zone keepout for chronic leaf corridor",
        "approval": "Sai 2026-05-30 Option A approved",
        "keepout": {
            "ref": ref,
            "net_opened": args.net,
            "layer": args.layer,
            "rect_mm": [x_min, y_min, x_max, y_max],
            "area_mm2": (x_max - x_min) * (y_max - y_min),
            "rule_settings": {
                "is_rule_area": True,
                "no_zone_fills": True,
                "tracks_allowed": True,
                "vias_allowed": True,
                "pads_allowed": True,
            },
        },
        "input_md5": _md5(args.board),
        "output_md5": _md5(args.output),
        "timestamp_utc": ts,
        "R21_deviation": "DEV-010: zone keepout added board-only; "
                          "reconciled via DRC + DRU rule set; "
                          "R19 mirror to CH2/3/4 when those routed",
    }
    prov_path.write_text(json.dumps(prov, indent=2))

    print(f"Added keepout {ref}")
    print(f"  layer:   {args.layer}")
    print(f"  rect:    ({x_min:.2f}, {y_min:.2f}) → ({x_max:.2f}, {y_max:.2f}) mm")
    print(f"  area:    {(x_max - x_min) * (y_max - y_min):.2f} mm²")
    print(f"  net:     opens corridor for {args.net}")
    print(f"  output:  {args.output}")
    print(f"  provenance: {prov_path}")
    print(f"  R21 DEV-010 disclosed: R19 cascade to CH2/3/4 pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
