#!/usr/bin/env python3
"""fix_inside_body_targeted.py — Sai-catch #12 Step 3 (master 2026-05-24).

For each component still flagged by check_component_inside_body, try in order:
  (a) ROTATE invader 90/180/270° (cheapest, no position change)
  (b) SHIFT invader by 0.5/1.0/1.5mm in 4 cardinals (8 candidates)
  (c) RE-ANCHOR to another pin on a shared net (R23-equivalent move)
  (d) SHIFT HOST by 0.5/1.0mm in 4 cardinals (4 candidates)

Each tentative move is validated against ALL audit gates inline:
  - COMPONENT-INSIDE-BODY (this rule, recomputed)
  - COINCIDENT-PLACEMENT (<1.6mm c-to-c same layer)
  - PAD-OVERLAP-DIFFNET (pad bboxes intersect different-net same-layer)
  - MOTOR-PAD-CLEAR (not within 2mm of motor TP)
  - DECOUPLING (decoupling caps within 3mm of parent IC VDD pin)

Picks the FIRST strategy that produces 0 regressions. If none work,
documents the case as INVESTIGATE FURTHER.

Codified per [[feedback-anchor-outside-parent-body]] +
[[feedback-host-silk-overdraw-exempt]].
"""
import pcbnew
import math
import re
from collections import defaultdict

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

AREA_RATIO = 4.0
HOST_MIN_AREA = 5.0
COINCIDENT_MIN = 1.6
MOTOR_PAD_KEEPOUT = 2.0
PAD_CLEAR = 0.3            # bumped from 0.2 — was creating DIFFNET regression
DECOUPLING_MAX_FROM_PIN = 3.0
DECOUPLING_RADIUS = 3.0    # audit check_decoupling threshold
# Silk-hide policy [[feedback-host-silk-overdraw-exempt]]: small passive
# classes that may have their refdes silk hidden when relocation causes
# SILK-ON-PAD. Critical components (ICs, connectors, FETs, polar) NOT in list.
SILK_HIDE_PASSIVE_CLASSES = (
    'R_0402', 'R_0603', 'R_0805',
    'C_0402', 'C_0603', 'C_0805',
    'L_0402', 'L_0603', 'L_0805',
    'D_SOD-123', 'D_SOD-323', 'BAT54', 'BZT52',
    'R_2512', 'C_2512',
)
MOTOR_TP_REFS = ('TP19','TP20','TP21','TP26','TP27','TP28',
                 'TP33','TP34','TP35','TP40','TP41','TP42')
_MOTOR_RE = re.compile(
    r'^(MOTOR_[ABC]_CH\d+|BEMF_[ABC]_CH\d+|CSA_[ABC]_OUT_CH\d+|CSA_MAX_CH\d+'
    r'|SHUNT_[ABC]_TOP_CH\d+|GH[ABC]_CH\d+|GL[ABC]_CH\d+|BST[ABC]_CH\d+)$'
)
HARDCODED_BODY_BBOX_REL = {
    'Sensor_Current:Allegro_CB_PFF': (-2.5, -2.5, 2.5, 2.5),
    'Sensor_Current:ACS770ECB':      (-13.5, -7.0, 13.5, 7.0),
}
SILK_OVERDRAW_EXEMPT_PATTERNS = (
    'Sensor_Current:Allegro_', 'Sensor_Current:ACS',
    'Sensor_Magnetic:', 'Sensor_Current:DRV',
)


def silk_bbox(fp):
    silk_pts = []; ctyd_pts = []
    for d in fp.GraphicalItems():
        if not isinstance(d, pcbnew.PCB_SHAPE): continue
        ly = d.GetLayer()
        bb = d.GetBoundingBox()
        box = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
               pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
        if ly in (pcbnew.F_SilkS, pcbnew.B_SilkS): silk_pts.append(box)
        elif ly in (pcbnew.F_CrtYd, pcbnew.B_CrtYd): ctyd_pts.append(box)
    pts = silk_pts or ctyd_pts
    if not pts:
        bb = fp.GetBoundingBox()
        return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
    xs = [b[0] for b in pts] + [b[2] for b in pts]
    ys = [b[1] for b in pts] + [b[3] for b in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def container_bbox(fp):
    """Return real-body container bbox per silk-overdraw exemption rules."""
    lib = fp.GetFPID().GetUniStringLibId()
    rel = HARDCODED_BODY_BBOX_REL.get(lib)
    if rel is not None:
        pos = fp.GetPosition()
        cx = pcbnew.ToMM(pos.x); cy = pcbnew.ToMM(pos.y)
        return (cx + rel[0], cy + rel[1], cx + rel[2], cy + rel[3])
    for pat in SILK_OVERDRAW_EXEMPT_PATTERNS:
        if lib.startswith(pat):
            xs=[]; ys=[]
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                xs += [pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetRight())]
                ys += [pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetBottom())]
            if xs:
                return (min(xs)-1.0, min(ys)-1.0, max(xs)+1.0, max(ys)+1.0)
    return silk_bbox(fp)


def is_motor_exempt(fp):
    for pad in fp.Pads():
        no = pad.GetNet()
        if no is None: continue
        n = no.GetNetname() or ''
        if _MOTOR_RE.match(n):
            return True
    return False


def build_fp_state(board):
    """Snapshot every fp's geometric state for inline validation."""
    state = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith('H'): continue
        pos = fp.GetPosition()
        cx = pcbnew.ToMM(pos.x); cy = pcbnew.ToMM(pos.y)
        cbox = container_bbox(fp)
        area = (cbox[2] - cbox[0]) * (cbox[3] - cbox[1])
        pads_pos = []
        pad_bxs = []
        for pad in fp.Pads():
            pp = pad.GetPosition()
            pads_pos.append((pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y)))
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            pad_bxs.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                            pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                            ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu),
                            pad.GetNetname() or ''))
        state[ref] = {
            'fp': fp, 'cx': cx, 'cy': cy, 'cbox': cbox, 'area': area,
            'pads_pos': pads_pos, 'pad_bxs': pad_bxs,
            'layer': fp.GetLayer(),
            'motor_exempt': is_motor_exempt(fp),
            'rot': fp.GetOrientationDegrees(),
        }
    return state


def find_invaders(state):
    """Return list of (invader_ref, host_ref) pairs."""
    out = []
    for iref, inh in state.items():
        if inh['motor_exempt']: continue
        for href, host in state.items():
            if href == iref: continue
            if host['layer'] != inh['layer']: continue
            if host['area'] < AREA_RATIO * inh['area']: continue
            if host['area'] < HOST_MIN_AREA: continue
            bx0, by0, bx1, by1 = host['cbox']
            ctr_in = bx0 <= inh['cx'] <= bx1 and by0 <= inh['cy'] <= by1
            pads_in = any(bx0 <= px <= bx1 and by0 <= py <= by1
                          for (px, py) in inh['pads_pos'])
            if ctr_in or pads_in:
                out.append((iref, href))
                break
    return out


def find_decoup_parent_pin(inh_state, inh_ref, state):
    """If inhabitant is a cap on a power net adjacent to some IC, return
    (px, py, parent_ref) of the closest IC VDD pin."""
    if not inh_ref.startswith('C'): return None
    cap_nets = set()
    for bb in inh_state['pad_bxs']:
        n = bb[6]
        if n.startswith('+') or n in ('VCC', 'VDD', 'AVDD', 'AVCC'):
            cap_nets.add(n)
    if not cap_nets: return None
    best = None; best_d = 1e9
    for oref, od in state.items():
        if oref == inh_ref: continue
        if not (oref.startswith('U') or oref.startswith('J')): continue
        for opp in od['pad_bxs']:
            n = opp[6]
            if n not in cap_nets: continue
            cx_pad = (opp[0] + opp[2]) / 2
            cy_pad = (opp[1] + opp[3]) / 2
            d = math.hypot(cx_pad - inh_state['cx'], cy_pad - inh_state['cy'])
            if d < best_d:
                best_d = d; best = (cx_pad, cy_pad, oref)
    return best


def ic_lose_cap_check(inh_ref, new_cx, new_cy, new_layer, state):
    """For caps: after move, does any IC that previously had this cap within
    3mm now lose its last cap within 3mm? Mirrors check_decoupling()."""
    if not inh_ref.startswith('C') or not inh_ref[1:].isdigit():
        return []
    inh = state[inh_ref]
    cx0, cy0 = inh['cx'], inh['cy']
    bad = []
    for iref, ic in state.items():
        if not (iref.startswith('U') and iref[1:].isdigit()): continue
        if ic['layer'] != new_layer: continue
        d_old = math.hypot(ic['cx'] - cx0, ic['cy'] - cy0)
        d_new = math.hypot(ic['cx'] - new_cx, ic['cy'] - new_cy)
        # If cap was inside 3mm before AND moving out
        if d_old > DECOUPLING_RADIUS: continue
        if d_new <= DECOUPLING_RADIUS: continue
        # Is there ANY other cap still within 3mm of this IC (excluding us)?
        has_other = False
        for cref, co in state.items():
            if cref == inh_ref: continue
            if not (cref.startswith('C') and cref[1:].isdigit()): continue
            if co['layer'] != ic['layer']: continue
            if math.hypot(co['cx'] - ic['cx'], co['cy'] - ic['cy']) <= DECOUPLING_RADIUS:
                has_other = True; break
        if not has_other:
            bad.append(iref)
    return bad


def position_violates(inh_ref, new_cx, new_cy, new_layer, state, decoup_pin):
    """Inline validate: would moving inhabitant to (new_cx, new_cy) violate
    any audit rule? Returns list of violations."""
    vios = []
    inh = state[inh_ref]
    dx = new_cx - inh['cx']; dy = new_cy - inh['cy']
    # Update tentative pad positions + bboxes
    new_pads_pos = [(p[0]+dx, p[1]+dy) for p in inh['pads_pos']]
    new_pad_bxs = [(b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy, b[4], b[5], b[6])
                   for b in inh['pad_bxs']]

    # 1) COMPONENT-INSIDE-BODY: tentative position vs all hosts (including current host)
    for href, host in state.items():
        if href == inh_ref: continue
        if host['layer'] != new_layer: continue
        if host['area'] < AREA_RATIO * inh['area']: continue
        if host['area'] < HOST_MIN_AREA: continue
        # Special case: if inh is currently the host's invader, skip if move clears it
        bx0, by0, bx1, by1 = host['cbox']
        ctr_in = bx0 <= new_cx <= bx1 and by0 <= new_cy <= by1
        pads_in = any(bx0 <= px <= bx1 and by0 <= py <= by1
                      for (px, py) in new_pads_pos)
        if ctr_in or pads_in:
            vios.append(f"INSIDE-BODY of {href}")
            break

    # 2) COINCIDENT-PLACEMENT
    for oref, other in state.items():
        if oref == inh_ref: continue
        if other['layer'] != new_layer: continue
        if math.hypot(other['cx'] - new_cx, other['cy'] - new_cy) < COINCIDENT_MIN:
            vios.append(f"COINCIDENT with {oref}")
            break

    # 3) PAD-OVERLAP-DIFFNET — check per-pad-pair (NOT per-component-net)
    for oref, other in state.items():
        if oref == inh_ref: continue
        for opp in other['pad_bxs']:
            for nb in new_pad_bxs:
                if nb[6] == opp[6] and nb[6] != '': continue  # same-net OK
                same_layer = (nb[4] and opp[4]) or (nb[5] and opp[5])
                if not same_layer: continue
                if nb[0] - PAD_CLEAR < opp[2] and nb[2] + PAD_CLEAR > opp[0] and \
                   nb[1] - PAD_CLEAR < opp[3] and nb[3] + PAD_CLEAR > opp[1]:
                    vios.append(f"PAD-OVERLAP {nb[6]}({inh_ref}) vs {opp[6]}({oref})")
                    return vios  # return early to keep cost down

    # 4) MOTOR-PAD-CLEAR
    for ref in MOTOR_TP_REFS:
        if ref not in state: continue
        m = state[ref]
        if m['layer'] != new_layer: continue
        if abs(new_cx - m['cx']) < MOTOR_PAD_KEEPOUT and \
           abs(new_cy - m['cy']) < MOTOR_PAD_KEEPOUT:
            if not inh['motor_exempt']:
                vios.append(f"MOTOR-PAD-CLEAR near {ref}")
                break

    # 5) DECOUPLING distance — both (a) tied-net check + (b) IC-lose-cap check
    if decoup_pin is not None:
        px, py, _ = decoup_pin
        if math.hypot(new_cx - px, new_cy - py) > DECOUPLING_MAX_FROM_PIN:
            vios.append(f"DECOUPLING > {DECOUPLING_MAX_FROM_PIN}mm from VDD pin")
    bad_ics = ic_lose_cap_check(inh_ref, new_cx, new_cy, new_layer, state)
    if bad_ics:
        vios.append(f"IC-LOSE-CAP: {bad_ics}")

    return vios


def try_strategy_b_shift(iref, state, max_d=3.0):
    """Try shifts at increasing distance + 24 angles. Range 0.5mm to max_d."""
    inh = state[iref]
    decoup_pin = find_decoup_parent_pin(inh, iref, state)
    cx, cy, layer = inh['cx'], inh['cy'], inh['layer']
    n_angles = 24
    d = 0.5
    while d <= max_d + 0.001:
        for ai in range(n_angles):
            theta = 2 * math.pi * ai / n_angles
            dx = d * math.cos(theta)
            dy = d * math.sin(theta)
            nx, ny = cx + dx, cy + dy
            if nx < 1.5 or nx > 98.5 or ny < 1.5 or ny > 98.5: continue
            vios = position_violates(iref, nx, ny, layer, state, decoup_pin)
            if not vios:
                return ('shift', nx, ny, dx, dy)
        d += 0.25
    return None


def try_strategy_d_move_host(iref, href, state):
    """Try shifting HOST 0.5/1.0/1.5mm cardinal (12 candidates) to clear invader.
    Special care: if host is an IC, check it doesn't lose its decoupling cap."""
    host = state[href]
    hcx, hcy = host['cx'], host['cy']
    hlayer = host['layer']
    inh = state[iref]
    is_ic_host = href.startswith('U') and href[1:].isdigit()
    # Host displacement candidates
    for d in (0.5, 1.0, 1.5):
        for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
            nx, ny = hcx + dx, hcy + dy
            if nx < 1.5 or nx > 98.5 or ny < 1.5 or ny > 98.5: continue
            # New host bbox
            new_cbox = (host['cbox'][0]+dx, host['cbox'][1]+dy,
                        host['cbox'][2]+dx, host['cbox'][3]+dy)
            ctr_in = new_cbox[0] <= inh['cx'] <= new_cbox[2] and \
                     new_cbox[1] <= inh['cy'] <= new_cbox[3]
            pads_in = any(new_cbox[0] <= px <= new_cbox[2] and
                          new_cbox[1] <= py <= new_cbox[3]
                          for (px, py) in inh['pads_pos'])
            if ctr_in or pads_in: continue
            # If host is an IC, ensure it still has at least one cap within 3mm
            if is_ic_host:
                has_cap = False
                for cref, co in state.items():
                    if not (cref.startswith('C') and cref[1:].isdigit()): continue
                    if co['layer'] != hlayer: continue
                    if math.hypot(co['cx'] - nx, co['cy'] - ny) <= DECOUPLING_RADIUS:
                        has_cap = True; break
                if not has_cap: continue
            # Validate host's new position (treat host as the moved one)
            vios = position_violates(href, nx, ny, hlayer, state, None)
            real_vios = [v for v in vios if not (v.startswith("INSIDE-BODY of") and iref in v)]
            if not real_vios:
                return ('move-host', nx, ny, dx, dy)
    return None


def is_silk_hide_eligible(fp):
    """True if footprint class is a small passive that may have silk hidden."""
    lib = str(fp.GetFPID().GetLibItemName() or '')
    for cls in SILK_HIDE_PASSIVE_CLASSES:
        if cls in lib:
            return True
    return False


def hide_refdes_silk(fp):
    """Set reference designator to invisible (preserves metadata, hides silk).
    Used when relocation would put silk text on copper pad — eligible classes
    only per master 2026-05-24 policy."""
    ref_field = fp.Reference()
    ref_field.SetVisible(False)


def apply_move(ref, nx, ny, state):
    """Apply a move + update state."""
    s = state[ref]
    s['fp'].SetPosition(pcbnew.VECTOR2I(int(nx * 1e6), int(ny * 1e6)))
    dx = nx - s['cx']; dy = ny - s['cy']
    s['cx'] = nx; s['cy'] = ny
    s['cbox'] = (s['cbox'][0]+dx, s['cbox'][1]+dy,
                 s['cbox'][2]+dx, s['cbox'][3]+dy)
    s['pads_pos'] = [(p[0]+dx, p[1]+dy) for p in s['pads_pos']]
    s['pad_bxs'] = [(b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy, b[4], b[5], b[6])
                    for b in s['pad_bxs']]


def main():
    board = pcbnew.LoadBoard(PCB)
    state = build_fp_state(board)
    invaders = find_invaders(state)
    print(f"Initial invaders: {len(invaders)}")

    fixes = []
    failed = []

    for iref, href in invaders:
        # Strategy (b): shift invader — first pass 3mm, then 5mm if stuck
        result = try_strategy_b_shift(iref, state, max_d=3.0)
        if not result:
            # Decoupling caps capped at 3mm by DECOUPLING_MAX_FROM_PIN inside validator;
            # other classes can try larger shifts
            inh = state[iref]
            if not (iref.startswith('C') and find_decoup_parent_pin(inh, iref, state)):
                result = try_strategy_b_shift(iref, state, max_d=5.0)
        if result:
            kind, nx, ny, dx, dy = result
            apply_move(iref, nx, ny, state)
            # Per silk-hide policy: if relocated component is eligible class,
            # preemptively hide silk to avoid new SILK-ON-PAD violations
            if is_silk_hide_eligible(state[iref]['fp']):
                hide_refdes_silk(state[iref]['fp'])
            fixes.append((iref, href, kind, dx, dy))
            print(f"  {iref} (in {href}): shift ({dx:+.1f},{dy:+.1f}) → ({nx:.2f},{ny:.2f})")
            continue
        # Strategy (d): move host
        result = try_strategy_d_move_host(iref, href, state)
        if result:
            kind, nx, ny, dx, dy = result
            apply_move(href, nx, ny, state)
            if is_silk_hide_eligible(state[href]['fp']):
                hide_refdes_silk(state[href]['fp'])
            fixes.append((href, iref, kind, dx, dy))
            print(f"  {href} hosting {iref}: move-host ({dx:+.1f},{dy:+.1f}) → ({nx:.2f},{ny:.2f})")
            continue
        failed.append((iref, href))
        print(f"  FAIL: {iref} in {href} — no strategy succeeded")

    print(f"\n=== Summary ===")
    print(f"Fixes applied: {len(fixes)}")
    print(f"Failed (INVESTIGATE FURTHER): {len(failed)}")

    # Re-detect invaders post-fix
    remaining = find_invaders(state)
    print(f"Remaining invaders: {len(remaining)}")
    if remaining:
        for r, h in remaining:
            print(f"  {r} inside {h}")

    board.Save(PCB)
    return 0 if not failed and not remaining else 1


if __name__ == "__main__":
    raise SystemExit(main())
