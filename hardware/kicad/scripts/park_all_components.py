#!/usr/bin/env python3
"""park_all_components.py — Phase 4-v3 PARK step (Sai PARK-THEN-BRING-IN REDO).

Produces the empty starting board: every placeable component moved to the
off-board parking grid, the immovable FOUNDATION (mount holes, fiducials, shared
connectors) left at its lockfile position, all tracks/vias stripped. Each
per-subsystem PR then BRINGS its roster onto the board (place_subsystem.py); a
component a PR does not touch stays parked — so every per-PR full-board audit has
no hidden "ghost" components in stale positions (the PR #91-99 failure).

SSoT: parking grid + foundation skip-set come from mechanical_anchors.yaml via
lockfile.py — no hardcoded coords (R32, PHASE4V3_PLAN §6). Motor pads / test
points / status LEDs are NOT foundation: they are parked here and brought to
their lockfile coordinate by their owning subsystem PR (master 2026-05-25).

Why park (move) not remove: removing forces a kinet2pcb re-import that silently
drops nets ([[reference-kinet2pcb-silent-drop]]). Parking preserves every
footprint, pad, and net from the locked netlist import.

Usage:
  python3 park_all_components.py --in BOARD --out PARKED [--report]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pcbnew
import lockfile
from place_subsystem_ch1_v3 import reset_text_to_body
import roster as roster_mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp",
                    default="hardware/kicad/pcbai_fpv4in1.kicad_pcb")
    ap.add_argument("--out", dest="out",
                    default="hardware/kicad/pcbai_fpv4in1_parked.kicad_pcb")
    ap.add_argument("--report", action="store_true", help="print plan, do not save")
    args = ap.parse_args()

    grid = lockfile.parking_grid()
    foundation = lockfile.foundation_refs()
    anchors = lockfile.load_anchors()
    roster = roster_mod.derive_roster(roster_mod.parse_netlist())

    ox, oy = grid["origin"]
    pitch, cols = grid["spacing"], grid["cols"]

    def slot(i):
        return (ox + (i % cols) * pitch, oy + (i // cols) * pitch)

    board = pcbnew.LoadBoard(args.inp)
    fps = list(board.GetFootprints())
    placeable = [fp for fp in fps if fp.GetReference() not in foundation]
    kept = [fp for fp in fps if fp.GetReference() in foundation]

    # Deterministic order (subsystem, ref) so a re-park reproduces every slot.
    def sort_key(fp):
        ref = fp.GetReference()
        m = re.match(r"([A-Za-z]+)(\d+)", ref)
        return (roster.get(ref, "ZZZ"), m.group(1) if m else ref,
                int(m.group(2)) if m else 0)

    placeable.sort(key=sort_key)

    print(f"loaded {args.inp}: {len(fps)} footprints "
          f"({len(kept)} foundation kept, {len(placeable)} placeable)")
    print(f"parking grid: origin {grid['origin']} pitch {pitch}mm cols {cols}")

    if args.report:
        print(f"[report] would park {len(placeable)}, strip "
              f"{len(list(board.GetTracks()))} tracks/vias")
        print(f"[report] foundation kept: {sorted(fp.GetReference() for fp in kept)}")
        return 0

    for i, fp in enumerate(placeable):
        x, y = slot(i)
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        reset_text_to_body(fp)

    # Foundation is not parked, but on a REDO from the inherited board it sits at
    # stale v2 positions — snap it to its lockfile coordinate so Tier-1 anchors
    # (mount holes, fiducials, J1/J12/J14) are correct from the empty board on.
    for fp in kept:
        a = anchors.get(fp.GetReference())
        if not a:
            continue
        x, y = a["pos"]
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        if a.get("rotation") is not None:
            fp.SetOrientationDegrees(float(a["rotation"]))
        # Compare canonical side via IsFlipped() — GetLayerName() returns the
        # board's custom stackup display name (e.g. "B.Cu 3oz — …"), never the
        # bare "F.Cu"/"B.Cu", so a name compare would flip everything wrongly.
        want_back = a.get("layer") == "B.Cu"
        if fp.IsFlipped() != want_back:
            fp.Flip(fp.GetPosition(), False)
        reset_text_to_body(fp)

    tracks = list(board.GetTracks())
    for t in tracks:
        board.Remove(t)

    pcbnew.SaveBoard(args.out, board)
    chk = pcbnew.LoadBoard(args.out)
    on = [fp.GetReference() for fp in chk.GetFootprints()
          if fp.GetReference() not in foundation
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
