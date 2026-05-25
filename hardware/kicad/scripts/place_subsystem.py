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
import math
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
    # Compare canonical side via IsFlipped() — GetLayerName() returns the board's
    # custom stackup display name, never bare "F.Cu"/"B.Cu", so a name compare
    # would flip everything wrongly.
    want_back = anchor.get("layer") == "B.Cu"
    if fp.IsFlipped() != want_back:
        fp.Flip(fp.GetPosition(), False)
    reset_text_to_body(fp)


def grid_placer(board, refs, zones):
    """Deterministic zone grid packer: 1.5mm pitch, 1mm inset, sorted by ref.
    LAST-RESORT only (R32: grid is banned as primary — fab-blocking pad overlaps +
    zero decoupling-anchoring). Used for refs without a routing_topology role."""
    x0, y0, x1, y1 = zones[0]
    inset, pitch = 1.0, 1.5
    cols = max(1, int((x1 - x0 - 2 * inset) / pitch))
    for i, ref in enumerate(sorted(refs, key=_ref_sort_key)):
        fp = board.FindFootprintByReference(ref)
        col, row = i % cols, i // cols
        fp.SetPosition(pcbnew.VECTOR2I(int((x0 + inset + col * pitch) * 1e6),
                                       int((y0 + inset + row * pitch) * 1e6)))
        reset_text_to_body(fp)


# ─── Real role-based placement engine (PLACEMENT_METHODOLOGY §2 bringSelected) ──

CLEARANCE_MM = 0.3   # IPC-7351 body-to-body minimum (edge-to-edge)
MIN_CENTER_MM = 1.6  # > audit COINCIDENT-PLACEMENT 1.5mm same-layer threshold


def _pad_bbox(fp):
    """Footprint copper extent from pads only (avoids the GetBoundingBox text trap).
    Returns (x0, y0, x1, y1) in mm."""
    xs, ys = [], []
    for p in fp.Pads():
        c = p.GetPosition()
        sz = p.GetSize()
        hx, hy = sz.x / 2e6, sz.y / 2e6
        xs += [c.x / 1e6 - hx, c.x / 1e6 + hx]
        ys += [c.y / 1e6 - hy, c.y / 1e6 + hy]
    if not xs:
        c = fp.GetPosition()
        return (c.x / 1e6, c.y / 1e6, c.x / 1e6, c.y / 1e6)
    return (min(xs), min(ys), max(xs), max(ys))


def _overlap(a, b, clr=CLEARANCE_MM):
    return not (a[2] + clr <= b[0] or b[2] + clr <= a[0]
                or a[3] + clr <= b[1] or b[3] + clr <= a[1])


def _parent_pad_pos(board, parent_ref, pin):
    fp = board.FindFootprintByReference(parent_ref)
    if fp is None:
        return None, None
    for p in fp.Pads():
        if p.GetPadName() == str(pin):
            c = p.GetPosition()
            return (c.x / 1e6, c.y / 1e6), fp
    c = fp.GetPosition()
    return (c.x / 1e6, c.y / 1e6), fp


def _spiral_offsets(max_r, step=0.6):
    """Candidate offsets (dx,dy) outward from a parent pad, nearest first."""
    out = [(0.0, 0.0)]
    r = step
    while r <= max_r + 1e-9:
        for ang in range(0, 360, 30):
            out.append((r * math.cos(math.radians(ang)),
                        r * math.sin(math.radians(ang))))
        r += step
    return out


def role_place(board, refs, zones, roles):
    """Place role-classified components per PLACEMENT_METHODOLOGY: cluster-anchor
    ICs in-zone (or near a foundation anchor), then passives ≤max_distance from
    their parent's pad, same layer, collision-free, in-zone. Deterministic; refs
    whose parent can't be resolved are returned as failures (no silent fallback)."""
    inv = ce.parse_board_invariants()
    highways = [(h[1], h[2], h[3], h[4]) for h in inv.highways]
    ox0, oy0, ox1, oy1 = inv.outline if inv.outline else (0.0, 0.0, 100.0, 100.0)
    EDGE_MARGIN = 3.0                  # G17: non-connector comps ≥3mm from board edge
    placed = {}                       # ref -> (bbox, is_back) of committed placement
    occupied = []                     # (bbox, cx, cy, is_back) already on board
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if r not in refs:             # foundation + already-brought + parked
            x = fp.GetPosition().x / 1e6
            if -2 <= x <= 102:        # only on-board obstacles matter
                bb = _pad_bbox(fp)
                occupied.append((bb, (bb[0]+bb[2])/2, (bb[1]+bb[3])/2, fp.IsFlipped()))

    def fits(bbox, want_back):
        # Layer-aware: F.Cu and B.Cu components share the board outline but not
        # copper — collisions only matter between SAME-side parts (Sai opt-(a):
        # LS FETs on B.Cu sit under HS FETs on F.Cu, halving top-side density).
        cx, cy = (bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2
        if not any(z[0] <= cx <= z[2] and z[1] <= cy <= z[3] for z in zones):
            return False
        # G17 board-edge keepout: the whole footprint (pad bbox) ≥ EDGE_MARGIN in.
        if (bbox[0] < ox0 + EDGE_MARGIN or bbox[1] < oy0 + EDGE_MARGIN or
                bbox[2] > ox1 - EDGE_MARGIN or bbox[3] > oy1 - EDGE_MARGIN):
            return False
        # G6 highway reservation: no pad bbox may intersect a reserved corridor.
        for hx0, hy0, hx1, hy1 in highways:
            if not (bbox[2] <= hx0 or hx1 <= bbox[0] or bbox[3] <= hy0 or hy1 <= bbox[1]):
                return False
        for ob, ocx, ocy, ob_back in occupied:
            if ob_back != want_back:
                continue
            if _overlap(bbox, ob) or math.hypot(cx-ocx, cy-ocy) < MIN_CENTER_MM:
                return False
        for pb, pb_back in placed.values():
            if pb_back != want_back:
                continue
            pcx, pcy = (pb[0]+pb[2])/2, (pb[1]+pb[3])/2
            if _overlap(bbox, pb) or math.hypot(cx-pcx, cy-pcy) < MIN_CENTER_MM:
                return False
        return True

    def want_back_of(rec, pfp):
        lyr = rec.get("layer")
        if lyr == "B.Cu":
            return True
        if lyr == "F.Cu":
            return False
        return pfp.IsFlipped() if (rec.get("same_layer_as_parent") and pfp) else False

    def place_fp_at(fp, x, y, want_back=False):
        if fp.IsFlipped() != want_back:
            fp.Flip(fp.GetPosition(), False)
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        reset_text_to_body(fp)
        # reset_text_to_body hides refs on R/C/D/TP; small inductors/others (e.g.
        # 0201 L11) keep visible refs that land on neighbour pads (SILK-ON-PAD).
        # Hide the ref on any small passive (pad-bbox < 3mm) the helper missed.
        bb = _pad_bbox(fp)
        if max(bb[2] - bb[0], bb[3] - bb[1]) < 3.0:
            rf = fp.Reference()
            if rf is not None:
                rf.SetVisible(False)

    errs = []
    # Phase A: cluster-anchor ICs.
    anchors_lf = lockfile.load_anchors()
    for r in [x for x in refs if roles[x].get("role") == "cluster-anchor"]:
        rec = roles[r]
        fp = board.FindFootprintByReference(r)
        if rec.get("near_anchor") and rec["near_anchor"] in anchors_lf:
            ax, ay = anchors_lf[rec["near_anchor"]]["pos"]
            ox, oy = rec.get("near_offset", [0.0, 0.0])
            base = (ax + ox, ay + oy)
        else:
            base = tuple(rec.get("zone_hint", [(zones[0][0]+zones[0][2])/2,
                                               (zones[0][1]+zones[0][3])/2]))
        wb = want_back_of(rec, None)
        if fp.IsFlipped() != wb:
            fp.Flip(fp.GetPosition(), False)
        for dx, dy in _spiral_offsets(8.0):
            fp.SetPosition(pcbnew.VECTOR2I(int((base[0]+dx)*1e6), int((base[1]+dy)*1e6)))
            bb = _pad_bbox(fp)
            if fits(bb, wb):
                place_fp_at(fp, base[0]+dx, base[1]+dy, wb)
                placed[r] = (_pad_bbox(fp), wb)
                break
        else:
            errs.append(f"role_place: no slot for cluster-anchor {r}")

    # Phase B: passives, resolving parent first (iterate until stable).
    pending = [x for x in refs if roles[x].get("role") in
               ("decoupling", "cluster-member", "cluster-aux")]
    progress = True
    while pending and progress:
        progress = False
        for r in list(pending):
            rec = roles[r]
            parent = rec.get("parent")
            if parent in refs and parent not in placed and parent in [
                    x for x in refs if roles[x].get("role") in
                    ("decoupling", "cluster-member")]:
                continue  # parent is a passive not yet placed → defer
            ppos, pfp = _parent_pad_pos(board, parent, rec.get("parent_pin", "1"))
            if ppos is None:
                errs.append(f"role_place: {r} parent {parent} not found")
                pending.remove(r); progress = True; continue
            fp = board.FindFootprintByReference(r)
            maxd = float(rec.get("max_distance_mm", 3))
            # Ring candidates around the parent BODY centre, reaching maxd past the
            # parent's half-diagonal — a big IC's decoupling caps distribute around
            # its perimeter (near its VDD pins) instead of piling on one pad.
            pbb = _pad_bbox(pfp) if pfp is not None else (ppos[0], ppos[1], ppos[0], ppos[1])
            pcx, pcy = (pbb[0] + pbb[2]) / 2, (pbb[1] + pbb[3]) / 2
            half_diag = 0.5 * math.hypot(pbb[2] - pbb[0], pbb[3] - pbb[1])
            search_r = maxd + half_diag
            wb = want_back_of(rec, pfp)
            if fp.IsFlipped() != wb:
                fp.Flip(fp.GetPosition(), False)
            # Try the preferred side, then (for non-loop passives) overflow to the
            # opposite side — Sai's B.Cu decoupling strategy: a bypass/filter cap
            # that can't fit a saturated F.Cu region drops to the roomy backside
            # rather than stretching its trace. Loop-members (FET/shunt) never flip.
            # Decoupling caps must stay on their IC's side (R25/G4) — never overflow.
            # Loop members (FET/shunt) never flip. Other aux passives may overflow.
            can_flip = not rec.get("loop_member") and rec.get("role") != "decoupling"
            sides = [wb, not wb] if can_flip else [wb]
            done = False
            for side in sides:
                if fp.IsFlipped() != side:
                    fp.Flip(fp.GetPosition(), False)
                for dx, dy in _spiral_offsets(search_r):
                    cx, cy = pcx + dx, pcy + dy
                    fp.SetPosition(pcbnew.VECTOR2I(int(cx * 1e6), int(cy * 1e6)))
                    bb = _pad_bbox(fp)
                    if fits(bb, side):
                        place_fp_at(fp, cx, cy, side)
                        placed[r] = (_pad_bbox(fp), side)
                        done = True
                        break
                if done:
                    break
            # Last resort for non-critical aux passives (not decoupling, not a loop
            # member): if no slot near the parent on either side, place anywhere
            # valid in the zone (B.Cu first — it's roomy and these are not
            # distance-critical). Keeps the cluster's critical parts tight while
            # guaranteeing 0-unplaced. Decoupling/loop parts never use this.
            if not done and can_flip:
                z = zones[0]
                for side in (True, False):  # B.Cu first
                    if fp.IsFlipped() != side:
                        fp.Flip(fp.GetPosition(), False)
                    step = 0.5  # finer than MIN_CENTER so spread placement's gaps are found
                    yy = z[1] + 1
                    while yy <= z[3] - 1 and not done:
                        xx = z[0] + 1
                        while xx <= z[2] - 1:
                            fp.SetPosition(pcbnew.VECTOR2I(int(xx*1e6), int(yy*1e6)))
                            bb = _pad_bbox(fp)
                            if fits(bb, side):
                                place_fp_at(fp, xx, yy, side)
                                placed[r] = (_pad_bbox(fp), side)
                                done = True
                                break
                            xx += step
                        yy += step
                    if done:
                        break
            pending.remove(r)
            progress = True
            if not done:
                errs.append(f"role_place: no slot ≤{search_r:.1f}mm for {r} near {parent} (both sides + zone-fill)")
    for r in pending:
        errs.append(f"role_place: unresolved parent chain for {r}")
    return errs


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
    # Lockfile anchors (foundation + motor pads + SWD/BOOT TPs + LEDs) are placed at
    # fixed coords by park / the Stage-1 TIER1 bring — NOT by the per-subsystem
    # cluster bring. Exclude them; role_place uses the placed motor pads as parents.
    want = {r for r, s in roster.items() if s == subsystem} - foundation - set(anchors)
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
    # 2. Non-anchor components: real role-based placement (routing_topology), else
    #    last-resort grid for refs with no role yet.
    rest = [r for r in refs if r not in anchors]
    role_placed = [r for r in rest if r in roles]
    grid_rest = [r for r in rest if r not in roles]
    errs = []
    if role_placed:
        errs += role_place(board, role_placed, zones,
                           {r: roles[r] for r in role_placed})
    if grid_rest:
        grid_placer(board, grid_rest, zones)

    stats = {"anchored": len(anchored), "role": len(role_placed),
             "grid": len(grid_rest)}

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


def bring_anchors(board):
    """Stage 1 (Tier-1): place every parked lockfile anchor at its lockfile
    coordinate. Foundation is already placed by park; this brings the rest
    (motor pads, SWD/BOOT test points, status LEDs) so Tier-2 channel clusters
    can anchor to the motor pads. Returns (placed_refs, errors)."""
    anchors = lockfile.load_anchors()
    placed, errs = [], []
    for ref, a in anchors.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        place_at_anchor(fp, a)
        placed.append(ref)
        ax, ay = a["pos"]
        p = fp.GetPosition()
        if abs(p.x / 1e6 - ax) > ANCHOR_TOL_MM or abs(p.y / 1e6 - ay) > ANCHOR_TOL_MM:
            errs.append(f"POSTCONDITION fail: {ref} at "
                        f"({p.x/1e6:.3f},{p.y/1e6:.3f}) != lockfile ({ax},{ay})")
    return placed, errs


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
    ap.add_argument("subsystem", help="TIER1 | CH1 CH2 CH3 CH4 S1 S2 S3 S5 S6")
    ap.add_argument("--board", default="hardware/kicad/pcbai_fpv4in1_parked.kicad_pcb")
    ap.add_argument("--out", default=None, help="defaults to in-place on --board")
    ap.add_argument("--render", action="store_true",
                    help="generate the G11 vision-check render set after bring")
    args = ap.parse_args()
    out = args.out or args.board

    board = pcbnew.LoadBoard(args.board)
    if args.subsystem == "TIER1":
        brought, errs = bring_anchors(board)
        stats = {}
        print(f"TIER1: placed {len(brought)} lockfile anchors at lockfile coords")
    else:
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
