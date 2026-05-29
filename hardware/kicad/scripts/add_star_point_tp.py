#!/usr/bin/env python3
"""add_star_point_tp.py — Phase 5 UU.4: add a STAR-POINT test point to a board.

Per Sai 2026-05-30 directive (UU.4): structurally solve KILL_RAIL_N_CH1
3-island MST split by adding a single TP that re-roots the MST as a star.
Tool generalizes: any net + any position + any layer.

Discipline preserved:
  R21 DEV-007: TP added board-only ≠ schematic; this is a documented
    deviation that must be reconciled by schematic edit before fab.
  R23 anchor: TP placement uses configurable position; caller must respect
    role-max distance to net's parent (verified by G_STAR_POINT_TP audit).
  R37 audit-not-faith: provenance JSON written with hash + content for
    audit-bound verification.

Reuses an existing TP footprint as the template (TestPoint_Pad_D1.0mm) to
match canonical TP geometry — no schematic-library introduction.

Usage:
    python3 add_star_point_tp.py
        --board <input.kicad_pcb>
        --output <output.kicad_pcb>
        --net KILL_RAIL_N_CH1
        --ref TP_KILL_STAR_CH1
        --position 27.50,62.50
        --layer B.Cu
        [--template-ref TP23]
        [--pad-size 1.0]
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
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
    ap.add_argument("--net", required=True,
                    help="Target net for the TP (must exist on board)")
    ap.add_argument("--ref", required=True,
                    help="New TP reference (e.g. TP_KILL_STAR_CH1)")
    ap.add_argument("--position", required=True,
                    help="X,Y mm — TP anchor position")
    ap.add_argument("--layer", default="B.Cu",
                    choices=["F.Cu", "B.Cu"])
    ap.add_argument("--template-ref", default="TP23",
                    help="Existing TP to clone as template (default TP23)")
    ap.add_argument("--pad-size", type=float, default=1.0)
    ap.add_argument("--provenance",
                    default="sims/star_point_tp_provenance",
                    help="provenance dir")
    args = ap.parse_args()

    try:
        x_mm, y_mm = (float(v.strip()) for v in args.position.split(","))
    except ValueError:
        print(f"FAIL: --position must be X,Y mm (got {args.position!r})",
              file=sys.stderr)
        return 2

    board = pcbnew.LoadBoard(args.board)

    # Verify net exists
    net = board.GetNetInfo().GetNetItem(args.net)
    if net is None or net.GetNetCode() == 0:
        print(f"FAIL: net {args.net!r} not found on board", file=sys.stderr)
        return 1

    # Verify ref doesn't already exist
    for fp in board.GetFootprints():
        if fp.GetReference() == args.ref:
            print(f"FAIL: reference {args.ref!r} already exists on board",
                  file=sys.stderr)
            return 1

    # Find template TP and clone it
    template = None
    for fp in board.GetFootprints():
        if fp.GetReference() == args.template_ref:
            template = fp
            break
    if template is None:
        print(f"FAIL: template {args.template_ref!r} not found", file=sys.stderr)
        return 1

    # Clone via Duplicate() so all pad geometry + net membership is preserved
    new_fp = template.Duplicate()
    # Move to target position
    new_fp.SetPosition(pcbnew.VECTOR2I(int(x_mm * 1e6), int(y_mm * 1e6)))
    new_fp.SetReference(args.ref)

    # Set layer (B.Cu by default for star-point on the B side)
    if args.layer == "F.Cu":
        new_fp.SetLayer(pcbnew.F_Cu)
        # Set pads' layer set explicitly
        for p in new_fp.Pads():
            ls = pcbnew.LSET()
            ls.AddLayer(pcbnew.F_Cu)
            try:
                p.SetLayerSet(ls)
            except Exception:
                pass
    else:
        new_fp.SetLayer(pcbnew.B_Cu)
        for p in new_fp.Pads():
            ls = pcbnew.LSET()
            ls.AddLayer(pcbnew.B_Cu)
            try:
                p.SetLayerSet(ls)
            except Exception:
                pass

    # Set the net on each pad
    for p in new_fp.Pads():
        p.SetNet(net)

    # Set pad size if requested
    sz = int(args.pad_size * 1e6)
    for p in new_fp.Pads():
        try:
            p.SetSize(pcbnew.VECTOR2I(sz, sz))
        except Exception:
            pass

    board.Add(new_fp)
    pcbnew.SaveBoard(args.output, board)

    # Provenance
    prov_dir = pathlib.Path(args.provenance)
    prov_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    prov_path = prov_dir / f"{args.ref}_{ts}.json"
    prov = {
        "lever": "UU.4 STAR-POINT TP",
        "approval": "Sai 2026-05-30 UU expansion",
        "tp": {
            "ref": args.ref,
            "net": args.net,
            "position_mm": (x_mm, y_mm),
            "layer": args.layer,
            "template_ref": args.template_ref,
            "pad_size_mm": args.pad_size,
        },
        "input_md5": _md5(args.board),
        "output_md5": _md5(args.output),
        "timestamp_utc": ts,
        "R21_deviation": "DEV-007: TP added board-only; schematic edit required",
    }
    prov_path.write_text(json.dumps(prov, indent=2))

    # Count pads on the net (sanity check)
    n_pads = 0
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == args.net:
                n_pads += 1

    print(f"Added {args.ref} at ({x_mm:.3f}, {y_mm:.3f}) {args.layer}")
    print(f"  template: {args.template_ref}  net: {args.net}")
    print(f"  net pad count on board: {n_pads}")
    print(f"  output: {args.output}")
    print(f"  provenance: {prov_path}")
    print(f"  R21 DEV-007: schematic edit follow-up required (board-only add)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
