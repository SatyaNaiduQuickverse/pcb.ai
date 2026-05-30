#!/usr/bin/env python3
"""audit_mst_root_provenance.py — G_MST_ROOT_PROVENANCE binding gate.

Per Sai 2026-05-30 DD directive: every chronic-leaf net with a documented
MST root override must satisfy:
  (1) Net is in MST_ROOT_OVERRIDE dict in route_subsystem_cooperative.
  (2) Override target (ref, pad) exists on the board for that net.
  (3) Override pad is actually on the net (not a stranded mistake).
  (4) For each chronic-residual net listed in Sai's DD spec, an override
      IS present (no silent drops).

Exit 0 = compliant.
Exit 1 = SoT drift / missing override / stranded target.

Usage:
    python3 audit_mst_root_provenance.py [<board.kicad_pcb>]
"""
from __future__ import annotations
import argparse
import os
import sys
from typing import List, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

try:
    import route_subsystem_cooperative as RC
except Exception as e:
    print(f"FAIL: import route_subsystem_cooperative: {e}", file=sys.stderr)
    sys.exit(2)


# Per Sai DD spec — the chronic-residual nets that REQUIRE an MST root
# override. Audit will FAIL if any of these is missing from MST_ROOT_OVERRIDE.
DD_REQUIRED_NETS = (
    "KILL_RAIL_N_CH1",
    "PWM_INLA_CH1",
    "GLB_CH1",
)


def audit(board_path: str = None) -> Tuple[int, List[str]]:
    failures: List[str] = []

    # (1) + (4): each required net is present in MST_ROOT_OVERRIDE
    overrides = RC.MST_ROOT_OVERRIDE
    for net in DD_REQUIRED_NETS:
        if net not in overrides:
            failures.append(
                f"net {net!r} missing from MST_ROOT_OVERRIDE — Sai DD spec "
                f"requires per-net root override for chronic-leaf nets")
        else:
            ref, pad = overrides[net]
            if not ref or not pad:
                failures.append(
                    f"net {net!r}: invalid override target ({ref!r}, {pad!r})")

    # (2) + (3): override targets exist on the board AND the pad belongs
    # to the override net.
    if board_path:
        import pcbnew
        board = pcbnew.LoadBoard(board_path)
        # Build (ref, pad) → net map for fast lookup
        pad_net = {}
        for fp in board.GetFootprints():
            r = fp.GetReference()
            for p in fp.Pads():
                try:
                    net = p.GetNetname() if p.GetNet() else ""
                except Exception:                                  # pragma: no cover
                    net = ""
                pad_net[(r, p.GetPadName())] = net

        for net, (ref, pad) in overrides.items():
            key = (ref, str(pad))
            if key not in pad_net:
                failures.append(
                    f"override for {net!r}: target {ref}.{pad} NOT on board")
            elif pad_net[key] != net:
                failures.append(
                    f"override for {net!r}: target {ref}.{pad} is on net "
                    f"{pad_net[key]!r}, not {net!r} (stranded target)")

    print(f"G_MST_ROOT_PROVENANCE audit:")
    print(f"  MST_ROOT_OVERRIDE entries: {len(overrides)}")
    print(f"  DD-required nets covered:  "
          f"{sum(1 for n in DD_REQUIRED_NETS if n in overrides)}/"
          f"{len(DD_REQUIRED_NETS)}")
    if board_path:
        print(f"  Board cross-check: {board_path}")
    if failures:
        print(f"\n❌ FAIL ({len(failures)} issue(s)):")
        for f in failures[:15]:
            print(f"  - {f}")
        return 1, failures
    print("\n✅ PASS — MST root override provenance verified")
    return 0, []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board", nargs="?", default=None)
    args = ap.parse_args(argv)
    code, _ = audit(args.board)
    return code


if __name__ == "__main__":
    sys.exit(main())
