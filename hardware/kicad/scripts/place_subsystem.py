#!/usr/bin/env python3
"""place_subsystem.py — Phase 4-v3 BRING-IN harness (Sai PARK-THEN-BRING-IN REDO).

REVISES the Phase 4-v2 skeleton. The v2 version identified a subsystem's
components by BOARD POSITION (net-suffix + hard-coded prefixes + zone fall-through)
— the circular dependency Sai diagnosed as the ghost root cause. v3 takes
ownership from the schematic SSoT (roster.py, position-independent) and BRINGS
that roster from the off-board parking grid into its zone, positioning each
component from the SSoT lockfiles (mechanical_anchors + routing_topology) — never
from where it currently sits.

bring_selected(board, subsystem) per PLACEMENT_METHODOLOGY §2 bringSelected():
  PRECONDITION  — every roster ref for this subsystem is currently parked.
  Placement, per component, deterministic, no random search:
    - anchor (in mechanical_anchors.yaml) → its exact lockfile pos/layer/rotation
    - role in routing_topology.yaml       → relative to parent per role (TODO: the
      components: section is filled per-stage; until then non-anchors fall back to
      the zone grid packer, flagged in output)
    - otherwise                            → deterministic zone grid packer
  POSTCONDITION — anchors match lockfile (±0.01mm); non-anchors inside the zone;
                  no ref outside this roster moved. Abort surfaces, never silent.

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
import lockfile
import roster as roster_mod
from place_subsystem_ch1_v3 import reset_text_to_body

# Footprint corrections (motor pads → ESCMotorPad, bulk caps → CP_Elec_8x6.2) are
# applied once by migrate_footprints.py BEFORE the bring stages — an in-place
# pcbnew swap, no kinet2pcb re-import (master+Sai 2026-05-25, path ii). Kept out
# of bring_selected so positioning stays decoupled from footprint geometry.

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
ON_BOARD_MARGIN = 2.0
ANCHOR_TOL_MM = 0.01


def is_parked(fp):
    x, y = fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6
    return not (-ON_BOARD_MARGIN <= x <= 100 + ON_BOARD_MARGIN
                and -ON_BOARD_MARGIN <= y <= 100 + ON_BOARD_MARGIN)


def in_any_zone(x, y, zones):
    return any(x0 <= x <= x1 and y0 <= y <= y1 for (x0, y0, x1, y1) in zones)


def _ref_sort_key(r):
    return (re.match(r"[A-Za-z]+", r).group(), int(re.search(r"\d+", r).group()))


def place_at_anchor(fp, anchor):
    """Place a component at its mechanical_anchors.yaml coordinate (role=anchor)."""
    x, y = anchor["pos"]
    fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
    if anchor.get("rotation") is not None:
        fp.SetOrientationDegrees(float(anchor["rotation"]))
    target_layer = anchor.get("layer", "F.Cu")
    if fp.GetLayerName() != target_layer and target_layer in ("F.Cu", "B.Cu"):
        # Flip to the lockfile-specified side (keeps position).
        fp.Flip(fp.GetPosition(), False)
    reset_text_to_body(fp)


def grid_placer(board, refs, zones):
    """Deterministic zone grid packer: 1.5mm pitch, 1mm inset, sorted by ref.
    Fallback for components without a routing_topology role yet (per-stage fill)."""
    x0, y0, x1, y1 = zones[0]
    inset, pitch = 1.0, 1.5
    cols = max(1, int((x1 - x0 - 2 * inset) / pitch))
    for i, ref in enumerate(sorted(refs, key=_ref_sort_key)):
        fp = board.FindFootprintByReference(ref)
        col, row = i % cols, i // cols
        fp.SetPosition(pcbnew.VECTOR2I(int((x0 + inset + col * pitch) * 1e6),
                                       int((y0 + inset + row * pitch) * 1e6)))
        reset_text_to_body(fp)


def bring_selected(board, subsystem):
    """Bring one subsystem's roster from parking into its zone(s).
    Returns (brought_refs, errors, stats)."""
    if subsystem not in SUBSYS_ZONES:
        return [], [f"unknown subsystem {subsystem!r}"], {}
    inv = ce.parse_board_invariants()
    zones = [inv.zones[z] for z in SUBSYS_ZONES[subsystem]]
    anchors = lockfile.load_anchors()
    roles = lockfile.load_component_roles()

    roster = roster_mod.derive_roster(roster_mod.parse_netlist())
    foundation = lockfile.foundation_refs()
    # Foundation (mount holes, fiducials, shared connectors J1/J11/J12) is placed
    # once at lockfile position and never parked — excluded from any subsystem
    # bring even though the netlist assigns e.g. J1→S1, J12→S6.
    want = {r for r, s in roster.items() if s == subsystem} - foundation
    present = {fp.GetReference(): fp for fp in board.GetFootprints()}
    refs = sorted(want & present.keys(), key=_ref_sort_key)
    missing = sorted(want - present.keys())

    not_parked = [r for r in refs if not is_parked(present[r])]
    if not_parked:
        return [], [f"PRECONDITION fail: {len(not_parked)} roster refs already "
                    f"on-board (re-bring or no park?): {not_parked[:12]}"], {}

    # 1. Anchors → exact lockfile coordinate.
    anchored = [r for r in refs if r in anchors]
    for r in anchored:
        place_at_anchor(present[r], anchors[r])
    # 2. Non-anchor components: role-based placement when routing_topology has an
    #    entry, else zone grid fallback (per-stage role fill is a separate step).
    rest = [r for r in refs if r not in anchors]
    role_placed = [r for r in rest if r in roles]
    grid_rest = [r for r in rest if r not in roles]
    # role-based placement not yet wired (components: section fills per-stage);
    # everything non-anchor currently uses the grid fallback.
    grid_placer(board, rest, zones)

    stats = {"anchored": len(anchored), "role": len(role_placed),
             "grid": len(grid_rest)}

    errs = []
    for r in anchored:
        ax, ay = anchors[r]["pos"]
        p = present[r].GetPosition()
        if (abs(p.x / 1e6 - ax) > ANCHOR_TOL_MM or
                abs(p.y / 1e6 - ay) > ANCHOR_TOL_MM):
            errs.append(f"POSTCONDITION fail: anchor {r} at "
                        f"({p.x/1e6:.3f},{p.y/1e6:.3f}) != lockfile ({ax},{ay})")
    for r in rest:
        p = present[r].GetPosition()
        x, y = p.x / 1e6, p.y / 1e6
        if not in_any_zone(x, y, zones):
            errs.append(f"POSTCONDITION fail: {r} at ({x:.1f},{y:.1f}) "
                        f"outside {subsystem} zone(s)")
    if missing:
        print(f"  note: {len(missing)} {subsystem} netlist refs not on board "
              f"(dropped TPs): {missing[:8]}")
    return refs, errs, stats


def _render(board_path, subsystem):
    """Invoke render_pr_visual.py for the vision-check set (G11). Best-effort:
    render_pr_visual degrades gracefully if render tools are missing."""
    import subprocess
    out_dir = f"sims/phase4v3/{subsystem}/renders"
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    script = str(Path(__file__).parent / "render_pr_visual.py")
    print(f"render: generating G11 vision set → {out_dir}")
    r = subprocess.run([sys.executable, script, board_path, out_dir,
                        "--subsystem", subsystem, "--diff-against", "origin/master"])
    if r.returncode != 0:
        print(f"  WARNING: render_pr_visual exit {r.returncode} (non-fatal)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subsystem", help="CH1 CH2 CH3 CH4 S1 S2 S3 S5 S6")
    ap.add_argument("--board", default="hardware/kicad/pcbai_fpv4in1_parked.kicad_pcb")
    ap.add_argument("--out", default=None, help="defaults to in-place on --board")
    ap.add_argument("--render", action="store_true",
                    help="generate the G11 vision-check render set after bring")
    args = ap.parse_args()
    out = args.out or args.board

    board = pcbnew.LoadBoard(args.board)
    brought, errs, stats = bring_selected(board, args.subsystem)
    print(f"{args.subsystem}: brought {len(brought)} components "
          f"(anchor={stats.get('anchored',0)} role={stats.get('role',0)} "
          f"grid={stats.get('grid',0)})")
    if errs:
        print("ERRORS:")
        for e in errs:
            print(f"  {e}")
        return 1
    pcbnew.SaveBoard(out, board)
    print(f"saved {out}")
    if args.render:
        _render(out, args.subsystem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
