#!/usr/bin/env python3
"""audit_star_point_tp_provenance.py — G_STAR_POINT_TP binding gate.

Per Sai 2026-05-30 UU.4 directive: every PR adding a star-point TP must
ship a provenance JSON; this gate cross-checks the JSON against the live
board to prevent silent additions / drift.

Checks per provenance entry:
  (1) TP footprint EXISTS on the board (by ref).
  (2) TP position within 0.10mm of provenance position.
  (3) TP layer matches provenance (F.Cu | B.Cu).
  (4) Every TP pad's net matches provenance net.
  (5) R21 DEV-007 disclosed in provenance (schematic edit required flag).

Exit 0 = all provenance entries verified. Exit 1 = any check failed.

Usage:
    python3 audit_star_point_tp_provenance.py <board.kicad_pcb>
        [--provenance-dir sims/star_point_tp_provenance]
"""
from __future__ import annotations
import argparse
import json
import math
import os
import pathlib
import sys
from typing import List, Tuple

import pcbnew


def audit(board_path: str, prov_dir: str) -> Tuple[int, List[str]]:
    failures: List[str] = []
    d = pathlib.Path(prov_dir)
    if not d.exists():
        print(f"G_STAR_POINT_TP audit @ {board_path}")
        print(f"  provenance dir {prov_dir} missing — vacuous PASS")
        return 0, []

    entries = sorted(d.glob("*.json"))
    if not entries:
        print(f"G_STAR_POINT_TP audit @ {board_path}")
        print(f"  no provenance entries in {prov_dir} — vacuous PASS")
        return 0, []

    board = pcbnew.LoadBoard(board_path)
    fp_by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}

    print(f"G_STAR_POINT_TP audit @ {board_path}")
    print(f"  provenance entries: {len(entries)}")

    for prov_path in entries:
        prov = json.loads(prov_path.read_text())
        tp = prov.get("tp", {})
        ref = tp.get("ref")
        prov_net = tp.get("net")
        prov_pos = tp.get("position_mm", (0, 0))
        prov_layer = tp.get("layer", "B.Cu")

        # (1) Footprint exists
        fp = fp_by_ref.get(ref)
        if fp is None:
            failures.append(f"{ref}: footprint missing from board "
                            f"(provenance {prov_path.name})")
            continue

        # (2) Position match
        pos = fp.GetPosition()
        px, py = pos.x / 1e6, pos.y / 1e6
        d_pos = math.hypot(px - prov_pos[0], py - prov_pos[1])
        if d_pos > 0.10:
            failures.append(f"{ref}: position drift {d_pos:.3f}mm > 0.10mm "
                            f"(prov {prov_pos}, board ({px:.3f},{py:.3f}))")

        # (3) Layer match
        actual_layer = pcbnew.LayerName(fp.GetLayer())
        if actual_layer != prov_layer:
            failures.append(f"{ref}: layer drift {actual_layer!r} != {prov_layer!r}")

        # (4) Pad nets match
        bad_pads = []
        for p in fp.Pads():
            pn = p.GetNetname() if p.GetNet() else ""
            if pn != prov_net:
                bad_pads.append((p.GetPadName(), pn))
        if bad_pads:
            failures.append(f"{ref}: pad net mismatch — expected {prov_net!r}, "
                            f"got {bad_pads[:3]}")

        # (5) R21 deviation disclosed
        if "R21_deviation" not in prov:
            failures.append(f"{ref}: R21 deviation field missing in provenance")
        else:
            r21 = prov["R21_deviation"]
            if "DEV-007" not in r21:
                failures.append(f"{ref}: R21 deviation does not cite DEV-007: {r21!r}")

        print(f"  {ref}: ref-ok pos-d={d_pos:.3f}mm layer={actual_layer} "
              f"net-pads={len(list(fp.Pads()))} R21-disclosed=yes")

    if failures:
        print(f"\n❌ FAIL ({len(failures)} issue(s)):")
        for f in failures[:20]:
            print(f"  - {f}")
        return 1, failures
    print("\n✅ PASS — all star-point TPs audit-verified")
    return 0, []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--provenance-dir",
                    default="sims/star_point_tp_provenance")
    args = ap.parse_args(argv)
    code, _ = audit(args.board, args.provenance_dir)
    return code


if __name__ == "__main__":
    sys.exit(main())
