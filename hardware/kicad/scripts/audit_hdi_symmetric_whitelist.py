#!/usr/bin/env python3
"""audit_hdi_symmetric_whitelist.py — G_HDI_SYMMETRIC_WHITELIST binding gate.

Per Sai 2026-05-30 CC directive (post II + Option A): every HDI via-in-pad
whitelist must include BOTH chain endpoints (start AND destination) for
each chronic residual net, so K3 multi-mech can use HDI microvia classes
at both ends and avoid through-via at fine-pitch QFN pads.

This gate enforces SoT synchronization:
  (1) route_subsystem_cooperative.HDI_VIA_IN_PAD_REFS includes every
      destination footprint named in BOTTOM_MICROVIA_REFS.
  (2) audit_hdi_via_in_pad.HDI_VIA_IN_PAD_WHITELIST mirrors the SoT (no
      drift between router and audit).
  (3) For each chronic-residual net in
      BLIND_F_IN2_NET_WHITELIST + BOTTOM_MICROVIA_NET_WHITELIST,
      EVERY pad on that net belongs to a footprint whose ref is in
      HDI_VIA_IN_PAD_WHITELIST. No silent "stranded" endpoint pads.

Exit 0 = symmetric whitelist verified.
Exit 1 = SoT drift or stranded endpoint detected.

Usage:
    python3 audit_hdi_symmetric_whitelist.py [<board.kicad_pcb>]
"""
from __future__ import annotations
import argparse
import os
import sys
from typing import List, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import audit_hdi_via_in_pad as AUD                                 # noqa: E402
try:
    import route_subsystem_cooperative as RC                       # noqa: E402
except Exception as e:
    print(f"FAIL: route_subsystem_cooperative import: {e}", file=sys.stderr)
    sys.exit(2)


def audit(board_path: str = None) -> Tuple[int, List[str]]:
    failures: List[str] = []

    # (1) + (2) SoT mirror check between router + audit module
    router_set = set(RC.HDI_VIA_IN_PAD_REFS)
    audit_set = set(AUD.HDI_VIA_IN_PAD_WHITELIST)
    if router_set != audit_set:
        failures.append(
            f"SoT drift: route_subsystem_cooperative.HDI_VIA_IN_PAD_REFS "
            f"= {sorted(router_set)} but "
            f"audit_hdi_via_in_pad.HDI_VIA_IN_PAD_WHITELIST = "
            f"{sorted(audit_set)} — they MUST be identical (SoT)")

    # Destination refs from BOTTOM_MICROVIA must be subset of HDI whitelist
    bm_refs = set(AUD.BOTTOM_MICROVIA_REFS)
    missing = bm_refs - router_set
    if missing:
        failures.append(
            f"BOTTOM_MICROVIA_REFS contains destinations not in "
            f"HDI_VIA_IN_PAD_REFS: {sorted(missing)} — CC symmetric "
            f"requires every BB destination to also have F-side HDI "
            f"via-in-pad geometry")

    # (3) Stranded endpoint check: every pad on a chronic-residual net
    # must belong to a footprint in the symmetric whitelist.
    stranded: List[str] = []
    if board_path:
        import pcbnew
        board = pcbnew.LoadBoard(board_path)
        chronic_nets = set(AUD.BLIND_F_IN2_NET_WHITELIST) | \
                       set(AUD.BOTTOM_MICROVIA_NET_WHITELIST)
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            for p in fp.Pads():
                try:
                    net = p.GetNetname() if p.GetNet() else ""
                except Exception:                                  # pragma: no cover
                    net = ""
                if net in chronic_nets and ref not in audit_set:
                    stranded.append(
                        f"  {ref}.{p.GetPadName()} net={net!r}: "
                        f"foot ref not in HDI whitelist")
        if stranded:
            failures.append(
                f"{len(stranded)} stranded endpoint(s) — chronic-net pads "
                f"on non-whitelisted footprints:\n" +
                "\n".join(stranded[:15]))

    print(f"G_HDI_SYMMETRIC_WHITELIST audit:")
    print(f"  router HDI_VIA_IN_PAD_REFS: {len(router_set)} ref(s)")
    print(f"  audit  HDI_VIA_IN_PAD_WHITELIST: {len(audit_set)} ref(s)")
    print(f"  BOTTOM_MICROVIA_REFS:      {len(bm_refs)} ref(s)")
    print(f"  Symmetric (router == audit): {router_set == audit_set}")
    print(f"  BOTTOM_MICROVIA destinations covered: "
          f"{bm_refs.issubset(router_set)}")
    if board_path:
        print(f"  Stranded endpoints on chronic nets: {len(stranded)}")
    if failures:
        print(f"\n❌ FAIL ({len(failures)} issue(s)):")
        for f in failures[:10]:
            print(f"  - {f}")
        return 1, failures
    print("\n✅ PASS — HDI whitelist symmetric across router + audit + destinations")
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
