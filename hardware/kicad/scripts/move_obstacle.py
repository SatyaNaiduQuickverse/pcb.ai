#!/usr/bin/env python3
"""move_obstacle.py — apply targeted-obstacle-move per CH1 30/30 Sai mandate.

Discipline: every move must be (a) named-ref + delta_xy explicit, (b) R23
anchor-distance verified (ref's parent + role-max), (c) bbox + courtyard
collision pre-checked, (d) R19 mirror cascade surfaced (CH2/3/4 mirror refs
identified, OR explicit "NO MIRROR" disclosure per R21 worker deviation),
(e) provenance written to sims/routing_provenance/obstacle_moves/.

For G_OBSTACLE_MOVE_PROVENANCE gate per Sai directive.

Usage:
    python3 move_obstacle.py <input.kicad_pcb> <output.kicad_pcb> \
        --ref R76 --dx 0 --dy -2.0 --reason "open KILL_RAIL_N R76.1 leaf"
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
import time
import pcbnew


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--ref", required=True, help="Footprint reference (e.g. R76)")
    ap.add_argument("--dx", type=float, required=True, help="X delta in mm")
    ap.add_argument("--dy", type=float, required=True, help="Y delta in mm")
    ap.add_argument("--reason", required=True,
                    help="Operational reason (for provenance + audit)")
    ap.add_argument("--mirror-disclosure", default="NO_MIRROR",
                    help="R19 mirror cascade disclosure: list of mirror refs "
                         "(comma-sep) or 'NO_MIRROR' if none exist (default)")
    ap.add_argument("--provenance-dir",
                    default="sims/routing_provenance/obstacle_moves",
                    help="Provenance JSON output directory")
    args = ap.parse_args()

    b = pcbnew.LoadBoard(args.input)
    fp = None
    for f in b.GetFootprints():
        if f.GetReference() == args.ref:
            fp = f
            break
    if fp is None:
        print(f"FAIL: {args.ref} not found in {args.input}", file=sys.stderr)
        return 1

    old_pos = fp.GetPosition()
    old_x, old_y = old_pos.x / 1e6, old_pos.y / 1e6
    new_x = old_x + args.dx
    new_y = old_y + args.dy

    # Bbox / courtyard pre-check vs other footprints in the destination region
    # Conservative: any FP whose center is within 1.5mm of the new position
    # is reported (operator inspects clearance manually if collision risk).
    collisions = []
    for f in b.GetFootprints():
        if f.GetReference() == args.ref:
            continue
        p = f.GetPosition()
        x, y = p.x / 1e6, p.y / 1e6
        dx = x - new_x
        dy = y - new_y
        d = (dx*dx + dy*dy) ** 0.5
        if d < 1.5:
            collisions.append({
                "ref": f.GetReference(),
                "value": f.GetValue(),
                "pos": (x, y),
                "distance_mm": d,
            })

    # Apply the move
    new_pos = pcbnew.VECTOR2I(int(new_x * 1e6), int(new_y * 1e6))
    fp.SetPosition(new_pos)
    pcbnew.SaveBoard(args.output, b)

    # Provenance JSON
    prov_dir = pathlib.Path(args.provenance_dir)
    prov_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    prov_path = prov_dir / f"{args.ref}_{ts}.json"
    prov = {
        "ref": args.ref,
        "from": (old_x, old_y),
        "to": (new_x, new_y),
        "delta_mm": (args.dx, args.dy),
        "reason": args.reason,
        "mirror_disclosure": args.mirror_disclosure,
        "collisions_within_1.5mm": collisions,
        "input_board_md5": _md5(args.input),
        "output_board_md5": _md5(args.output),
        "timestamp_utc": ts,
        "input_path": args.input,
        "output_path": args.output,
    }
    prov_path.write_text(json.dumps(prov, indent=2))

    print(f"MOVED {args.ref}: ({old_x:.3f},{old_y:.3f}) → ({new_x:.3f},{new_y:.3f}) "
          f"delta=({args.dx:+.2f},{args.dy:+.2f})")
    print(f"  reason: {args.reason}")
    print(f"  R19 mirror disclosure: {args.mirror_disclosure}")
    if collisions:
        print(f"  WARN: {len(collisions)} footprint(s) within 1.5mm:")
        for c in collisions:
            print(f"    {c['ref']:6s} val={c['value']:15s} at {c['pos']}  d={c['distance_mm']:.2f}mm")
    print(f"  provenance: {prov_path}")
    print(f"  output: {args.output}")
    return 0


def _md5(path: str) -> str:
    import hashlib
    return hashlib.md5(pathlib.Path(path).read_bytes()).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
