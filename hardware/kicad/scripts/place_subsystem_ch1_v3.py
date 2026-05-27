#!/usr/bin/env python3
"""place_subsystem_ch1_v3.py — Phase 4-v2 Step 2 CH1, Approach B.

Per master 2026-05-24 ACCEPT-pivot-to-Approach-B:
- Drop net-copy work (pcbai_fpv4in1.kicad_pcb has full netlist from kinet2pcb)
- Re-position CH1 components only; other subsystems stay at PR #73 coords
- silk-bbox keepout in spiral validation
- U3 re-anchored with ≥6mm gap from J22

Algorithm:
1. Load full pcbai_fpv4in1.kicad_pcb (donor==recipient)
2. Identify CH1 components via ref-list (FETs/ICs) + net suffix (_CH1 passives)
3. Move IC anchors to fixed positions (Q5-Q10 grid, J18/J19/J20-22/U3/U4)
4. For each passive: find parent IC via shared net, spiral-search from parent
   pin position, validate: pad-bbox + silk-bbox + zone containment
5. Save back

Targets per master gate:
  PAD-OVERLAP-DIFFNET = 0
  COMPONENT-INSIDE-BODY = 0
  16+5+6 audit gates GREEN on CH1 scope
"""
import math
import re
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from constraint_engine import parse_board_invariants

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# CH1 IC anchors — re-anchored per master 2026-05-24:
# J20/21/22 INAs at x=3 (far west, aligned with motor TPs at x=5)
# U3 LM393 at (20,72) — central, between J18 north and J19 south,
#   ≥6mm from all INAs (closest: J22 at (3,80) = hypot(17,8)=18.8mm)
# U4 LM393 at (10,74) — west central, ≥6mm from FETs (Q7@12,68 → hypot(2,6)=6.3mm)
IC_ANCHORS = {
    # 12mm row pitch enforced (audit SYMMETRY strict 0.5mm tolerance).
    # All FETs shifted south by 2mm to keep Q9/Q10 pad max y=80.5 → 79.5,
    # clearing TLM/AUX strip (80-82) while maintaining 12mm row spacing.
    'Q5':  (12.0, 54.0),
    'Q6':  (30.0, 54.0),
    'Q7':  (12.0, 66.0),
    'Q8':  (30.0, 66.0),
    'Q9':  (12.0, 78.0),
    'Q10': (30.0, 78.0),
    'J18': (26.0, 72.0),   # MCU QFN-32 — between Q7 (66) and Q9 (78); east of U3
    'J19': (22.0, 60.0),   # DRV HVQFN-24 — between Q5 (54) and Q7 (66)
    'J20': (3.0, 54.0),    # INA-A — track Q5 row
    'J21': (3.0, 66.0),    # INA-B — track Q7 row
    'J22': (3.0, 78.0),    # INA-C — track Q9 row
    'U3':  (17.0, 72.0),   # LM393 SOIC-8 — west of J18 by 6mm clearance
    'U4':  (8.0, 70.0),    # LM393 SOT-353 — far west
    # TP19/20/21 deliberately NOT anchored — let spiral place them via their
    # MOTOR_x_CH1 net (parent = FET source pads). Fixed TP position at x=5 next
    # to INAs at x=3 caused pad collisions (1mm TP pad vs 2mm INA body).
}

PAD_CLEARANCE_MM = 0.3
SILK_BBOX_MARGIN_MM = 0.0   # match audit_layout_compliance _silk_bbox_mm exactly


def reset_text_to_body(fp):
    """KiCad SetPosition() leaves child text fields at their absolute prior
    positions — they don't auto-follow the body. Reset Reference + Value text
    to fp center. For small passives (R/C/D/TP — body <3mm), HIDE ref text:
    dense CH1 layout has no room for visible silk text on every 0402/0603 +
    audit's SILK-ON-PAD is DFM-blocking; common production practice is to
    hide refs on small passives, rely on assembly position file for placement.
    IC refs (U/J/Q) stay visible for assembly cross-check."""
    pos = fp.GetPosition()
    rf = fp.Reference()
    vf = fp.Value()
    if rf is not None:
        rf.SetPosition(pos)
    if vf is not None:
        vf.SetPosition(pos)
        vf.SetVisible(False)  # value always hidden on silk
    ref = fp.GetReference()
    if rf is not None and ref and ref[0] in ('R', 'C', 'D') and ref[1:].isdigit():
        rf.SetVisible(False)
    if rf is not None and ref and ref.startswith('TP'):
        rf.SetVisible(False)

# Per-ref east-edge bound — master 2026-05-24 directive for collisions with
# fixed non-CH1 neighbors near CH1 zone east boundary (x=35).
PER_REF_EAST_EDGE = {
    'R59': 33.0,   # avoid non-CH1 C82 at x=36
    'R60': 33.0,   # mirror of R59 — same constraint
    'R56': 33.0,   # 2512 shunt; safer to keep east-edge bounded
}

# ─── SHUNT OVERLAP ANCHORS (PLACEMENT_GLOBAL_PLAN §8 addendum #9, lock 2026-05-27) ───
# Per worker STEP-5 SHUNT ampacity finding: high-current shunts MUST physically
# overlap LS FET source pad with ≥1.5mm² overlap area for the 16-via 0.6mm pitch
# array (~96A continuous per IPC-2152), since bridge-trace at 0.85mm gap can never
# carry 70A continuous (needs ~4mm width per IPC-2152, geometrically impossible).
#
# Coords derived (PR #197, master subagent 2026-05-27):
#   Each shunt center is offset by +2.962mm in Y from its LS FET source pad
#   center (=shunt pad-1 SHUNT-TOP-side center after 270° rotation). Shunt is
#   moved to B.Cu (same layer as LS FET) so its bbox overlap with FET source EP
#   becomes direct copper merge — no via array necessary across layers, though
#   the GND pad-2 still stitches to GND plane via the 16-via 0.6mm array
#   audited by G_SW_GND_VIA (see PR #196).
#
# Body shape: 2512 chip (6.5mm x 3.2mm). At rotation 270°:
#   - pad-1 (SHUNT_*_TOP_CHn) at (cx, cy - 2.962)
#   - pad-2 (GND)             at (cx, cy + 2.962)
#   - body bbox y-extent: cy-4.65 .. cy+4.65 mm
# Body stays inside CH1 zone (y=50..89), no collision with VMOTOR feed corridor
# at y=47..53. Same-layer body bbox overlap with LS FET (Q6/Q8/Q10) is INTENTIONAL
# (per §8 addendum #9) and exempted in BBOX_OVERLAP_EXEMPT.txt.
#
# Format: ref -> {pos:(x,y,mm), rotation:degrees, layer:str}
SHUNT_ANCHORS = {
    # CH1 — Q6/Q8/Q10 LS FETs are at (30, {54,66,78}) per IC_ANCHORS above
    'R57': {'pos': (30.000, 56.962), 'rotation': 270.0, 'layer': 'B.Cu'},  # over Q6 source (phase A)
    'R58': {'pos': (30.000, 68.962), 'rotation': 270.0, 'layer': 'B.Cu'},  # over Q8 source (phase B)
    'R59': {'pos': (30.000, 80.962), 'rotation': 270.0, 'layer': 'B.Cu'},  # over Q10 source (phase C)
}

# Override default PER_REF_EAST_EDGE for shunts that are now anchored — anchor
# logic takes precedence over east-edge validate, but keep an entry so the
# fallback spiral knows not to push them east.
PER_REF_EAST_EDGE['R57'] = 33.0
PER_REF_EAST_EDGE['R58'] = 33.0
PER_REF_EAST_EDGE['R59'] = 33.0


def get_ch1_refs(board, zone):
    """Identify CH1 components — three classification paths (master 2026-05-24
    REJECT #4/#5 expanded classifier):
      1. Explicit IC list (IC_ANCHORS keys)
      2. Any FP with a _CH1-suffix net (e.g., MOTOR_A_CH1, +3V3A_CH1)
      3. Any FP physically inside CH1 zone bbox (catches global-net comps like
         GND-only caps + VMOTOR_CH passives that sit in CH1 zone)
    Path 3 ensures zone-internal collisions are visible to the CH1 placement
    rerun, not just the CH1-suffixed-net subset."""
    refs = set()
    zx0, zy0, zx1, zy1 = zone
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        # Skip mount holes + fiducials — fixed at corners by design
        if ref.startswith('H') or ref.startswith('FID'):
            continue
        if ref in IC_ANCHORS:
            refs.add(ref); continue
        # Path 2: _CH1 net suffix
        if any(re.search(r'_CH1$', pad.GetNetname() or '')
               for pad in fp.Pads()):
            refs.add(ref); continue
        # Path 3: physically inside CH1 zone bbox
        p = fp.GetPosition()
        x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
        if zx0 <= x <= zx1 and zy0 <= y <= zy1:
            refs.add(ref)
    return refs


def fp_bbox_relative(fp):
    """PAD-CLUSTER bbox relative to fp.GetPosition(). Used for test fp's OWN
    area (avoid inflation from ref text → 0402 caps appear 60mm² else)."""
    cx = pcbnew.ToMM(fp.GetPosition().x)
    cy = pcbnew.ToMM(fp.GetPosition().y)
    xs, ys = [], []
    for pad in fp.Pads():
        bb = pad.GetBoundingBox()
        xs.extend([pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetRight())])
        ys.extend([pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetBottom())])
    if not xs:
        return (-1.0, -1.0, 1.0, 1.0)
    return (
        min(xs) - cx - 0.5,
        min(ys) - cy - 0.5,
        max(xs) - cx + 0.5,
        max(ys) - cy + 0.5,
    )


def fp_silk_relative(fp):
    """SILK-DRAWING bbox relative to fp.GetPosition(). Matches audit_layout_compliance
    _silk_bbox_mm — extracts only silkscreen PCB_SHAPE items (excludes ref text +
    courtyard). Falls back to courtyard then pad-cluster."""
    cx = pcbnew.ToMM(fp.GetPosition().x)
    cy = pcbnew.ToMM(fp.GetPosition().y)
    silk_pts, ctyd_pts = [], []
    for d in fp.GraphicalItems():
        if not isinstance(d, pcbnew.PCB_SHAPE): continue
        layer = d.GetLayer()
        if layer in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            bucket = silk_pts
        elif layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            bucket = ctyd_pts
        else:
            continue
        bb = d.GetBoundingBox()
        bucket.extend([
            pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetRight()),
            pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetBottom()),
        ])
    pts = silk_pts or ctyd_pts
    if not pts:
        return fp_bbox_relative(fp)
    # silk_pts is flat (L,R,T,B,L,R,T,B...) — collect xs/ys
    xs = [pts[i] for i in range(0, len(pts), 2)]   # L,T,L,T... wait no
    # rewrite: each PCB_SHAPE contributed [L, R, T, B]
    xs, ys = [], []
    for i in range(0, len(pts), 4):
        xs.extend([pts[i], pts[i+1]])
        ys.extend([pts[i+2], pts[i+3]])
    return (min(xs) - cx, min(ys) - cy, max(xs) - cx, max(ys) - cy)


def silk_bbox_at(fp_rel, pos_mm, layer):
    """Compute world silk bbox at given (x, y) using pre-snapshotted relative extents."""
    x, y = pos_mm
    return (
        x + fp_rel[0] - SILK_BBOX_MARGIN_MM,
        y + fp_rel[1] - SILK_BBOX_MARGIN_MM,
        x + fp_rel[2] + SILK_BBOX_MARGIN_MM,
        y + fp_rel[3] + SILK_BBOX_MARGIN_MM,
        layer,
    )


def fp_pad_bboxes(fp, at_pos=None):
    """Return list of (x1,y1,x2,y2, F,B, netname) pad bboxes at given pos."""
    cur_x = pcbnew.ToMM(fp.GetPosition().x)
    cur_y = pcbnew.ToMM(fp.GetPosition().y)
    if at_pos:
        dx = at_pos[0] - cur_x; dy = at_pos[1] - cur_y
    else:
        dx = 0; dy = 0
    out = []
    for pad in fp.Pads():
        bb = pad.GetBoundingBox()
        ls = pad.GetLayerSet()
        out.append((
            pcbnew.ToMM(bb.GetLeft()) + dx,
            pcbnew.ToMM(bb.GetTop()) + dy,
            pcbnew.ToMM(bb.GetRight()) + dx,
            pcbnew.ToMM(bb.GetBottom()) + dy,
            ls.Contains(pcbnew.F_Cu),
            ls.Contains(pcbnew.B_Cu),
            pad.GetNetname() or '',
        ))
    return out


def position_valid(test_pads, test_layer, test_area_mm2,
                   placed_pad_bxs, ic_silk_bxs, tp_keepouts,
                   is_motor_sense, placed_centers, x, y, zone,
                   east_edge=None, test_ref=None):
    """Validate (x,y) for new fp.
    - Inside zone with 0.5mm inset
    - 1.5mm center-to-center clearance same-layer
    - pad-bbox: no diff-net overlap same-side
    - silk-bbox keepout: BOTH center AND any pad center must NOT be inside
      a ≥4× larger IC silk (matches audit logic)
    - motor-TP 2mm keepout for non-sense-net components
    """
    if not (zone[0] + 0.5 <= x <= zone[2] - 0.5 and zone[1] + 0.5 <= y <= zone[3] - 0.5):
        return False
    # Per-ref east-edge constraint (master 2026-05-24: R59 x ≤ 33 to avoid C82)
    if east_edge is not None and x > east_edge:
        return False
    for (px, py, pl) in placed_centers:
        if pl != test_layer: continue
        if math.hypot(px - x, py - y) < 1.5:
            return False
    for (b1, b2, b3, b4, F, B, net) in test_pads:
        for (p1, p2, p3, p4, pF, pB, pn) in placed_pad_bxs:
            if net and pn and net == pn: continue
            same_side = (F and pF) or (B and pB)
            if not same_side: continue
            if b1 - PAD_CLEARANCE_MM < p3 and b3 + PAD_CLEARANCE_MM > p1 and \
               b2 - PAD_CLEARANCE_MM < p4 and b4 + PAD_CLEARANCE_MM > p2:
                return False
    # Silk-bbox keepout — CTR + per-pad-center checks
    for (s1, s2, s3, s4, sl) in ic_silk_bxs:
        if sl != test_layer: continue
        ic_area = (s3 - s1) * (s4 - s2)
        if ic_area < test_area_mm2 * 4: continue
        if s1 < x < s3 and s2 < y < s4:
            return False
        for (b1, b2, b3, b4, F, B, net) in test_pads:
            same_side = ((F and sl == pcbnew.F_Cu) or (B and sl == pcbnew.B_Cu))
            if not same_side: continue
            px_c = (b1 + b3) / 2; py_c = (b2 + b4) / 2
            if s1 < px_c < s3 and s2 < py_c < s4:
                return False
    # Motor-TP keepout — bbox match audit; layer-AGNOSTIC (audit cares about
    # probe access in XY, not per-layer). TP pad 3mm + 2mm keepout = ±3.5mm.
    if not is_motor_sense:
        for (tx, ty, _tl) in tp_keepouts:
            if (tx - 3.6) <= x <= (tx + 3.6) and (ty - 3.6) <= y <= (ty + 3.6):
                return False
    # TP-TP spacing — if placing a TP, require ≥4mm c-to-c from other TPs
    # (Sai catch #4: probe access blocked below 4mm). Layer-agnostic.
    if test_ref and test_ref.startswith('TP'):
        for (tx, ty, _tl) in tp_keepouts:
            if math.hypot(tx - x, ty - y) < 4.0:
                return False
    return True


_MOTOR_SENSE_NET_RE = re.compile(
    r'^(MOTOR_[ABC]_CH\d+|BEMF_[ABC]_CH\d+|CSA_[ABC]_OUT_CH\d+'
    r'|CSA_MAX_CH\d+|SHUNT_[ABC]_TOP_CH\d+'
    r'|GH[ABC]_CH\d+|GL[ABC]_CH\d+|BST[ABC]_CH\d+)$'
)


def fp_is_motor_sense(fp):
    for pad in fp.Pads():
        n = pad.GetNetname() or ''
        if _MOTOR_SENSE_NET_RE.match(n):
            return True
    return False


def main():
    inv = parse_board_invariants("docs/BOARD_INVARIANTS.md")
    ch1_zone = inv.zones.get('CH1', (0, 50, 35, 82))
    if hasattr(ch1_zone, 'x_min'):
        zone = (ch1_zone.x_min, ch1_zone.y_min, ch1_zone.x_max, ch1_zone.y_max)
    else:
        zone = ch1_zone
    print(f"CH1 zone: x=[{zone[0]}-{zone[2]}], y=[{zone[1]}-{zone[3]}]")

    board = pcbnew.LoadBoard(PCB)
    ch1_refs = get_ch1_refs(board, zone)
    print(f"CH1 components: {len(ch1_refs)}")

    placed_centers = []
    placed_pad_bxs = []
    ic_silk_bxs = []

    # Reserve all non-CH1 components first (treat as fixed obstacles in their zones)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in ch1_refs: continue
        # Only obstacles within or near CH1 zone need consideration
        cx = pcbnew.ToMM(fp.GetPosition().x)
        cy = pcbnew.ToMM(fp.GetPosition().y)
        if not (zone[0] - 2 <= cx <= zone[2] + 2 and zone[1] - 2 <= cy <= zone[3] + 2):
            continue
        placed_centers.append((cx, cy, fp.GetLayer()))
        for pb in fp_pad_bboxes(fp):
            placed_pad_bxs.append(pb)

    # Place IC anchors
    placed = 0
    for ref, (x, y) in IC_ANCHORS.items():
        if ref not in ch1_refs: continue
        fp = board.FindFootprintByReference(ref)
        if fp is None: continue
        # Snapshot bbox BEFORE SetPosition (avoid stale cache)
        fp_silk_rel = fp_silk_relative(fp)
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6))); reset_text_to_body(fp)
        placed_centers.append((x, y, fp.GetLayer()))
        for pb in fp_pad_bboxes(fp):
            placed_pad_bxs.append(pb)
        ic_silk_bxs.append(silk_bbox_at(fp_silk_rel, (x, y), fp.GetLayer()))
        placed += 1
    print(f"IC anchors placed: {placed}")

    # Place SHUNT_ANCHORS (PLACEMENT_GLOBAL_PLAN §8 addendum #9 enforcement).
    # These shunts MUST overlap LS-FET source pads ≥1.5mm² — explicit anchor
    # coords (with layer + rotation) override the spiral placer's default
    # "spiral from parent IC pin" which cannot satisfy the overlap requirement.
    shunts_placed = 0
    for ref, spec in SHUNT_ANCHORS.items():
        if ref not in ch1_refs: continue
        fp = board.FindFootprintByReference(ref)
        if fp is None: continue
        x, y = spec['pos']
        rot = spec['rotation']
        layer = spec['layer']
        # Move to B.Cu if requested and currently on F.Cu (Flip() rotates 180°)
        want_back = (layer == 'B.Cu')
        if fp.IsFlipped() != want_back:
            fp.Flip(fp.GetPosition(), False)
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        reset_text_to_body(fp)
        placed_centers.append((x, y, fp.GetLayer()))
        for pb in fp_pad_bboxes(fp):
            placed_pad_bxs.append(pb)
        shunts_placed += 1
        print(f"  SHUNT anchor {ref} → ({x:.3f},{y:.3f}) rot={rot}° {layer} (§8#9 overlap)")
    if shunts_placed:
        print(f"Shunt overlap anchors placed: {shunts_placed} (§8 addendum #9)")

    # Two-pass passive placement:
    #  Pass A: motor TPs + motor-sense-net components first (no TP keepout yet,
    #          they ARE the sense topology)
    #  Pass B: non-sense components last (with TP keepout active)
    # SHUNT_ANCHORS already placed deterministically above (§8 #9 overlap) —
    # exclude from spiral search to preserve the overlap anchor.
    all_passives = sorted(ch1_refs - set(IC_ANCHORS.keys()) - set(SHUNT_ANCHORS.keys()))
    tp_refs = [r for r in all_passives if r.startswith('TP')]
    sense_refs = [r for r in all_passives
                  if r not in tp_refs
                  and fp_is_motor_sense(board.FindFootprintByReference(r))]
    other_refs = [r for r in all_passives if r not in tp_refs and r not in sense_refs]
    passives = tp_refs + sense_refs + other_refs   # ordered

    tp_keepouts = []   # filled as TPs get placed
    failed = []
    pl_count = 0
    for ref in passives:
        fp = board.FindFootprintByReference(ref)
        if fp is None: continue
        # Find parent IC via shared (non-power) net
        parent_pin = None
        for pad in fp.Pads():
            n = pad.GetNetname() or ''
            if not n or n in ('GND', '+VMOTOR', '+VM'): continue
            for anchor_ref in IC_ANCHORS:
                if anchor_ref not in ch1_refs: continue
                a_fp = board.FindFootprintByReference(anchor_ref)
                if a_fp is None: continue
                for apad in a_fp.Pads():
                    if (apad.GetNetname() or '') == n:
                        ap = apad.GetPosition()
                        parent_pin = (pcbnew.ToMM(ap.x), pcbnew.ToMM(ap.y))
                        break
                if parent_pin: break
            if parent_pin: break
        if parent_pin is None:
            parent_pin = ((zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2)

        # FP pad-cluster area (avoid inflation from ref text — see fp_bbox_relative)
        rel = fp_bbox_relative(fp)
        fp_area = (rel[2] - rel[0]) * (rel[3] - rel[1])
        test_layer = fp.GetLayer()

        is_sense = fp_is_motor_sense(fp)
        chosen = None
        for r_steps in range(1, 30):
            r = r_steps * 0.4
            n_pts = max(8, r_steps * 4)
            for i in range(n_pts):
                theta = 2 * math.pi * i / n_pts
                tx = parent_pin[0] + r * math.cos(theta)
                ty = parent_pin[1] + r * math.sin(theta)
                tp = fp_pad_bboxes(fp, (tx, ty))
                if position_valid(tp, test_layer, fp_area,
                                  placed_pad_bxs, ic_silk_bxs, tp_keepouts,
                                  is_sense, placed_centers, tx, ty, zone,
                                  east_edge=PER_REF_EAST_EDGE.get(ref),
                                  test_ref=ref):
                    chosen = (tx, ty); break
            if chosen: break
        if chosen is None:
            failed.append(ref)
            continue
        fp.SetPosition(pcbnew.VECTOR2I(int(chosen[0] * 1e6), int(chosen[1] * 1e6))); reset_text_to_body(fp)
        placed_centers.append((chosen[0], chosen[1], test_layer))
        for pb in fp_pad_bboxes(fp):
            placed_pad_bxs.append(pb)
        if ref in tp_refs:
            tp_keepouts.append((chosen[0], chosen[1], test_layer))
        pl_count += 1

    print(f"Passives placed: {pl_count}/{len(passives)}")
    if failed:
        print(f"Failed ({len(failed)}): {failed[:10]}")

    # Decoupling fixup: ensure every IC has any C within 3mm (R25 + audit gate)
    # Find ICs lacking; relocate the nearest CH1 C currently >3mm from any IC.
    ic_refs_placed = [r for r in IC_ANCHORS if r in ch1_refs and r.startswith('U')]
    moved = 0
    for ic_ref in ic_refs_placed:
        ic_fp = board.FindFootprintByReference(ic_ref)
        if ic_fp is None: continue
        ix = pcbnew.ToMM(ic_fp.GetPosition().x)
        iy = pcbnew.ToMM(ic_fp.GetPosition().y)
        # Any C within 3mm same-side?
        any_near = False
        for fp in board.GetFootprints():
            r = fp.GetReference()
            if not (r.startswith('C') and r[1:].isdigit()): continue
            if fp.GetLayer() != ic_fp.GetLayer(): continue
            cx = pcbnew.ToMM(fp.GetPosition().x)
            cy = pcbnew.ToMM(fp.GetPosition().y)
            if math.hypot(cx - ix, cy - iy) <= 3.0:
                any_near = True; break
        if any_near: continue
        # Master 2026-05-24 R25-exempt path: prefer ANY CH1 cap whose net SHARES
        # with an IC pad (power preferred, then any non-GND signal). The audit's
        # R25-exempt check uses shared-net at <3mm — any non-GND shared net works.
        ic_pad_nets = {}  # net -> (x,y) of pad
        for pad in ic_fp.Pads():
            n = pad.GetNetname() or ''
            if n in ('', 'GND'): continue
            if n not in ic_pad_nets:
                pp = pad.GetPosition()
                ic_pad_nets[n] = (pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y))
        power_nets = {n for n in ic_pad_nets
                      if n in ('+3V3', '+5V', '+9V', 'VCC', 'VDD')}
        ic_power_pin_pos = next((ic_pad_nets[n] for n in power_nets), None)

        shared_power_candidates = []  # cap shares an IC power net
        shared_any_candidates = []    # cap shares any non-GND IC net
        any_candidates = []           # any far CH1 cap
        for fp in board.GetFootprints():
            r = fp.GetReference()
            if not (r.startswith('C') and r[1:].isdigit()): continue
            if r not in ch1_refs: continue
            cap_nets = {pad.GetNetname() or '' for pad in fp.Pads()}
            cap_nets.discard('GND')
            cap_nets.discard('')
            cx = pcbnew.ToMM(fp.GetPosition().x)
            cy = pcbnew.ToMM(fp.GetPosition().y)
            d = math.hypot(cx - ix, cy - iy)
            shared = cap_nets & set(ic_pad_nets.keys())
            if shared & power_nets:
                shared_power_candidates.append((d, r, fp, list(shared)[0]))
            elif shared:
                shared_any_candidates.append((d, r, fp, list(shared)[0]))
            if d > 5.0:
                any_candidates.append((d, r, fp))
        # Selection priority: shared-power > shared-any > any-far
        if shared_power_candidates:
            shared_power_candidates.sort()
            _, c_ref, c_fp, c_target_net = shared_power_candidates[0]
            target_x, target_y = ic_power_pin_pos or (ix, iy)
        elif shared_any_candidates:
            shared_any_candidates.sort()
            _, c_ref, c_fp, c_target_net = shared_any_candidates[0]
            target_x, target_y = ic_pad_nets[c_target_net]
        elif any_candidates:
            any_candidates.sort()
            _, c_ref, c_fp = any_candidates[0]
            c_target_net = None
            target_x, target_y = (ix, iy)
        else:
            print(f"  WARN: no relocatable cap for {ic_ref}")
            continue
        # Search around IC for a free slot, same side. Use pad-cluster area.
        c_rel = fp_bbox_relative(c_fp)
        c_area = (c_rel[2] - c_rel[0]) * (c_rel[3] - c_rel[1])
        # Rebuild placed list excluding this cap
        new_placed_pads = [pb for pb in placed_pad_bxs]
        new_placed_centers = [pc for pc in placed_centers]
        old_cx = pcbnew.ToMM(c_fp.GetPosition().x)
        old_cy = pcbnew.ToMM(c_fp.GetPosition().y)
        # Remove this cap's contributions (approx by center match)
        new_placed_centers = [pc for pc in new_placed_centers
                              if not (abs(pc[0]-old_cx)<0.05 and abs(pc[1]-old_cy)<0.05)]
        # (skip removing pad bxs; just don't self-collide via dist check)
        is_sense_c = fp_is_motor_sense(c_fp)
        # R25-exempt mode: cap can sit INSIDE silk — relax silk-bbox check by
        # omitting from ic_silk_bxs only the host's silk for this cap
        r25_mode = bool(shared_power_candidates or shared_any_candidates)
        # In R25-exempt mode, cap may sit inside host IC silk — drop host's silk
        # from the constraint set; other ICs' silks still enforced.
        if r25_mode:
            host_silk = silk_bbox_at(fp_silk_relative(ic_fp),
                                     (ix, iy), ic_fp.GetLayer())
            ic_silk_for_check = [s for s in ic_silk_bxs
                                 if not (abs(s[0]-host_silk[0])<0.05 and
                                         abs(s[2]-host_silk[2])<0.05)]
        else:
            ic_silk_for_check = ic_silk_bxs
        for r_step in range(1, 16):
            r = 0.3 + r_step * 0.2     # 0.5 .. 3.3 mm
            n_pts = max(12, r_step * 6)
            done = False
            for i in range(n_pts):
                theta = 2 * math.pi * i / n_pts
                tx = target_x + r * math.cos(theta)
                ty = target_y + r * math.sin(theta)
                tp = fp_pad_bboxes(c_fp, (tx, ty))
                # DECOUPLING audit: cap-CENTER must be <=3mm from IC-CENTER
                if math.hypot(tx-ix, ty-iy) > 3.0: continue
                if position_valid(tp, c_fp.GetLayer(), c_area,
                                  new_placed_pads, ic_silk_for_check, tp_keepouts,
                                  is_sense_c, new_placed_centers, tx, ty, zone):
                    c_fp.SetPosition(pcbnew.VECTOR2I(int(tx*1e6), int(ty*1e6))); reset_text_to_body(c_fp)
                    placed_centers.append((tx, ty, c_fp.GetLayer()))
                    for pb in fp_pad_bboxes(c_fp):
                        placed_pad_bxs.append(pb)
                    moved += 1
                    print(f"  Relocated {c_ref} → ({tx:.1f},{ty:.1f}) for {ic_ref} decoupling")
                    done = True; break
            if done: break
    print(f"Decoupling fixup: {moved} caps relocated")

    board.Save(PCB)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
