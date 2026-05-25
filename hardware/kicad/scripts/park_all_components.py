#!/usr/bin/env python3
"""park_all_components.py — Phase 4-v3 PARK step (Sai PARK-THEN-BRING-IN REDO).

Produces the EMPTY starting board: every placeable component moved to an
off-board parking grid, fixed mechanical geometry (mount holes, fiducials) left
in place, all tracks/vias stripped. Each subsequent per-subsystem PR then BRINGS
its roster onto the board (place_subsystem.py). Components a PR does not touch
stay parked — so by construction every per-PR audit sees the FULL board with no
hidden "ghost" components in stale positions. That ghost accumulation across
PR #91-99 is the failure this REDO fixes.

Why park (move) instead of remove: removing footprints forces a kinet2pcb
re-import to get them back, which silently drops nets when SKiDL pin names ≠
footprint pad numbers ([[reference-kinet2pcb-silent-drop]]). Parking preserves
every footprint, pad, and net assignment from the locked netlist import.

Parking grid lives at x >= PARK_X0 (>> 100mm board), 5mm pitch, deterministic
order (roster subsystem, then ref) so a re-park is reproducible and a parked
component's slot is stable across runs.

Usage:
  python3 park_all_components.py --in BOARD --out PARKED [--report]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pcbnew
from place_subsystem_ch1_v3 import reset_text_to_body
import roster as roster_mod

PARK_X0 = 130.0      # board is 0-100mm; 130 is unambiguously off-board
PARK_Y0 = 5.0
PARK_PITCH = 5.0
PARK_COLS = 24       # 24 cols * 5mm = 120mm wide parking field (x 130-245)
FIXED_RE = re.compile(r"^(FID|H)\d+$")


def is_fixed(ref):
    return bool(FIXED_RE.match(ref))


def parking_slot(index):
    col = index % PARK_COLS
    row = index // PARK_COLS
    return (PARK_X0 + col * PARK_PITCH, PARK_Y0 + row * PARK_PITCH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp",
                    default="hardware/kicad/pcbai_fpv4in1.kicad_pcb")
    ap.add_argument("--out", dest="out",
                    default="hardware/kicad/pcbai_fpv4in1_parked.kicad_pcb")
    ap.add_argument("--report", action="store_true",
                    help="print plan without saving")
    args = ap.parse_args()

    comps = roster_mod.parse_netlist()
    roster = roster_mod.derive_roster(comps)

    board = pcbnew.LoadBoard(args.inp)
    fps = list(board.GetFootprints())

    placeable = [fp for fp in fps if not is_fixed(fp.GetReference())]
    fixed = [fp for fp in fps if is_fixed(fp.GetReference())]

    # Deterministic order: subsystem, then ref number. Unknown-roster refs (the
    # netlist TPs absent here are simply not present) sort last but still park.
    def sort_key(fp):
        ref = fp.GetReference()
        sub = roster.get(ref, "ZZZ")
        m = re.match(r"([A-Za-z]+)(\d+)", ref)
        return (sub, m.group(1) if m else ref, int(m.group(2)) if m else 0)

    placeable.sort(key=sort_key)

    print(f"loaded {args.inp}: {len(fps)} footprints "
          f"({len(fixed)} fixed, {len(placeable)} placeable)")

    for i, fp in enumerate(placeable):
        x, y = parking_slot(i)
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        reset_text_to_body(fp)

    tracks = list(board.GetTracks())
    if args.report:
        print(f"[report] would park {len(placeable)} comps to grid "
              f"x>={PARK_X0} pitch {PARK_PITCH}mm, strip {len(tracks)} tracks/vias")
        print(f"[report] fixed kept in place: {sorted(fp.GetReference() for fp in fixed)}")
        return 0

    for t in tracks:
        board.Remove(t)

    pcbnew.SaveBoard(args.out, board)
    # Verify the artifact: re-load and confirm everything is off-board.
    chk = pcbnew.LoadBoard(args.out)
    on = [fp.GetReference() for fp in chk.GetFootprints()
          if not is_fixed(fp.GetReference())
          and -2 <= fp.GetPosition().x / 1e6 <= 102
          and -2 <= fp.GetPosition().y / 1e6 <= 102]
    print(f"parked {len(placeable)} comps, stripped {len(tracks)} tracks/vias")
    print(f"saved {args.out}")
    if on:
        print(f"ERROR: {len(on)} placeable comps still on-board: {on[:10]}")
        return 1
    print("verify: 0 placeable comps on-board (all parked) — OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
