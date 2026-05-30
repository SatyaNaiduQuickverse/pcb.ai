#!/usr/bin/env python3
"""insert_relay_resistor.py — Phase 5 UU.1 schematic-level chain decoupling.

Per Sai 2026-05-30 directive: insert a series-R relay at the mid-point of a
chronic-residual net's F.Cu corridor. The original net's connectivity is
preserved electrically (series 22Ω/10Ω/0Ω depending on signal class) but
the routing problem becomes 2 shorter nets (source↔R + R↔dest) instead
of 1 long chain — relieves K3 chain construction at fine-pitch QFN escape.

R21 DEV-019 disclosure (BINDING): this tool mutates the BOARD ONLY.
The schematic (KiCad .kicad_sch) is NOT updated by this tool — the new
relay R + split-net topology exists on the .kicad_pcb but NOT in the
schematic source of truth. Pre-fab requirement: regenerate schematic
to include the relay components, then re-run kinet2pcb to verify board
matches. Until then, the board has a documented R21 deviation.

Discipline:
  R23 anchor: relay R placed at midpoint of net's corridor (NOT a passive
    island — anchored to the corridor it relays)
  R21 worker deviation disclosure: schematic mismatch declared in
    per-relay provenance JSON
  R37 audit-not-faith: tool writes provenance JSON cross-referenced
    against board state by audit gate

Usage:
    python3 insert_relay_resistor.py
        --board <input.kicad_pcb>
        --output <output.kicad_pcb>
        --net PWM_INLA_CH1
        --source-pad J18.15
        --dest-pad J19.1
        --position 28.0,65.0
        --ref R_RELAY_PWM_INLA
        --value 22R
        [--layer F.Cu]
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


def _find_or_create_net(board, netname: str):
    """Return existing NETINFO_ITEM by name or create one.
    KiCad 9 NETINFO_LIST has no public AppendNet; instead, instantiate
    NETINFO_ITEM with board parent and add via board.Add() pattern OR
    just rely on board.BuildListOfNets() if pads are first assigned.
    Empirical: creating a NETINFO_ITEM with the board pointer auto-
    registers it in the board's net list."""
    nl = board.GetNetInfo()
    existing = nl.GetNetItem(netname)
    if existing and existing.GetNetCode() > 0:
        return existing
    # Create new net — constructor with board arg auto-registers
    new_net = pcbnew.NETINFO_ITEM(board, netname)
    # Try adding via board (some KiCad versions need explicit Add)
    try:
        board.Add(new_net)
    except Exception:
        pass
    # Rebuild + lookup
    try:
        board.BuildListOfNets()
    except Exception:
        pass
    refreshed = board.GetNetInfo().GetNetItem(netname)
    if refreshed and refreshed.GetNetCode() > 0:
        return refreshed
    # Fall back to the freshly-created instance even if not in list yet
    return new_net


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--net", required=True,
                    help="Original net (will be split: original on source side, "
                         "new <net>_R on dest side)")
    ap.add_argument("--source-pad", required=True,
                    help="<ref>.<pad> stays on original net (e.g. J18.15)")
    ap.add_argument("--dest-pad", required=True,
                    help="<ref>.<pad> moves to new split net (e.g. J19.1)")
    ap.add_argument("--position", required=True, help="X,Y mm — relay R position")
    ap.add_argument("--ref", required=True,
                    help="New R reference (e.g. R_RELAY_PWM_INLA)")
    ap.add_argument("--value", default="22R")
    ap.add_argument("--layer", default="F.Cu", choices=["F.Cu", "B.Cu"])
    ap.add_argument("--template-ref", default="R45",
                    help="Existing R_0402 ref to clone (default R45)")
    ap.add_argument("--provenance",
                    default="sims/uu1_relay_provenance",
                    help="provenance dir")
    args = ap.parse_args()

    try:
        x_mm, y_mm = (float(v.strip()) for v in args.position.split(","))
    except ValueError:
        print(f"FAIL: --position must be X,Y mm", file=sys.stderr)
        return 2

    board = pcbnew.LoadBoard(args.board)

    # Verify ref doesn't exist
    for fp in board.GetFootprints():
        if fp.GetReference() == args.ref:
            print(f"FAIL: ref {args.ref} already exists", file=sys.stderr)
            return 1

    # Find template + clone
    template = None
    for fp in board.GetFootprints():
        if fp.GetReference() == args.template_ref:
            template = fp
            break
    if template is None:
        print(f"FAIL: template {args.template_ref} not found", file=sys.stderr)
        return 1

    new_fp = template.Duplicate()
    new_fp.SetPosition(pcbnew.VECTOR2I(int(x_mm * 1e6), int(y_mm * 1e6)))
    new_fp.SetReference(args.ref)
    new_fp.SetValue(args.value)
    if args.layer == "B.Cu" and pcbnew.LayerName(new_fp.GetLayer()) == "F.Cu":
        new_fp.Flip(new_fp.GetPosition(), False)
    elif args.layer == "F.Cu" and pcbnew.LayerName(new_fp.GetLayer()) == "B.Cu":
        new_fp.Flip(new_fp.GetPosition(), False)
    board.Add(new_fp)

    # Locate source + dest pads on the original net
    src_ref, src_pad = args.source_pad.split(".", 1)
    dst_ref, dst_pad = args.dest_pad.split(".", 1)
    src_pad_obj = dst_pad_obj = None
    for fp in board.GetFootprints():
        if fp.GetReference() == src_ref:
            for p in fp.Pads():
                if p.GetPadName() == src_pad:
                    src_pad_obj = p
        if fp.GetReference() == dst_ref:
            for p in fp.Pads():
                if p.GetPadName() == dst_pad:
                    dst_pad_obj = p
    if src_pad_obj is None or dst_pad_obj is None:
        print(f"FAIL: source/dest pad not found", file=sys.stderr)
        return 1

    # Verify both currently on the target net
    if src_pad_obj.GetNetname() != args.net or dst_pad_obj.GetNetname() != args.net:
        print(f"FAIL: pads not on {args.net}: "
              f"src={src_pad_obj.GetNetname()!r} dst={dst_pad_obj.GetNetname()!r}",
              file=sys.stderr)
        return 1

    original_net = src_pad_obj.GetNet()

    # Create new split net (dest side)
    new_net_name = f"{args.net}_R"
    new_net = _find_or_create_net(board, new_net_name)
    if new_net is None:
        print(f"FAIL: could not create net {new_net_name}", file=sys.stderr)
        return 1

    # Reassign dest pad to new net
    dst_pad_obj.SetNet(new_net)

    # Assign relay R pads: pad 1 = original net, pad 2 = new net
    relay_pads = list(new_fp.Pads())
    if len(relay_pads) < 2:
        print(f"FAIL: relay template has <2 pads", file=sys.stderr)
        return 1
    relay_pads[0].SetNet(original_net)
    relay_pads[1].SetNet(new_net)

    pcbnew.SaveBoard(args.output, board)

    prov_dir = pathlib.Path(args.provenance)
    prov_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    prov_path = prov_dir / f"{args.ref}_{ts}.json"
    prov = {
        "lever": "Phase 5 UU.1 — schematic-level chain decoupling",
        "approval": "Sai 2026-05-30 UU.1 dispatch",
        "relay": {
            "ref": args.ref,
            "value": args.value,
            "layer": args.layer,
            "position_mm": (x_mm, y_mm),
            "template": args.template_ref,
        },
        "net_split": {
            "original_net": args.net,
            "new_net": new_net_name,
            "source_side": {"pad": args.source_pad, "net": args.net},
            "dest_side":   {"pad": args.dest_pad,   "net": new_net_name},
            "relay_pad_1_net": args.net,
            "relay_pad_2_net": new_net_name,
        },
        "input_md5": _md5(args.board),
        "output_md5": _md5(args.output),
        "timestamp_utc": ts,
        "R21_deviation": "DEV-019: board-only relay add — schematic NOT updated. "
                          "Pre-fab requirement: regenerate .kicad_sch with relay R + "
                          "split net topology, then re-run kinet2pcb to verify "
                          "board matches.",
    }
    prov_path.write_text(json.dumps(prov, indent=2))

    print(f"Added relay {args.ref} ({args.value}) at ({x_mm}, {y_mm}) {args.layer}")
    print(f"  net split: {args.net} → ({args.net} on src-side, {new_net_name} on dest-side)")
    print(f"  source pad {args.source_pad}: stays on {args.net}")
    print(f"  dest pad   {args.dest_pad}: moved to {new_net_name}")
    print(f"  output:  {args.output}")
    print(f"  provenance: {prov_path}")
    print(f"  R21 DEV-019: schematic edit follow-up REQUIRED before fab")
    return 0


if __name__ == "__main__":
    sys.exit(main())
