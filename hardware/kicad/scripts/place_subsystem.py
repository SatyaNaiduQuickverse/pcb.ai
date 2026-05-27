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

# G_PP19: reserved inter-cluster routing channels are SSoT'd by the parametric
# engine. Compute the zone list ONCE here — is_position_forbidden() rebuilds it on
# every call (~38ms), which the spiral invokes O(10^5) times → hours. Guarded so
# the placer still runs against pre-#142 boards/checkouts.
try:
    from parametric_placement import (placement_forbidden_zones as _forbidden_zones_fn,
                                       BoardParameters as _BoardParameters)
    _FORBIDDEN_ZONES = _forbidden_zones_fn(_BoardParameters())
except Exception:  # engine absent → skip channel reservation (audit still gates)
    _FORBIDDEN_ZONES = None

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
# Per-phase symmetry transform — gated off until J18/J19 placement is resolved
# clear of the 3-phase FET column (see replicate_phases docstring).
PHASE_REPLICATE = True
PHASE_LOOKAHEAD = True  # phantom keep-out (needs TP2/TP7 moved out of FET column first)
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


def _body_bbox(fp):
    """Component BODY envelope (x0,y0,x1,y1 mm) for collision — the courtyard, else
    silk, else pad bbox. Unlike _pad_bbox this includes the package body, so parts
    with small pads but large bodies (SOD-323 diodes, LEDs, SOIC ICs) don't overlap
    each other's bodies while their pads clear (G_PP11 / Sai 2026-05-26 catch)."""
    cxs, cys, sxs, sys_ = [], [], [], []
    for d in fp.GraphicalItems():
        if not isinstance(d, pcbnew.PCB_SHAPE):
            continue
        lyr = d.GetLayer()
        bb = d.GetBoundingBox()
        if lyr in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            cxs += [bb.GetLeft()/1e6, bb.GetRight()/1e6]
            cys += [bb.GetTop()/1e6, bb.GetBottom()/1e6]
        elif lyr in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            sxs += [bb.GetLeft()/1e6, bb.GetRight()/1e6]
            sys_ += [bb.GetTop()/1e6, bb.GetBottom()/1e6]
    if cxs:
        return (min(cxs), min(cys), max(cxs), max(cys))
    pb = _pad_bbox(fp)
    if sxs:  # union silk with pads (silk alone can miss pad extent)
        return (min(min(sxs), pb[0]), min(min(sys_), pb[1]),
                max(max(sxs), pb[2]), max(max(sys_), pb[3]))
    return pb


def _layers(fp):
    """Which copper sides a footprint actually occupies, from its pad layer sets.
    A part with a thru-hole / thermal-via pad (e.g. the MCU's exposed-pad thermal
    field) occupies BOTH sides, so it must block placement on the back even though
    the body sits on the front. Returns (has_F, has_B)."""
    hf = hb = False
    for p in fp.Pads():
        ls = p.GetLayerSet()
        if ls.Contains(pcbnew.F_Cu):
            hf = True
        if ls.Contains(pcbnew.B_Cu):
            hb = True
        if hf and hb:
            break
    if not (hf or hb):                # no copper pads (fiducial/mech) → mounted side
        return (not fp.IsFlipped(), fp.IsFlipped())
    return (hf, hb)


# ----- motor-pad clear-zone (mirrors G5 audit so placer + audit agree) -----
# High-current motor terminal pads need 14-16AWG solder clearance: no component
# within pad bbox + 2mm, EXCEPT topologically-required motor-adjacent-net parts
# (master path D 2026-05-24 + 2026-05-26 VMOTOR addition). See
# feedback-motor-pad-clear-zone.
MOTOR_TP_REFS = ('TP19', 'TP20', 'TP21', 'TP26', 'TP27', 'TP28',
                 'TP33', 'TP34', 'TP35', 'TP40', 'TP41', 'TP42')
MOTOR_PAD_KEEPOUT_MM = 2.0
_MOTOR_ADJ_NET_RE = re.compile(
    r'^(MOTOR_[ABC]_CH\d+'
    r'|BEMF_[ABC]_CH\d+'
    r'|CSA_[ABC]_OUT_CH\d+'
    r'|CSA_MAX_CH\d+'
    r'|SHUNT_[ABC]_TOP_CH\d+'
    r'|GH[ABC]_CH\d+|GL[ABC]_CH\d+'
    r'|BST[ABC]_CH\d+'
    r'|\+?VMOTOR(_CH\d*)?'              # motor power rail bulk (master 2026-05-26)
    r')$'
)


def _is_motor_adjacent(fp):
    """True if any pad sits on a motor-adjacent net → exempt from motor keep-out."""
    for pad in fp.Pads():
        no = pad.GetNet()
        if no is None:
            continue
        try:
            n = no.GetNetname()
        except Exception:
            continue
        if _MOTOR_ADJ_NET_RE.match(n):
            return True
    return False


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


def role_place(board, refs, zones, roles, extra_keepouts=()):
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
    motor_keepouts = []               # (x0,y0,x1,y1) = motor TP pad bbox + 2mm
    K = MOTOR_PAD_KEEPOUT_MM
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if r in MOTOR_TP_REFS:
            x = fp.GetPosition().x / 1e6
            if -2 <= x <= 102:
                b = _pad_bbox(fp)
                motor_keepouts.append((b[0]-K, b[1]-K, b[2]+K, b[3]+K))
        if r not in refs:             # foundation + already-brought + parked
            x = fp.GetPosition().x / 1e6
            if -2 <= x <= 102:        # only on-board obstacles matter
                bb = _body_bbox(fp)
                # Fiducials / mech marks: their ~1mm copper dot + silk refdes text
                # extend past the tiny pad bbox, so a passive can land under the silk
                # (G5 SILK-ON-PAD: FID silk on Cxx.pad1). Reserve a generous keepout
                # around the whole footprint so passives clear the mark + its silk.
                if r.startswith(("FID", "REF**")) or (bb[2]-bb[0] < 0.1 and bb[3]-bb[1] < 0.1):
                    fcx, fcy = (bb[0]+bb[2])/2, (bb[1]+bb[3])/2
                    FID_K = 2.5
                    bb = (fcx - FID_K, fcy - FID_K, fcx + FID_K, fcy + FID_K)
                hf, hb = _layers(fp)
                occupied.append((bb, (bb[0]+bb[2])/2, (bb[1]+bb[3])/2, hf, hb))
    # G5 motor keep-out: a component must clear motor-terminal pads unless it sits
    # on a motor-adjacent net (topologically required at the node). Precompute the
    # exempt set from the board's pad nets so placer ↔ audit agree.
    motor_exempt = {r for r in refs
                    if (fpx := board.FindFootprintByReference(r)) is not None
                    and _is_motor_adjacent(fpx)}
    # 0.6mm creepage halos around the gate driver's MOTOR (SW-node) pads — filled
    # after Phase A places the driver (so its pads are at final position).
    driver_keepouts = []

    def fits(bbox, want_back, motor_ok=True):
        # Layer-aware: F.Cu and B.Cu components share the board outline but not
        # copper — collisions only matter between SAME-side parts (Sai opt-(a):
        # LS FETs on B.Cu sit under HS FETs on F.Cu, halving top-side density).
        cx, cy = (bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2
        if not any(z[0] <= cx <= z[2] and z[1] <= cy <= z[3] for z in zones):
            return False
        # G_PP19: no body may intrude the reserved inter-cluster routing channels.
        if _FORBIDDEN_ZONES is not None:
            for fx0, fy0, fx1, fy1, _name in _FORBIDDEN_ZONES:
                if bbox[0] < fx1 and bbox[2] > fx0 and bbox[1] < fy1 and bbox[3] > fy0:
                    return False
        # G17 board-edge keepout: the whole footprint (pad bbox) ≥ EDGE_MARGIN in.
        if (bbox[0] < ox0 + EDGE_MARGIN or bbox[1] < oy0 + EDGE_MARGIN or
                bbox[2] > ox1 - EDGE_MARGIN or bbox[3] > oy1 - EDGE_MARGIN):
            return False
        # G6 highway reservation: no pad bbox may intersect a reserved corridor.
        for hx0, hy0, hx1, hy1 in highways:
            if not (bbox[2] <= hx0 or hx1 <= bbox[0] or bbox[3] <= hy0 or hy1 <= bbox[1]):
                return False
        # G5 motor-pad clear-zone: non-motor-adjacent parts must clear motor TP
        # pads + 2mm (high-current solder clearance). Exempt parts skip this.
        if not motor_ok:
            for mx0, my0, mx1, my1 in motor_keepouts:
                if not (bbox[2] <= mx0 or mx1 <= bbox[0] or bbox[3] <= my0 or my1 <= bbox[1]):
                    return False
            # G_PP10 / master option-1 (2026-05-26): non-MOTOR-domain pads must
            # clear the driver's MOTOR (SW-node, 27V) pins by 0.6mm creepage —
            # IPC-2221 B-grade for the SW↔logic domain gap. Defense-in-depth that
            # enforces the east MOTOR/LOGIC sub-zone split on every iteration.
            for dx0, dy0, dx1, dy1 in driver_keepouts:
                if not (bbox[2] <= dx0 or dx1 <= bbox[0] or bbox[3] <= dy0 or dy1 <= bbox[1]):
                    return False
        # Phase-replication look-ahead: when placing a reference phase, avoid spots
        # whose +pitch translations (the B/C copies) would land on foundation —
        # these are foundation obstacles shifted back by the phase offsets.
        for kx0, ky0, kx1, ky1 in extra_keepouts:
            if not (bbox[2] <= kx0 or kx1 <= bbox[0] or bbox[3] <= ky0 or ky1 <= bbox[1]):
                return False
        # A candidate on side `want_back` collides with an obstacle only if the
        # obstacle has copper on THAT side. Both-layer parts (MCU thermal pad,
        # thru-hole) block whichever side is being placed.
        side_has = (lambda hf, hb: hb if want_back else hf)
        for ob, ocx, ocy, ob_f, ob_b in occupied:
            if not side_has(ob_f, ob_b):
                continue
            if _overlap(bbox, ob) or math.hypot(cx-ocx, cy-ocy) < MIN_CENTER_MM:
                return False
        for pb, pf, pbk in placed.values():
            if not side_has(pf, pbk):
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
        bb = _body_bbox(fp)
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
            bb = _body_bbox(fp)
            if fits(bb, wb, motor_ok=(r in motor_exempt)):
                place_fp_at(fp, base[0]+dx, base[1]+dy, wb)
                _hf, _hb = _layers(fp)
                placed[r] = (_body_bbox(fp), _hf, _hb)
                break
        else:
            errs.append(f"role_place: no slot for cluster-anchor {r}")

    # Driver MOTOR-pin creepage halos (G_PP10): now the gate driver is placed,
    # reserve a 0.6mm halo around each of its MOTOR_x (SW-node) pads so Phase-B
    # non-MOTOR passives can't seat within IPC-2221 creepage of 27V SW pins.
    CREEP = 0.6
    for dr in [x for x in refs if roles[x].get("relation") == "gate-driver"]:
        dfp = board.FindFootprintByReference(dr)
        if dfp is None:
            continue
        for pad in dfp.Pads():
            n = pad.GetNetname() or ""
            if re.match(r"MOTOR_[ABC]_CH\d+$", n):
                c = pad.GetPosition(); sz = pad.GetSize()
                hx, hy = sz.x / 2e6 + CREEP, sz.y / 2e6 + CREEP
                driver_keepouts.append((c.x/1e6 - hx, c.y/1e6 - hy,
                                        c.x/1e6 + hx, c.y/1e6 + hy))

    # Phase B: passives, resolving parent first (iterate until stable).
    # Tightest constraint first: decoupling (≤3mm of a VDD pin) must claim the
    # pin-adjacent slots before looser cluster-aux/bulk caps crowd them out.
    _bprio = {"decoupling": 0, "cluster-member": 1, "cluster-aux": 2}
    # Loop members (HS/LS FETs, shunts) are the LARGE bodies of the switching cell
    # — place them BEFORE the small gate clamps/resistors so they claim their spot
    # and the clamps then seat NEXT TO them (body-clear), not on top. Otherwise
    # ref-order puts D-clamps before Q-FETs and the big FET can't fit (G_PP11).
    def _bkey(x):
        rec = roles[x]
        return (0 if rec.get("loop_member") else 1,
                _bprio[rec["role"]], _ref_sort_key(x))
    pending = sorted(
        [x for x in refs if roles[x].get("role") in _bprio], key=_bkey)
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
            half_diag = 0.5 * math.hypot(pbb[2] - pbb[0], pbb[3] - pbb[1])
            if rec.get("role") == "decoupling":
                # R25/G4: prefer ≤maxd of the specific VDD PIN — ring FROM the pin
                # (nearest-first spiral seats the cap ≤maxd when there's room, so
                # G4 passes). Radius is widened to cover the same reachable area a
                # body-centre ring would (maxd + half_diag past the parent body),
                # so an over-subscribed pin still finds a farther slot rather than
                # failing and dropping the whole subsystem's save.
                bcx = (pbb[0] + pbb[2]) / 2
                bcy = (pbb[1] + pbb[3]) / 2
                pcx, pcy = ppos[0], ppos[1]
                search_r = maxd + half_diag + math.hypot(pcx - bcx, pcy - bcy)
            else:
                # aux/cluster: ring around the IC BODY centre so they distribute
                # around the perimeter (reach maxd past the body).
                pcx = (pbb[0] + pbb[2]) / 2
                pcy = (pbb[1] + pbb[3]) / 2
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
            can_flip = (not rec.get("loop_member") and rec.get("role") != "decoupling"
                        and rec.get("relation") != "motor-clamp")
            sides = [wb, not wb] if can_flip else [wb]
            # HS FET sits to the LEFT of its motor pad (not on/above it): the B.Cu
            # LS FET stacked beneath must clear the pad's both-layer thru-via field
            # (~7.7×5.6mm FET over a 4.5×6mm pad ⇒ ≥~6.5mm offset), and a LEFT
            # (−X) offset keeps the cluster at the pad's Y-level so the replicated
            # phase-C copy stays clear of the CH-zone top edge (TPs / bus strips).
            is_hs = rec.get("relation") == "hs-fet"
            done = False
            for side in sides:
                if fp.IsFlipped() != side:
                    fp.Flip(fp.GetPosition(), False)
                # Explicit orientation (e.g. TVS clamp rotated 90° so the 7.4mm body
                # fits the ~5mm east MOTOR strip vertically) — set after the flip so
                # the spiral's body bbox reflects it.
                if rec.get("rotation") is not None:
                    fp.SetOrientationDegrees(float(rec["rotation"]))
                for dx, dy in _spiral_offsets(search_r):
                    if is_hs and not (dx <= -6.5 and abs(dy) <= 3.0):
                        continue
                    cx, cy = pcx + dx, pcy + dy
                    fp.SetPosition(pcbnew.VECTOR2I(int(cx * 1e6), int(cy * 1e6)))
                    bb = _body_bbox(fp)
                    if fits(bb, side, motor_ok=(r in motor_exempt)):
                        place_fp_at(fp, cx, cy, side)
                        _hf, _hb = _layers(fp); placed[r] = (_body_bbox(fp), _hf, _hb)
                        done = True
                        break
                if done:
                    break
            # Last resort for non-critical aux passives (not decoupling, not a loop
            # member): if no slot near the parent on either side, place anywhere
            # valid in the zone (B.Cu first — it's roomy and these are not
            # distance-critical). Keeps the cluster's critical parts tight while
            # guaranteeing 0-unplaced. Decoupling/loop parts never use this.
            # Shunts (loop-member) may also zone-fill, but on their OWN side only
            # (F.Cu) — keep them near the phase without flipping off the loop.
            is_shunt = rec.get("relation") == "source-shunt"
            if not done and (can_flip or is_shunt):
                z = zones[0]
                zf_sides = (True, False) if can_flip else (wb,)
                for side in zf_sides:
                    if fp.IsFlipped() != side:
                        fp.Flip(fp.GetPosition(), False)
                    step = 0.5  # finer than MIN_CENTER so spread placement's gaps are found
                    yy = z[1] + 1
                    while yy <= z[3] - 1 and not done:
                        xx = z[0] + 1
                        while xx <= z[2] - 1:
                            fp.SetPosition(pcbnew.VECTOR2I(int(xx*1e6), int(yy*1e6)))
                            bb = _body_bbox(fp)
                            if fits(bb, side, motor_ok=(r in motor_exempt)):
                                place_fp_at(fp, xx, yy, side)
                                _hf, _hb = _layers(fp); placed[r] = (_body_bbox(fp), _hf, _hb)
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


# NOTE \b fails after a phase letter that is followed by "_" (e.g. GHA_CH1), since
# "_" is a word char so there is no A|_ boundary — use (?:_|\b) like the first
# alternative, else gate-drive Rs (GHx/GLx/BSTx) never phase-tag and scatter into
# rest_role, crowding the per-phase FET cell.
_PHASE_NET_RE = re.compile(r'(?:MOTOR_|SHUNT_|BEMF_|CSA_)([ABC])(?:_|\b)|(?:GH|GL|BST)([ABC])(?:_|\b)')


def _phase_of(fp):
    """The half-bridge phase (A/B/C) a footprint belongs to, from its pad nets."""
    ph = set()
    for pad in fp.Pads():
        m = _PHASE_NET_RE.search(pad.GetNetname() or "")
        if m:
            ph.add(m.group(1) or m.group(2))
    return next(iter(ph)) if len(ph) == 1 else None


def _strip_phase(n):
    n = re.sub(r'(MOTOR_|SHUNT_|BEMF_|CSA_)[ABC]', r'\1X', n)
    return re.sub(r'(GH|GL|BST)[ABC]', r'\1X', n)


def _phase_sig(fp, role):
    """Phase-invariant signature: role + named nets with the phase letter masked.
    A's HS-FET and B's HS-FET share this signature; counterparts map by it."""
    nets = []
    for pad in fp.Pads():
        n = pad.GetNetname() or ""
        if not n or n.startswith(("N$", "Net-", "unconnected")):
            continue
        nets.append(_strip_phase(n))
    return (role, tuple(sorted(set(nets))))


def _channel_motor_pads(board, present, cn):
    """{phase: (x_mm, y_mm)} for this channel's 3 motor terminal pads."""
    import re as _re
    mp = {}
    for r in MOTOR_TP_REFS:
        fp = present.get(r)
        if fp is None:
            continue
        for pad in fp.Pads():
            m = _re.match(rf"MOTOR_([ABC])_CH{cn}$", pad.GetNetname() or "")
            if m:
                p = fp.GetPosition()
                mp[m.group(1)] = (p.x / 1e6, p.y / 1e6)
                break
    return mp


def replicate_phases(board, refs, roles, subsystem, zones):
    """R20 / symmetry-preserves-work: a channel's 3 half-bridge phases must be
    IDENTICAL geometric copies. Place all phases via the role engine, then snap
    every phase onto ONE reference phase's geometry translated by the motor-pad
    pitch (so FET rows land at the lockfile 12mm pitch and the channel is a clean
    mirror template). The reference is chosen so the translated copies all stay
    in-zone — e.g. for a zone whose top edge crowds the last motor pad, the top
    phase is the reference and the others translate inward. Returns issues."""
    import re as _re
    chan = _re.search(r'\d+', subsystem)
    if not chan:
        return []
    cn = chan.group()
    present = {fp.GetReference(): fp for fp in board.GetFootprints()}
    mpads = {}
    for r in MOTOR_TP_REFS:
        fp = present.get(r)
        if not fp:
            continue
        for pad in fp.Pads():
            m = _re.match(rf'MOTOR_([ABC])_CH{cn}$', pad.GetNetname() or "")
            if m:
                p = fp.GetPosition()
                mpads[m.group(1)] = (p.x / 1e6, p.y / 1e6)
                break
    if set(mpads) != {"A", "B", "C"}:
        return [f"replicate_phases: {subsystem} motor pads incomplete: {sorted(mpads)}"]
    # Group placeable phase components by phase, keyed by phase-invariant signature.
    # West FET strip only (master 2026-05-26 sub-zone split): replicate the
    # switching cell (FET/shunt/gate-R/clamp/VMOTOR-bypass). The east control
    # strip (MCU/DRV/INA/decoupling) is placed separately by their zone_hints, so
    # exclude cluster-anchors (MCU/DRV/INA/U3/U4) and the INA from replication.
    by_phase = {"A": {}, "B": {}, "C": {}}
    for r in refs:
        fp = present.get(r)
        if fp is None or r in MOTOR_TP_REFS:
            continue
        rec = roles.get(r, {})
        if rec.get("role") == "cluster-anchor" or rec.get("relation") == "ina-near-shunt":
            continue
        ph = _phase_of(fp)
        if ph in by_phase:
            by_phase[ph].setdefault(_phase_sig(fp, rec.get("role")), []).append(r)

    # West FET strip only: cap x at the sub-zone split (master 2026-05-26) so the
    # replicated phases stay clear of the east control strip (MCU/DRV/INA).
    FET_STRIP_X1 = 22.0
    _z0 = zones[0]
    z = (_z0[0], _z0[1], min(_z0[2], FET_STRIP_X1), _z0[3])

    def _safe_subzone(ref_ph):
        # A reference-phase CENTER placed in this box stays in-zone for ALL phases
        # (= intersection of zone − phase_offset over A/B/C). Empty ⇒ zone too small.
        dxs = [mpads[p][0] - mpads[ref_ph][0] for p in ("A", "B", "C")]
        dys = [mpads[p][1] - mpads[ref_ph][1] for p in ("A", "B", "C")]
        return (z[0] - min(dxs), z[1] - min(dys), z[2] - max(dxs), z[3] - max(dys))

    def _clamp_plan(ref_ph):
        """Map ref_ph components to all phases, clamping the reference CENTER into
        the safe sub-zone first. Returns (moves, distortion) or None on mismatch."""
        sx0, sy0, sx1, sy1 = _safe_subzone(ref_ph)
        if sx0 > sx1 or sy0 > sy1:
            return None, None  # safe sub-zone empty → zone genuinely too tight
        moves, dist = [], 0.0
        for sig, ref_refs in by_phase[ref_ph].items():
            ref_refs = sorted(ref_refs, key=_ref_sort_key)
            groups = {}
            for ph in ("A", "B", "C"):
                groups[ph] = sorted(by_phase[ph].get(sig, []), key=_ref_sort_key)
                if len(groups[ph]) != len(ref_refs):
                    return None, None
            for i, rr in enumerate(ref_refs):
                rp = present[rr].GetPosition()
                cx = min(max(rp.x / 1e6, sx0), sx1)
                cy = min(max(rp.y / 1e6, sy0), sy1)
                dist += abs(cx - rp.x / 1e6) + abs(cy - rp.y / 1e6)
                for ph in ("A", "B", "C"):
                    tgt = present[groups[ph][i]]
                    moves.append((tgt, present[rr],
                                  cx + mpads[ph][0] - mpads[ref_ph][0],
                                  cy + mpads[ph][1] - mpads[ref_ph][1]))
        return moves, dist

    # Pick the reference phase needing the least clamp distortion (best-preserved
    # role-engine geometry) among those whose safe sub-zone is non-empty.
    best, best_dist, best_ph = None, None, None
    for ref_ph in ("A", "B", "C"):
        moves, dist = _clamp_plan(ref_ph)
        if moves is None:
            continue
        if best is None or dist < best_dist:
            best, best_dist, best_ph = moves, dist, ref_ph
    if best is None:
        return [f"replicate_phases: {subsystem} no valid reference "
                f"(zone too tight for 3 phases, or signature groups mismatch)"]
    for tgt, ref, x, y in best:
        if tgt.IsFlipped() != ref.IsFlipped():
            tgt.Flip(tgt.GetPosition(), False)
        tgt.SetOrientation(ref.GetOrientation())
        tgt.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        reset_text_to_body(tgt)
    return []


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
    rmap = {r: roles[r] for r in role_placed}
    did_phase = False
    if role_placed and subsystem.startswith("CH") and PHASE_REPLICATE:
        # R20 west/east split (master 2026-05-26): place the WEST switching cell of
        # ONE reference phase (A) in the replication-safe sub-zone via the role
        # engine, DON'T place phases B/C's west components, then replicate A's
        # geometry onto them (motor-pad-pitch translation). This keeps each phase a
        # clean collision-free copy — the earlier place-all-then-clamp stacked the
        # cluster into the narrow safe band. East control (MCU/DRV/INA) places
        # normally via its zone_hints.
        mp = _channel_motor_pads(board, present, re.search(r"\d+", subsystem).group())
        if set(mp) == {"A", "B", "C"}:
            def _wphase(r):
                rec = rmap.get(r, {})
                if rec.get("role") == "cluster-anchor" or rec.get("relation") in (
                        "ina-near-shunt", "motor-clamp", "sense-clamp"):
                    return None  # placed with the east cluster, not the west phase cell
                fp = present.get(r)
                return _phase_of(fp) if fp else None
            pa = [r for r in role_placed if _wphase(r) == "A"]
            pbc = [r for r in role_placed if _wphase(r) in ("B", "C")]
            rest_role = [r for r in role_placed if r not in pa and r not in pbc]
            if pa and pbc:
                z = zones[0]
                yspan = max(p[1] for p in mp.values()) - min(p[1] for p in mp.values())
                # Cap the reference band 2mm short of the full phase pitch so the
                # 3 replicated clusters leave an inter-phase GAP (else adjacent
                # clusters abut at the 12mm seam → cross-phase body overlaps).
                sub = (z[0], z[1], min(z[2], 22.0), z[3] - yspan - 0.0)
                # EAST control (MCU/DRV/INA + decoupling) first, so phase-A's west
                # cluster — and therefore its replicated B/C copies — avoid them.
                # (Otherwise the HS-FET offsets toward the empty east band and the
                # replicated FET lands on the driver.)
                errs += role_place(board, rest_role, zones, {r: rmap[r] for r in rest_role})
                # Phantom keep-outs: EVERY on-board obstacle that is NOT one of the
                # phase parts being placed/replicated (foundation + the already-
                # placed east control J19/J18/INA + S6 + other channels), BODY-bbox,
                # translated BACK by the B/C phase offsets — so the reference phase A
                # avoids any spot whose replicated B/C copy would land on it (e.g. a
                # phase-B gate-R copy hitting the driver J19). Motor pads excluded
                # (FETs belong beside them). No x-filter: a phantom only rejects a
                # candidate if it actually falls in the sub-zone.
                ch1_role = set(role_placed)
                offs = [(mp[p][0] - mp["A"][0], mp[p][1] - mp["A"][1]) for p in ("B", "C")]
                # Targeted: foundation in the FET-strip x-band + the shared east
                # anchors (driver/MCU, whose bodies reach the strip) — NOT every
                # board obstacle (that over-constrains the reference cluster).
                drv_mcu = {x for x in role_placed
                           if roles[x].get("relation") in ("gate-driver",)
                           or (roles[x].get("role") == "cluster-anchor" and x not in pa and x not in pbc)}
                phantoms = []
                for fp in board.GetFootprints():
                    r = fp.GetReference()
                    if fp.GetPosition().x / 1e6 >= 130:
                        continue
                    is_found = r not in ch1_role and r not in MOTOR_TP_REFS
                    if not (is_found or r in drv_mcu):
                        continue
                    bb = _body_bbox(fp)
                    for dx, dy in offs:
                        phantoms.append((bb[0] - dx, bb[1] - dy, bb[2] - dx, bb[3] - dy))
                errs += role_place(board, pa, [sub], {r: rmap[r] for r in pa},
                                   extra_keepouts=phantoms if PHASE_LOOKAHEAD else [])
                errs += replicate_phases(board, pa + pbc,
                                         {r: rmap[r] for r in pa + pbc}, subsystem, zones)
                did_phase = True
    if role_placed and not did_phase:
        errs += role_place(board, role_placed, zones, rmap)
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
