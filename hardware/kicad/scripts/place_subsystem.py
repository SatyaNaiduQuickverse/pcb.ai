#!/usr/bin/env python3
"""place_subsystem.py — Phase 4-v3 BRING-IN harness (Sai PARK-THEN-BRING-IN REDO).

REVISES the Phase 4-v2 skeleton. The v2 version identified a subsystem's
components by BOARD POSITION (net-suffix + hard-coded prefix lists + zone
fall-through). That is the circular dependency Sai diagnosed as the ghost root
cause: position decides ownership, ownership decides position. v3 takes ownership
from the schematic SSOT (roster.py, position-independent) and BRINGS that roster
from the off-board parking grid into the zone.

bring_selected(board, subsystem): move exactly the roster of one subsystem from
parking into its declared zone, leaving every other component untouched (parked,
or already-brought by a prior PR). Enforces the contract at both ends:

  PRECONDITION  — every roster ref for this subsystem is currently parked
                  (off-board). Refuses otherwise: re-bringing a placed subsystem
                  or bringing before park is a process error, surfaced not masked.
  POSTCONDITION — every brought ref sits inside one of the subsystem's declared
                  zones; no ref outside this roster moved.

Component XY within the zone comes from a placement strategy. This harness ships
a deterministic grid packer (default) that satisfies the zone contract; a
subsystem PR overrides it with its bespoke, validated geometry (the
place_subsystem_ch1_v3 template, the mirror transforms) via the `placer`
callback. The harness owns the CONTRACT; the callback owns the geometry.

Usage:
  python3 place_subsystem.py <subsystem> --board PARKED [--out OUT]
  subsystems: CH1 CH2 CH3 CH4 S1 S2 S3 S5 S6
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import constraint_engine as ce
import roster as roster_mod
from place_subsystem_ch1_v3 import reset_text_to_body
from park_all_components import is_fixed

try:
    import pcbnew
except ImportError:
    print("FATAL: pcbnew not importable — install KiCad python bindings.")
    sys.exit(2)

# roster subsystem -> acceptable zone keys in BOARD_INVARIANTS
SUBSYS_ZONES = {
    "CH1": ["CH1"], "CH2": ["CH2"], "CH3": ["CH3"], "CH4": ["CH4"],
    "S1": ["S1"], "S2": ["S2"], "S3": ["S3"], "S6": ["S6"],
    "S5": ["S5_east", "S5_west", "S5_south"],
}
ON_BOARD_MARGIN = 2.0  # center within this of the 0-100 board counts as on-board


def is_parked(fp):
    x = fp.GetPosition().x / 1e6
    y = fp.GetPosition().y / 1e6
    return not (-ON_BOARD_MARGIN <= x <= 100 + ON_BOARD_MARGIN
                and -ON_BOARD_MARGIN <= y <= 100 + ON_BOARD_MARGIN)


def in_any_zone(x, y, zones):
    return any(x0 <= x <= x1 and y0 <= y <= y1 for (x0, y0, x1, y1) in zones)


def _ref_sort_key(r):
    return (re.match(r"[A-Za-z]+", r).group(), int(re.search(r"\d+", r).group()))


def grid_placer(board, refs, zones):
    """Default zone-satisfying placer: pack refs on a 1.5mm grid inside the
    first zone, 1mm inset, deterministic by ref. A subsystem PR replaces this
    with validated cluster geometry — see module docstring."""
    x0, y0, x1, y1 = zones[0]
    inset, pitch = 1.0, 1.5
    cols = max(1, int((x1 - x0 - 2 * inset) / pitch))
    for i, ref in enumerate(sorted(refs, key=_ref_sort_key)):
        fp = board.FindFootprintByReference(ref)
        col, row = i % cols, i // cols
        fp.SetPosition(pcbnew.VECTOR2I(int((x0 + inset + col * pitch) * 1e6),
                                       int((y0 + inset + row * pitch) * 1e6)))
        reset_text_to_body(fp)


def bring_selected(board, subsystem, placer=grid_placer):
    """Bring one subsystem's roster from parking into its zone(s).
    Returns (brought_refs, errors)."""
    if subsystem not in SUBSYS_ZONES:
        return [], [f"unknown subsystem {subsystem!r}"]
    inv = ce.parse_board_invariants()
    zones = [inv.zones[z] for z in SUBSYS_ZONES[subsystem]]

    roster = roster_mod.derive_roster(roster_mod.parse_netlist())
    want = {r for r, s in roster.items() if s == subsystem}

    present = {fp.GetReference(): fp for fp in board.GetFootprints()}
    refs = sorted(want & present.keys(), key=_ref_sort_key)
    missing = sorted(want - present.keys())  # netlist refs not on this board

    not_parked = [r for r in refs if not is_parked(present[r])]
    if not_parked:
        return [], [f"PRECONDITION fail: {len(not_parked)} roster refs already "
                    f"on-board (re-bring or no park?): {not_parked[:12]}"]

    placer(board, refs, zones)

    errs = []
    for r in refs:
        p = present[r].GetPosition()
        x, y = p.x / 1e6, p.y / 1e6
        if not in_any_zone(x, y, zones):
            errs.append(f"POSTCONDITION fail: {r} at ({x:.1f},{y:.1f}) "
                        f"outside {subsystem} zone(s)")
    if missing:
        print(f"  note: {len(missing)} {subsystem} netlist refs not on board "
              f"(dropped TPs): {missing[:8]}")
    return refs, errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subsystem", help="CH1 CH2 CH3 CH4 S1 S2 S3 S5 S6")
    ap.add_argument("--board", default="hardware/kicad/pcbai_fpv4in1_parked.kicad_pcb")
    ap.add_argument("--out", default=None, help="defaults to in-place on --board")
    args = ap.parse_args()
    out = args.out or args.board

    board = pcbnew.LoadBoard(args.board)
    brought, errs = bring_selected(board, args.subsystem)
    print(f"{args.subsystem}: brought {len(brought)} components into zone")
    if errs:
        print("ERRORS:")
        for e in errs:
            print(f"  {e}")
        return 1
    pcbnew.SaveBoard(out, board)
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
