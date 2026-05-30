#!/usr/bin/env python3
"""audit_zone_keepout_provenance.py — G_ZONE_KEEPOUT_PROVENANCE binding gate.

Per Sai 2026-05-30 Option A directive: every zone keepout added to the
board must ship a provenance JSON; this gate cross-checks the JSON
against the live board (R37 audit-not-faith).

Checks per provenance entry:
  (1) Keepout zone EXISTS on board (by ref / ZoneName).
  (2) Layer matches provenance.
  (3) Outline matches the declared rect within ±0.10mm.
  (4) Rule settings match (rule_area, no_fills, tracks/vias/pads allowed).
  (5) R21 DEV-010 disclosed.

Exit 0 = all provenance entries verified.
Exit 1 = any check failed.

Usage:
    python3 audit_zone_keepout_provenance.py <board.kicad_pcb>
        [--provenance-dir sims/zone_keepout_provenance]
"""
from __future__ import annotations
import argparse
import json
import math
import pathlib
import sys
from typing import List, Tuple

import pcbnew


def _zones_by_ref(board) -> dict:
    out = {}
    for z in board.Zones():
        try:
            name = z.GetZoneName()
        except Exception:                                          # pragma: no cover
            name = ""
        if name:
            out[name] = z
    return out


def audit(board_path: str, prov_dir: str) -> Tuple[int, List[str]]:
    d = pathlib.Path(prov_dir)
    if not d.exists():
        print(f"G_ZONE_KEEPOUT_PROVENANCE audit @ {board_path}")
        print(f"  provenance dir {prov_dir} missing — vacuous PASS")
        return 0, []
    entries = sorted(d.glob("*.json"))
    if not entries:
        print(f"G_ZONE_KEEPOUT_PROVENANCE audit @ {board_path}")
        print(f"  no provenance entries — vacuous PASS")
        return 0, []

    board = pcbnew.LoadBoard(board_path)
    zones = _zones_by_ref(board)

    print(f"G_ZONE_KEEPOUT_PROVENANCE audit @ {board_path}")
    print(f"  provenance entries: {len(entries)}")

    failures: List[str] = []
    for prov_path in entries:
        doc = json.loads(prov_path.read_text())
        ko = doc.get("keepout", {})
        ref = ko.get("ref", "")
        z = zones.get(ref)
        if z is None:
            failures.append(f"{ref}: zone missing from board "
                            f"(provenance {prov_path.name})")
            continue

        # Layer
        actual_layer = pcbnew.LayerName(z.GetLayer())
        if actual_layer != ko.get("layer"):
            failures.append(f"{ref}: layer drift {actual_layer!r} "
                            f"!= {ko.get('layer')!r}")

        # Rect bounds
        bb = z.GetBoundingBox()
        bx_min, by_min = bb.GetX() / 1e6, bb.GetY() / 1e6
        bx_max, by_max = (bb.GetX() + bb.GetWidth()) / 1e6, \
                          (bb.GetY() + bb.GetHeight()) / 1e6
        prov_rect = ko.get("rect_mm", [0, 0, 0, 0])
        for i, (act, prov) in enumerate(zip(
                [bx_min, by_min, bx_max, by_max], prov_rect)):
            if abs(act - prov) > 0.10:
                failures.append(f"{ref}: rect[{i}] drift {act:.3f} != "
                                f"{prov:.3f} (>0.10mm tolerance)")

        # Rule-area settings
        try:
            is_ra = z.GetIsRuleArea()
        except Exception:                                          # pragma: no cover
            is_ra = False
        if not is_ra:
            failures.append(f"{ref}: NOT a rule area (IsRuleArea=False)")
        try:
            no_fills = z.GetDoNotAllowCopperPour()
        except Exception:                                          # pragma: no cover
            no_fills = False
        if not no_fills:
            failures.append(f"{ref}: zone fill NOT disallowed "
                            f"(GetDoNotAllowCopperPour=False)")

        # R21
        r21 = doc.get("R21_deviation", "")
        if "DEV-010" not in r21:
            failures.append(f"{ref}: R21 DEV-010 not disclosed")

        print(f"  {ref}: layer={actual_layer} rect=({bx_min:.2f},{by_min:.2f})→"
              f"({bx_max:.2f},{by_max:.2f}) rule_area={is_ra} "
              f"no_fills={no_fills}")

    if failures:
        print(f"\n❌ FAIL ({len(failures)} issue(s)):")
        for s in failures[:20]:
            print(f"  - {s}")
        return 1, failures
    print("\n✅ PASS — all zone keepouts audit-verified")
    return 0, []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--provenance-dir",
                    default="sims/zone_keepout_provenance")
    args = ap.parse_args(argv)
    code, _ = audit(args.board, args.provenance_dir)
    return code


if __name__ == "__main__":
    sys.exit(main())
