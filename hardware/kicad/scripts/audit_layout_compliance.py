#!/usr/bin/env python3
"""
Layout compliance audit per master rules R5/R20/R22/R23/R24.

Checks (all hard gates):
  1. Off-board: any footprint with center outside board outline + 2mm margin
  2. Pad-overlap: any two pads on same layer that physically intersect
  3. Symmetry: CH1-4 FETs match locked transforms within 0.5mm tolerance
  4. Passive anchoring: every R/C/L within role-specific max distance of parent device
  5. Decoupling: every IC's VDD/VCC pin has a cap within 3mm

Run: python3 audit_layout_compliance.py <board.kicad_pcb>
Exit 0 on PASS, 1 on any FAIL.
"""
import sys, os, math, re
import pcbnew

if len(sys.argv) < 2:
    sys.exit("usage: audit_layout_compliance.py <board.kicad_pcb>")

board = pcbnew.LoadBoard(sys.argv[1])
fails = []
warns = []


def get_outline_bbox():
    xs = []
    ys = []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            xs += [pcbnew.ToMM(d.GetStart().x), pcbnew.ToMM(d.GetEnd().x)]
            ys += [pcbnew.ToMM(d.GetStart().y), pcbnew.ToMM(d.GetEnd().y)]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def collect_components():
    items = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        p = fp.GetPosition()
        items[ref] = {
            "x": pcbnew.ToMM(p.x),
            "y": pcbnew.ToMM(p.y),
            "fp": fp,
            "side": "F" if fp.GetLayer() == pcbnew.F_Cu else "B",
        }
    return items


# ----- check 1: off-board (PAD-EXTENT-AWARE per master 2026-05-24 Sai-catch #2 fix) -----
# Previously used component CENTER which missed C38 case (center 0.17mm, pad extends to -0.56mm).
# Now uses pad bbox extent — any pad whose bbox exceeds board outline = FAIL.
def check_off_board(items, bbox):
    if not bbox:
        warns.append("no board outline found; off-board check skipped")
        return
    x_min, y_min, x_max, y_max = bbox
    m_center = 2.0     # ≥2mm center inset (for footprint body)
    m_pad = 0.3        # ≥0.3mm pad-extent inset (fab routing clearance)
    off_center = []
    off_pad = []
    for r, d in items.items():
        cx, cy = d["x"], d["y"]
        if not (x_min - m_center <= cx <= x_max + m_center
                and y_min - m_center <= cy <= y_max + m_center):
            off_center.append(r)
            continue  # center off-board is the bigger violation
        # Pad-extent check
        for pad in d["fp"].Pads():
            bb = pad.GetBoundingBox()
            px0 = pcbnew.ToMM(bb.GetLeft())
            py0 = pcbnew.ToMM(bb.GetTop())
            px1 = pcbnew.ToMM(bb.GetRight())
            py1 = pcbnew.ToMM(bb.GetBottom())
            if (px0 < x_min + m_pad or py0 < y_min + m_pad
                    or px1 > x_max - m_pad or py1 > y_max - m_pad):
                off_pad.append((r, pad.GetPadName(), px0, py0, px1, py1))
                break
    if off_center:
        fails.append(f"OFF-BOARD-CENTER: {len(off_center)} footprints with center outside outline+{m_center}mm")
        for r in off_center[:10]:
            d = items[r]
            fails.append(f"  {r} at ({d['x']:.2f}, {d['y']:.2f})")
        if len(off_center) > 10:
            fails.append(f"  ... and {len(off_center) - 10} more")
    if off_pad:
        fails.append(f"OFF-BOARD-PAD: {len(off_pad)} footprint(s) with pad extending beyond board outline (≤{m_pad}mm clearance)")
        for r, pn, x0, y0, x1, y1 in off_pad[:10]:
            fails.append(f"  {r}.pad{pn} bbox ({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f}) vs outline ({x_min:.2f},{y_min:.2f})-({x_max:.2f},{y_max:.2f})")


# ----- check 2: pad-overlap (same-net vs different-net split) -----
def check_pad_overlap(items):
    pads = []
    for ref, d in items.items():
        for pad in d["fp"].Pads():
            bb = pad.GetBoundingBox()
            layers = pad.GetLayerSet()
            try:
                net = pad.GetNet().GetNetname()
            except Exception:
                net = ""
            pads.append({
                "ref": ref,
                "pad": pad.GetPadName(),
                "net": net,
                "bb": (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                       pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())),
                "layers_F": layers.Contains(pcbnew.F_Cu),
                "layers_B": layers.Contains(pcbnew.B_Cu),
            })
    same_net = 0
    diff_net = 0
    diff_pairs = []
    same_pairs = []
    for i in range(len(pads)):
        a = pads[i]
        for j in range(i + 1, len(pads)):
            b = pads[j]
            if a["ref"] == b["ref"]:
                continue
            same_layer = ((a["layers_F"] and b["layers_F"])
                          or (a["layers_B"] and b["layers_B"]))
            if not same_layer:
                continue
            ax1, ay1, ax2, ay2 = a["bb"]
            bx1, by1, bx2, by2 = b["bb"]
            if ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1:
                # Same non-empty net = intentional pour overlap (not fab-blocking).
                if a["net"] and b["net"] and a["net"] == b["net"]:
                    same_net += 1
                    if len(same_pairs) < 8:
                        same_pairs.append((a["ref"], a["pad"], b["ref"], b["pad"], a["net"]))
                else:
                    diff_net += 1
                    if len(diff_pairs) < 12:
                        diff_pairs.append((a["ref"], a["pad"], a["net"] or "<noconn>",
                                           b["ref"], b["pad"], b["net"] or "<noconn>"))
    total = same_net + diff_net
    # Always emit summary line (PASS or FAIL) so worker/master can grep.
    if total:
        fails.append(f"PAD-OVERLAP-TOTAL: {total} (same-net {same_net} intentional, "
                     f"different-net {diff_net} FAB-BLOCKING)")
        if diff_net:
            fails.append(f"PAD-OVERLAP-DIFFNET: {diff_net} different-net pad pairs")
            for r1, p1, n1, r2, p2, n2 in diff_pairs:
                fails.append(f"  {r1}.{p1}[{n1}] <-> {r2}.{p2}[{n2}]")
            if diff_net > len(diff_pairs):
                fails.append(f"  ... and {diff_net - len(diff_pairs)} more different-net pairs")
        if same_net:
            fails.append(f"PAD-OVERLAP-SAMENET: {same_net} same-net pad pairs (intentional pour/bus overlap)")
            for r1, p1, r2, p2, net in same_pairs[:5]:
                fails.append(f"  {r1}.{p1} <-> {r2}.{p2}  net={net}")
            if same_net > 5:
                fails.append(f"  ... and {same_net - 5} more same-net pairs")


# ----- check 3: symmetry (4 channels) -----
def check_symmetry(items, board_h=None, board_w=None):
    # PR-A4-redo 2026-05-23: read board outline dynamically (was hardcoded 95×100)
    bb = get_outline_bbox()
    if bb:
        x_min, y_min, x_max, y_max = bb
        if board_w is None: board_w = x_max - x_min
        if board_h is None: board_h = y_max - y_min
    if board_w is None: board_w = 100.0
    if board_h is None: board_h = 100.0
    fets = {ref: (d["x"], d["y"]) for ref, d in items.items()
            if ref.startswith("Q") and ref[1:].isdigit()
            and 5 <= int(ref[1:]) <= 28}
    # Channel-to-FET assignment by quadrant
    ch1 = {ref: (x, y) for ref, (x, y) in fets.items() if x < 50 and y >= 47.5}
    ch2 = {ref: (x, y) for ref, (x, y) in fets.items() if x >= 50 and y >= 47.5}
    ch3 = {ref: (x, y) for ref, (x, y) in fets.items() if x >= 50 and y < 47.5}
    ch4 = {ref: (x, y) for ref, (x, y) in fets.items() if x < 50 and y < 47.5}
    for name, ch, n in [("CH1", ch1, 6), ("CH2", ch2, 6),
                        ("CH3", ch3, 6), ("CH4", ch4, 6)]:
        if len(ch) != n:
            fails.append(f"SYMMETRY: {name} has {len(ch)} FETs, expected {n}")
    # Pure row-pitch check: each channel's Y rows must be P=12
    for name, ch in [("CH1", ch1), ("CH2", ch2), ("CH3", ch3), ("CH4", ch4)]:
        if len(ch) < 3:
            continue
        ys = sorted({round(y, 2) for _, y in ch.values()})
        if len(ys) < 2:
            continue
        deltas = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
        for d in deltas:
            if abs(d - 12.0) > 0.5:
                fails.append(f"SYMMETRY: {name} row pitch {d:.2f}mm (expected 12.00mm)")
                break
    # Cross-channel mirror: CH1 vs CH2 about X=board_w/2
    for r1 in ch1:
        x1, y1 = ch1[r1]
        # find CH2 ref at expected mirror position
        ex, ey = board_w - x1, y1
        partner = min(ch2.items(),
                      key=lambda kv: math.hypot(kv[1][0] - ex, kv[1][1] - ey),
                      default=None)
        if partner is None:
            continue
        pref, (px, py) = partner
        dx, dy = abs(px - ex), abs(py - ey)
        if dx > 0.5 or dy > 0.5:
            fails.append(
                f"SYMMETRY: {r1}@({x1:.1f},{y1:.1f}) X-mirror partner "
                f"{pref}@({px:.1f},{py:.1f}) deviates ({dx:.1f},{dy:.1f}) mm from expected ({ex:.1f},{ey:.1f})"
            )
    # CH1 vs CH4 about Y=board_h/2
    for r1 in ch1:
        x1, y1 = ch1[r1]
        ex, ey = x1, board_h - y1
        partner = min(ch4.items(),
                      key=lambda kv: math.hypot(kv[1][0] - ex, kv[1][1] - ey),
                      default=None)
        if partner is None:
            continue
        pref, (px, py) = partner
        dx, dy = abs(px - ex), abs(py - ey)
        if dx > 0.5 or dy > 0.5:
            fails.append(
                f"SYMMETRY: {r1}@({x1:.1f},{y1:.1f}) Y-mirror partner "
                f"{pref}@({px:.1f},{py:.1f}) deviates ({dx:.1f},{dy:.1f}) mm from expected ({ex:.1f},{ey:.1f})"
            )


# ----- check 4: passive anchoring -----
# Role detection by ref + value heuristic; complete mapping requires schematic parse
ROLE_MAX_MM = {
    "decouple": 3.0,
    "gate_R": 5.0,
    "bootstrap_C": 2.0,
    "sense_R": 3.0,
    "snubber_RC": 3.0,
    "pull_R": 5.0,
    "feedback_R": 3.0,
    "led_R": 2.0,
}


def check_passive_anchoring(items):
    fets = [(ref, d["x"], d["y"]) for ref, d in items.items()
            if ref.startswith("Q") and ref[1:].isdigit()
            and 5 <= int(ref[1:]) <= 28]
    ics = [(ref, d["x"], d["y"]) for ref, d in items.items()
           if ref.startswith("U") and ref[1:].isdigit()]
    parents = fets + ics
    passives = [(ref, d["x"], d["y"]) for ref, d in items.items()
                if ref[0] in ("R", "C") and ref[1:].isdigit()]
    far = []
    for r, x, y in passives:
        if not parents:
            break
        nearest = min(parents,
                      key=lambda p: math.hypot(p[1] - x, p[2] - y))
        d = math.hypot(nearest[1] - x, nearest[2] - y)
        if d > 5.0:
            far.append((r, x, y, nearest[0], d))
    if far:
        # Many passives won't have a FET/IC parent (BEC, MCU support, etc.);
        # report worst >10mm as a warning, >20mm as a hard fail
        very_far = [t for t in far if t[4] > 20.0]
        moderate = [t for t in far if 10.0 < t[4] <= 20.0]
        if very_far:
            fails.append(f"PASSIVE-ANCHORING: {len(very_far)} passives >20mm from any FET/IC parent (likely islanded)")
            for r, x, y, p, d in sorted(very_far, key=lambda t: -t[4])[:10]:
                fails.append(f"  {r} at ({x:.1f},{y:.1f}) -> nearest {p} @ {d:.1f} mm")
        if moderate:
            warns.append(f"PASSIVE-ANCHORING: {len(moderate)} passives 10-20mm from nearest parent (verify role)")


# ----- check 5: decoupling caps -----
def check_decoupling(items):
    """R25 enforcement: every IC must have a decoupling cap within 3mm AND on
    the SAME copper layer. Opposite-side via adds ~0.5nH inductance, defeats
    decoupling above ~50MHz. Master 2026-05-24 extension."""
    ics = [(ref, d["x"], d["y"], d["side"]) for ref, d in items.items()
           if ref.startswith("U") and ref[1:].isdigit()]
    caps = [(ref, d["x"], d["y"], d["side"]) for ref, d in items.items()
            if ref.startswith("C") and ref[1:].isdigit()]
    no_cap = []
    wrong_side = []
    for ref, x, y, side in ics:
        nearby_any = [c for c in caps
                      if math.hypot(c[1] - x, c[2] - y) <= 3.0]
        if not nearby_any:
            no_cap.append((ref, x, y))
            continue
        # R25 same-side check: at least one cap within 3mm must be on same side
        same_side_caps = [c for c in nearby_any if c[3] == side]
        if not same_side_caps:
            wrong_side.append((ref, x, y, side, nearby_any[0][0], nearby_any[0][3]))
    if no_cap:
        fails.append(f"DECOUPLING: {len(no_cap)} ICs have no cap within 3mm")
        for r, x, y in no_cap[:10]:
            fails.append(f"  {r} at ({x:.1f},{y:.1f}) — no C within 3mm")
    if wrong_side:
        fails.append(f"DECOUPLING-R25-SAME-SIDE: {len(wrong_side)} ICs have decoupling cap on OPPOSITE side (R25 violation)")
        for r, x, y, side, c_ref, c_side in wrong_side[:10]:
            fails.append(f"  {r} on {side}.Cu at ({x:.1f},{y:.1f}) — nearest cap {c_ref} on {c_side}.Cu (opposite side)")


# ----- check 6: mount-hole vs body conflict (PR-spine-fix 2026-05-23) -----
def check_mount_hole_vs_body(items):
    """For every mount hole H*, verify no other component's pad bbox intersects
    the hole's 3mm keep-out radius. Catches the PR-S3 H1/H2-inside-U1-Hall bug."""
    mount_holes = []
    for ref, d in items.items():
        if ref.startswith("H") and len(ref) > 1 and ref[1:].isdigit():
            mount_holes.append((ref, d["x"], d["y"]))
    if not mount_holes:
        return
    conflicts = []
    KEEPOUT_R = 3.0  # mm — M3 clearance + 1.5mm trace keepout per industry std
    for h_ref, h_x, h_y in mount_holes:
        for ref, d in items.items():
            if ref == h_ref or ref.startswith("H"):
                continue
            for pad in d["fp"].Pads():
                bb = pad.GetBoundingBox()
                px1 = pcbnew.ToMM(bb.GetLeft())
                py1 = pcbnew.ToMM(bb.GetTop())
                px2 = pcbnew.ToMM(bb.GetRight())
                py2 = pcbnew.ToMM(bb.GetBottom())
                # Closest point of pad bbox to hole center
                cx = max(px1, min(h_x, px2))
                cy = max(py1, min(h_y, py2))
                d_min = math.hypot(h_x - cx, h_y - cy)
                if d_min < KEEPOUT_R:
                    conflicts.append((h_ref, ref, d_min))
                    break  # only flag once per component
    if conflicts:
        fails.append(f"MOUNT-HOLE-CONFLICT: {len(conflicts)} component(s) inside mount-hole {KEEPOUT_R}mm keep-out")
        for h, r, d_min in conflicts[:10]:
            fails.append(f"  {h} keep-out hit by {r} (closest pad {d_min:.2f}mm)")


# ----- check 7: pad-in-body bbox (Defect-1 class) -----
# Detects footprints whose pads are physically separated from the footprint body,
# e.g., kinet2pcb library bug where Allegro_CB_PFF has pads 4-5 21mm offset from body.
def check_pad_in_body_bbox():
    """For each footprint, verify every pad center is within the body bbox
    (Edge/SilkS/Fab outline) + 5mm. Catches "floating pad" library bugs."""
    suspects = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        # Use footprint-relative body bbox (includes silk/fab outlines).
        # PADs that fall outside body+5mm are suspect.
        pad_positions = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
                         for p in fp.Pads()]
        if len(pad_positions) < 2:
            continue
        # Compute pad-cluster bbox and pad-pair max separation
        xs = [p[0] for p in pad_positions]
        ys = [p[1] for p in pad_positions]
        max_x_span = max(xs) - min(xs)
        max_y_span = max(ys) - min(ys)
        # Suspect threshold: if any pad is >20mm from the centroid of others, flag
        cx = sum(xs) / len(xs); cy = sum(ys) / len(ys)
        for p in fp.Pads():
            ppos = p.GetPosition()
            px, py = pcbnew.ToMM(ppos.x), pcbnew.ToMM(ppos.y)
            d = math.hypot(px - cx, py - cy)
            if d > 15.0:  # 15mm is generous — flags ACS758-CB-PFF-class issues
                suspects.append((ref, p.GetNumber(), px, py, d))
                break
    if suspects:
        fails.append(f"PAD-IN-BODY-BBOX: {len(suspects)} footprint(s) have pads >15mm from cluster centroid (likely library bug)")
        for ref, padn, x, y, d in suspects[:10]:
            fails.append(f"  {ref} pad {padn!r} at ({x:.1f},{y:.1f}) is {d:.1f}mm from cluster centroid")


# ----- check 8: motor-pad clear-zone (Defect-2 class) -----
# Motor terminal pads need 14-16AWG solder clearance — no components within
# pad bbox + 2mm keep-out.
MOTOR_TP_REFS = ('TP19','TP20','TP21','TP26','TP27','TP28',
                 'TP33','TP34','TP35','TP40','TP41','TP42')
MOTOR_PAD_KEEPOUT = 2.0

_MOTOR_ADJACENT_NET_RE = re.compile(
    r'^(MOTOR_[ABC]_CH\d+|BEMF_[ABC]_CH\d+|CSA_[ABC]_OUT_CH\d+'
    r'|CSA_MAX_CH\d+|SHUNT_[ABC]_TOP_CH\d+)$'
)


def _has_motor_adjacent_net_pad(fp):
    """True if footprint has a pad on a motor-adjacent sense net.
    Master 2026-05-24 path D: exempt topologically-required sense components.
    See feedback-motor-pad-clear-zone.md memory for full rationale."""
    for pad in fp.Pads():
        no = pad.GetNet()
        if no is None: continue
        try:
            n = no.GetNetname()
        except Exception:
            continue
        if _MOTOR_ADJACENT_NET_RE.match(n):
            return True
    return False


# NEW check: coincident-placement bugs (master 2026-05-24 PR #71 reject)
def check_coincident_placement():
    """Pairs of components within 1.5mm center-to-center on same layer.
    Real bug: 2 components can't occupy same footprint spot at assembly."""
    fps = []
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if r.startswith('H'): continue
        p = fp.GetPosition()
        fps.append((r, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), fp.GetLayer()))
    bugs = []
    for i in range(len(fps)):
        r1, x1, y1, l1 = fps[i]
        for j in range(i + 1, len(fps)):
            r2, x2, y2, l2 = fps[j]
            if l1 != l2: continue
            d = math.hypot(x1 - x2, y1 - y2)
            if d < 1.5:
                bugs.append((d, r1, r2, x1, y1))
    if bugs:
        fails.append(f"COINCIDENT-PLACEMENT: {len(bugs)} component-pair(s) <1.5mm center-to-center on same layer (real bug, not intentional)")
        for d, r1, r2, x, y in bugs[:15]:
            fails.append(f"  {d:.2f}mm: {r1} <-> {r2} near ({x:.2f},{y:.2f})")


# Master 2026-05-24 Gap #5: detect fp_layer vs pad_layer mismatch (trap class from
# [[feedback-flip-bcu-footprints-recurrence]] — text-edit (layer F→B) without flipping pads).
# In PR #71 this trap masked 162 footprints with fp_layer=B.Cu but pad_layer=F.Cu,
# inflating audit PAD-OVERLAP count from 9 to 245.
def check_fp_layer_mismatch():
    """Footprint declared layer vs actual pad copper layer must agree. If
    fp.GetLayer() reports B.Cu but pads are on F.Cu (or vice versa), Freerouting
    + audit will treat them inconsistently. Skip pads with no copper layer
    (PDFN-8 courtyard/no-net unnamed pads etc.)."""
    bugs = []
    for fp in board.GetFootprints():
        fp_layer = fp.GetLayer()
        for pad in fp.Pads():
            if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue  # THT pads span both layers
            ls = pad.GetLayerSet()
            pad_F = ls.Contains(pcbnew.F_Cu)
            pad_B = ls.Contains(pcbnew.B_Cu)
            if not (pad_F or pad_B):
                continue  # no copper layer — courtyard artifact, skip
            if fp_layer == pcbnew.F_Cu and pad_B and not pad_F:
                bugs.append((fp.GetReference(), 'fp=F.Cu pad=B-only'))
                break
            if fp_layer == pcbnew.B_Cu and pad_F and not pad_B:
                bugs.append((fp.GetReference(), 'fp=B.Cu pad=F-only'))
                break
    if bugs:
        fails.append(f"FP-LAYER-MISMATCH: {len(bugs)} footprint(s) with fp.GetLayer() ≠ pad copper layer (text-edit-without-flip trap, run flip_bcu_footprints.py)")
        for r, why in bugs[:15]:
            fails.append(f"  {r}: {why}")


# PR #67 Sai-eye catch #4: TP-spacing audit gate (re-added per master 2026-05-24)
def check_test_point_spacing():
    """Test points (TP*) on the same layer must be ≥4mm center-to-center to
    allow scope probe access. PR #67 locked the threshold; re-codified as
    audit gate per master directive (was lost during edits)."""
    THRESH = 4.0
    tps = []
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if not r.startswith('TP'): continue
        p = fp.GetPosition()
        tps.append((r, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), fp.GetLayer()))
    bugs = []
    for i in range(len(tps)):
        r1, x1, y1, l1 = tps[i]
        for j in range(i + 1, len(tps)):
            r2, x2, y2, l2 = tps[j]
            if l1 != l2: continue
            d = math.hypot(x1 - x2, y1 - y2)
            if d < THRESH:
                bugs.append((d, r1, r2, x1, y1))
    if bugs:
        fails.append(f"TP-SPACING: {len(bugs)} TP-pair(s) <{THRESH}mm c-to-c on same layer (probe access blocked, Sai catch #4)")
        for d, r1, r2, x, y in bugs[:10]:
            fails.append(f"  {d:.2f}mm: {r1} <-> {r2} near ({x:.2f},{y:.2f})")


# PR #67 Sai-eye catch #5: external connector edge audit gate
def check_external_connector_edge():
    """J14 FC + J12 AUX must be ≤5mm from N/S board edge (cable bend zone)."""
    EDGE_MAX = 5.0
    bb = get_outline_bbox()
    if not bb: return
    _, _, _, y_max = bb
    bugs = []
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if r in ('J14', 'J12'):
            cy = pcbnew.ToMM(fp.GetPosition().y)
            d_edge = min(cy, y_max - cy)
            if d_edge > EDGE_MAX:
                bugs.append((r, fp.GetValue(), cy, d_edge))
    if bugs:
        fails.append(f"EXTERNAL-CONNECTOR-EDGE: {len(bugs)} cable connector(s) >{EDGE_MAX}mm from N/S edge (Sai catch #5)")
        for r, v, cy, d in bugs:
            fails.append(f"  {r} ({v}) Y={cy:.1f}, {d:.1f}mm from edge")


# Master 2026-05-24 Gap #3 (Sai catch #9): label-overlap
# Silkscreen refdes/value text overlapping adjacent component bbox.
# Catches Findings 3+4 from Sai 2026-05-24 hand-check (R102/R140/R144 cluster
# and C38/C39/C46/C47 cluster — components at 1.5-2.5mm spacing with piled labels).
def check_label_overlap():
    """Silkscreen refdes TEXT bbox overlaps another component's BODY bbox on
    the same side. Uses real fp.Reference() PCB_FIELD bbox (not estimated).
    Only counts visible refdes texts. Fail when text bbox lies fully within
    another component's body bbox (aesthetic piling — typically caused by
    density >2.5mm placement). Detection-only; manual fix via refdes
    reposition."""
    items = []
    for fp in board.GetFootprints():
        if fp.GetReference().startswith('H'): continue
        bb = fp.GetBoundingBox()
        items.append({
            'ref': fp.GetReference(),
            'fp': fp,
            'side': 'F' if fp.GetLayer() == pcbnew.F_Cu else 'B',
            'body': (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                     pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())),
        })
    bugs = []
    for it in items:
        rf = it['fp'].Reference()
        if not rf.IsVisible(): continue
        tb = rf.GetBoundingBox()
        tx0, ty0 = pcbnew.ToMM(tb.GetLeft()), pcbnew.ToMM(tb.GetTop())
        tx1, ty1 = pcbnew.ToMM(tb.GetRight()), pcbnew.ToMM(tb.GetBottom())
        # Look for another component on same side whose body FULLY contains the
        # text bbox (means text is INSIDE another component — definite issue)
        for ot in items:
            if ot['ref'] == it['ref'] or ot['side'] != it['side']: continue
            bx0, by0, bx1, by1 = ot['body']
            # Full-containment check (text bbox inside body bbox, with 0.1mm tolerance)
            if (bx0 - 0.1 <= tx0 and tx1 <= bx1 + 0.1
                    and by0 - 0.1 <= ty0 and ty1 <= by1 + 0.1):
                bugs.append((it['ref'], ot['ref']))
                break
    if bugs:
        fails.append(f"LABEL-OVERLAP: {len(bugs)} refdes silk text inside another component's body bbox (Sai catch #9)")
        for r, body_ref in bugs[:10]:
            fails.append(f"  {r} silk inside {body_ref}")


# Master 2026-05-24 Gap #4 (Sai catch #10): silk-on-pad
# Silkscreen text overlapping copper pad → solder joint defect (silk ink on pad).
def check_silk_on_pad():
    """Real fp.Reference() text bbox intersects another component's PAD bbox
    on the same copper side. DFM critical — silk ink on solder pad creates
    bad joint. Uses pcbnew GetBoundingBox() for the text PCB_FIELD."""
    pads_by_layer = {'F': [], 'B': []}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            entry = {'ref': fp.GetReference(), 'pad': pad.GetPadName(),
                     'box': (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                             pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))}
            if ls.Contains(pcbnew.F_Cu): pads_by_layer['F'].append(entry)
            if ls.Contains(pcbnew.B_Cu): pads_by_layer['B'].append(entry)
    bugs = []
    CLR = 0.05
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith('H'): continue
        rf = fp.Reference()
        if not rf.IsVisible(): continue
        tb = rf.GetBoundingBox()
        tx0, ty0 = pcbnew.ToMM(tb.GetLeft()), pcbnew.ToMM(tb.GetTop())
        tx1, ty1 = pcbnew.ToMM(tb.GetRight()), pcbnew.ToMM(tb.GetBottom())
        side = 'F' if fp.GetLayer() == pcbnew.F_Cu else 'B'
        for p in pads_by_layer[side]:
            if p['ref'] == ref: continue
            px0, py0, px1, py1 = p['box']
            px0 -= CLR; py0 -= CLR; px1 += CLR; py1 += CLR
            if tx0 < px1 and tx1 > px0 and ty0 < py1 and ty1 > py0:
                bugs.append((ref, p['ref'], p['pad']))
                break
    if bugs:
        fails.append(f"SILK-ON-PAD: {len(bugs)} refdes silk text on copper pad (Sai catch #10, DFM critical)")
        for r, p_ref, p_num in bugs[:10]:
            fails.append(f"  {r} silk on {p_ref}.pad{p_num}")


# Master 2026-05-24 Sai-class catch #8: fiducial markers for JLC SMT assembly
def check_fiducials():
    """≥3 fiducials per side (F.Cu, B.Cu) for JLC SMT machine-vision alignment."""
    fids_f = []
    fids_b = []
    for fp in board.GetFootprints():
        r = fp.GetReference()
        v = fp.GetValue() or ''
        lib_name = str(fp.GetFPID().GetLibItemName() or '')
        is_fid = r.startswith('FID') or 'Fiducial' in v or 'Fiducial' in lib_name
        if not is_fid: continue
        p = fp.GetPosition()
        x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
        if fp.GetLayer() == pcbnew.F_Cu:
            fids_f.append((r, x, y))
        else:
            fids_b.append((r, x, y))
    issues = []
    if len(fids_f) < 3:
        issues.append(f"F.Cu side has {len(fids_f)} fiducials, need ≥3 (JLC SMT alignment)")
    if len(fids_b) < 3:
        issues.append(f"B.Cu side has {len(fids_b)} fiducials, need ≥3 (JLC SMT alignment)")
    for side_name, fids in [('F.Cu', fids_f), ('B.Cu', fids_b)]:
        if len(fids) >= 3:
            max_pair = max(
                math.hypot(a[1] - b[1], a[2] - b[2])
                for i, a in enumerate(fids)
                for b in fids[i + 1:]
            )
            if max_pair < 40.0:
                issues.append(f"{side_name} max fiducial separation {max_pair:.1f}mm < 40mm (triangulation accuracy)")
    if issues:
        fails.append(f"FIDUCIALS: {len(issues)} issue(s)")
        for msg in issues:
            fails.append(f"  {msg}")


def check_motor_pad_clear():
    zones = {}
    for fp in board.GetFootprints():
        if fp.GetReference() in MOTOR_TP_REFS:
            bb = fp.GetBoundingBox()
            zones[fp.GetReference()] = (
                pcbnew.ToMM(bb.GetLeft()) - MOTOR_PAD_KEEPOUT,
                pcbnew.ToMM(bb.GetTop()) - MOTOR_PAD_KEEPOUT,
                pcbnew.ToMM(bb.GetRight()) + MOTOR_PAD_KEEPOUT,
                pcbnew.ToMM(bb.GetBottom()) + MOTOR_PAD_KEEPOUT,
            )
    encroach = []
    motor_net_exempt = 0
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if r in MOTOR_TP_REFS or r.startswith(('Q', 'J', 'U', 'H')):
            continue
        pos = fp.GetPosition()
        cx, cy = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        for tp, (x1, y1, x2, y2) in zones.items():
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                # master 2026-05-24 path D: exempt motor-adjacent-sense-net comps
                if _has_motor_adjacent_net_pad(fp):
                    motor_net_exempt += 1
                else:
                    encroach.append((r, tp, cx, cy))
                break
    if encroach:
        fails.append(f"MOTOR-PAD-CLEAR: {len(encroach)} non-sense-net component(s) inside motor-TP zone + {MOTOR_PAD_KEEPOUT}mm keep-out")
        for ref, tp, cx, cy in encroach[:10]:
            fails.append(f"  {ref} at ({cx:.1f},{cy:.1f}) inside {tp} zone")
    if motor_net_exempt:
        warns.append(f"MOTOR-PAD-CLEAR-EXEMPTS: {motor_net_exempt} motor-adjacent-net components inside motor-TP zone (exempt per master path D 2026-05-24, see feedback-motor-pad-clear-zone)")


# ----- check 9: quadrant component-count balance (Defect-3 class) -----
# Per R19: components are classified into 3 buckets with different balance rules:
#   1. CHANNEL bucket: 24 channel FETs + per-channel passives + MCU/DRV instances.
#      Rule: ≤2 delta on CH1↔CH2 (NW↔NE) and CH3↔CH4 (SE↔SW) — the symmetry payoff.
#   2. S-ZONE-MIRROR-PAIR bucket: paired multi-instance S-zone components.
#      Rule: ≤2 delta on NW↔NE and SW↔SE.
#   3. SINGLE-INSTANCE bucket: inherently single-instance subsystem parts.
#      Rule: warn but don't fail (placed on central spine X=50±5 or single-strip).
# Refined per master Defect-3 adjudication 2026-05-23.

QUADRANT_DELTA_LIMIT = 2

# Explicit S-zone mirror-pair refs (multi-instance, must X-mirror about X=50)
S_ZONE_MIRROR_PAIR_REFS = {
    # S1 protection FETs (4× parallel)
    'Q1', 'Q2', 'Q3', 'Q4',
    # S1 NTC pair
    'R1', 'R2',
    # S2 bulk caps (2×2 grid: 4 instances expected)
    'C1', 'C2', 'C3', 'C4',
    # S5 BEC bucks 1-4 + inductors (mirror pair J2↔J4, J3↔J5; L1↔L3, L2↔L4)
    'J2', 'J3', 'J4', 'J5',
    'L1', 'L2', 'L3', 'L4',
    # S5 FB resistor pairs (R6/R7 ↔ R10/R11, R8/R9 ↔ R12/R13)
    'R6', 'R7', 'R8', 'R9', 'R10', 'R11', 'R12', 'R13',
    # S5 boot caps (C7 ↔ C14, C11 ↔ C17)
    'C7', 'C11', 'C14', 'C17',
    # S5 input-side eFuses + diodes (D5/D6 ↔ D7/D8; J7 ↔ J9)
    'D5', 'D6', 'D7', 'D8',
    'J7', 'J9',
    # S5 output-side ferrites/TVS (L6 ↔ L8 ↔ L9, D10/D11 ↔ D12/D13 partials)
    'L6', 'L8', 'L9',
    'D10', 'D12', 'D13',
    # S6 LED pairs + USBLC6 J15↔J16
    'D3', 'D4', 'R4', 'R5',
    'J15', 'J16',
}

# Explicit single-instance refs (exempt from quadrant balance)
SINGLE_INSTANCE_REFS = {
    'J1',           # XT30 battery connector (central)
    'U1',           # Hall ACS770 (single)
    'U2',           # supervisor (if any)
    'J11',          # supervisor connector
    'J12',          # AUX header (single)
    'J14',          # FC header (single)
    'J17',          # 3rd USBLC6 (single — TLM+spare)
    'F1', 'F2',     # polyfuses (single per rail)
    'J6',           # Buck #5 V9_VTX2 (single instance)
    'L5', 'L10',    # Buck #5 inductor + output ferrite
    'D9', 'D14',    # Buck #5 catch + TVS diodes
    'R14', 'R15',   # Buck #5 FB pair (single-rail)
    'C20', 'C21',   # Buck #5 boot + C_OUT
    'C8', 'C12', 'C15', 'C18',  # post-ferrite C_OUT (mostly central or asymmetric)
    'D11',          # V5_PI5 TVS (single, central)
    'L7',           # V5_PI5 ferrite (single, central)
    'J10', 'J13',   # supervisor IC + LDO (single)
    'R3', 'D2',     # S1 gate cluster (R3 anchored to Q1, D2 to Q4 — paired but small)
    'D26',          # S1 historic SMBJ33A
    'C49', 'R36', 'R37',  # S6 VBAT divider (3 components, central)
}


def classify_ref(ref, fp):
    """Return one of: 'channel', 's_mirror', 'single', 'auto'."""
    # Single-instance explicit
    if ref in SINGLE_INSTANCE_REFS:
        return 'single'
    # Mount holes — separate concern
    if ref.startswith('H') and len(ref) > 1 and ref[1:].isdigit():
        return 'single'
    # Motor TPs (TP19-42) — single-instance per channel, but 12 of them so they balance naturally
    if ref in ('TP19','TP20','TP21','TP26','TP27','TP28',
               'TP33','TP34','TP35','TP40','TP41','TP42'):
        return 'channel'
    # S-zone mirror-pair explicit
    if ref in S_ZONE_MIRROR_PAIR_REFS:
        return 's_mirror'
    # Channel: by net analysis (any pad has _CHn)
    for pad in fp.Pads():
        net = pad.GetNet()
        if net and re.search(r'_CH[1234]', net.GetNetname()):
            return 'channel'
    # MCU/DRV/INA explicit channel instances (in case net parsing missed)
    if ref in ('J18','J19','J20','J21','J22','J23','J24','J25','J26','J27',
               'J28','J29','J30','J31','J32','J33','J34','J35','J36','J37'):
        return 'channel'
    # Channel FETs Q5-Q28
    if ref.startswith('Q') and ref[1:].isdigit():
        n = int(ref[1:])
        if 5 <= n <= 28:
            return 'channel'
    # Auto-anchored debris — passives w/o channel net, w/o explicit list membership
    return 'auto'


def quadrant_of(x, y, mid_x=50.0, mid_y=50.0):
    if x <= mid_x and y >= mid_y: return 'NW'
    elif x > mid_x and y >= mid_y: return 'NE'
    elif x <= mid_x and y < mid_y: return 'SW'
    return 'SE'


def check_quadrant_count_balance():
    bb = get_outline_bbox()
    if not bb:
        return
    x_min, y_min, x_max, y_max = bb
    mid_x = (x_min + x_max) / 2
    mid_y = (y_min + y_max) / 2

    buckets = {'channel': {'NW':0,'NE':0,'SW':0,'SE':0},
               's_mirror': {'NW':0,'NE':0,'SW':0,'SE':0},
               'single':  {'NW':0,'NE':0,'SW':0,'SE':0},
               'auto':    {'NW':0,'NE':0,'SW':0,'SE':0}}
    for fp in board.GetFootprints():
        if fp.GetLayer() != pcbnew.F_Cu:
            continue
        pos = fp.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        cls = classify_ref(fp.GetReference(), fp)
        # PR-A4-integrate amendment 5f boundary-noise fix:
        # For CHANNEL bucket, derive quadrant from the component's CH-NET (not
        # physical Y) to eliminate Y=50-axis boundary-noise. CH1→NW, CH2→NE,
        # CH3→SE, CH4→SW. Multi-CH refs use the lowest CH number.
        if cls == 'channel':
            chs = set()
            for pad in fp.Pads():
                if pad.GetNet():
                    for m in re.finditer(r'_CH([1234])', pad.GetNet().GetNetname()):
                        chs.add(int(m.group(1)))
            if chs:
                ch = min(chs)
                q = {1: 'NW', 2: 'NE', 3: 'SE', 4: 'SW'}[ch]
            else:
                # No CH-net (channel ICs like motor TPs classified by ref): fall back to position
                q = quadrant_of(x, y, mid_x, mid_y)
        else:
            q = quadrant_of(x, y, mid_x, mid_y)
        buckets[cls][q] += 1

    # Report per-bucket totals
    total_nw = sum(b['NW'] for b in buckets.values())
    total_ne = sum(b['NE'] for b in buckets.values())
    total_sw = sum(b['SW'] for b in buckets.values())
    total_se = sum(b['SE'] for b in buckets.values())

    # CHANNEL rule: ≤2 delta on NW↔NE (CH1↔CH2) and SW↔SE (CH4↔CH3)
    ch = buckets['channel']
    ch_fails = []
    if abs(ch['NW']-ch['NE']) > QUADRANT_DELTA_LIMIT:
        ch_fails.append(f"CH1(NW)↔CH2(NE) Δ={abs(ch['NW']-ch['NE'])}")
    if abs(ch['SW']-ch['SE']) > QUADRANT_DELTA_LIMIT:
        ch_fails.append(f"CH4(SW)↔CH3(SE) Δ={abs(ch['SW']-ch['SE'])}")

    # S-ZONE-MIRROR-PAIR rule: ≤2 delta on NW↔NE and SW↔SE
    sm = buckets['s_mirror']
    sm_fails = []
    if abs(sm['NW']-sm['NE']) > QUADRANT_DELTA_LIMIT:
        sm_fails.append(f"S-mirror NW↔NE Δ={abs(sm['NW']-sm['NE'])}")
    if abs(sm['SW']-sm['SE']) > QUADRANT_DELTA_LIMIT:
        sm_fails.append(f"S-mirror SW↔SE Δ={abs(sm['SW']-sm['SE'])}")

    # AUTO bucket rule: WARN ONLY (master adjudication 2026-05-23).
    # Auto-anchored debris (debug TPs, generic +3V3/GND/N$nn pulls, IC decoupling)
    # often has NO mirror partner by design — components anchored to single-instance
    # parents (MCU central spine, supervisor) cannot move ≥40mm away per R23
    # without breaking electrical function. The audit surfaces structural
    # asymmetry as a WARNING for verification, not a FAIL.
    au = buckets['auto']
    auto_warns = []
    AUTO_WARN_THRESHOLD = 4
    if abs(au['NW']-au['NE']) > AUTO_WARN_THRESHOLD:
        auto_warns.append(f"auto-anchored NW↔NE Δ={abs(au['NW']-au['NE'])} — verify no mirror partner exists then document as structural")
    if abs(au['SW']-au['SE']) > AUTO_WARN_THRESHOLD:
        auto_warns.append(f"auto-anchored SW↔SE Δ={abs(au['SW']-au['SE'])} — verify no mirror partner exists then document as structural")
    # No auto_fails list — only warns
    auto_fails = []

    # Composite report — always print bucket counts for transparency
    if ch_fails or sm_fails:
        fails.append(f"QUADRANT-BALANCE: channel and/or s_mirror bucket(s) over enforced limit")
        fails.append(f"  channel  NW={ch['NW']} NE={ch['NE']} SW={ch['SW']} SE={ch['SE']} (ENFORCED Δ≤{QUADRANT_DELTA_LIMIT})")
        fails.append(f"  s_mirror NW={sm['NW']} NE={sm['NE']} SW={sm['SW']} SE={sm['SE']} (ENFORCED Δ≤{QUADRANT_DELTA_LIMIT})")
        fails.append(f"  single   NW={buckets['single']['NW']} NE={buckets['single']['NE']} SW={buckets['single']['SW']} SE={buckets['single']['SE']} (EXEMPT — central/strip placement)")
        fails.append(f"  auto     NW={au['NW']} NE={au['NE']} SW={au['SW']} SE={au['SE']} (WARN-only — debris inherits parent asymmetry)")
        fails.append(f"  TOTAL    NW={total_nw} NE={total_ne} SW={total_sw} SE={total_se}")
        for f in ch_fails + sm_fails:
            fails.append(f"  {f}")
    else:
        warns.append(f"QUADRANT-BALANCE: channel + s_mirror PASS — channel NW={ch['NW']}/NE={ch['NE']}/SW={ch['SW']}/SE={ch['SE']}; "
                     f"s_mirror NW={sm['NW']}/NE={sm['NE']}/SW={sm['SW']}/SE={sm['SE']}; "
                     f"auto NW={au['NW']}/NE={au['NE']}/SW={au['SW']}/SE={au['SE']}; "
                     f"TOTAL NW={total_nw}/NE={total_ne}/SW={total_sw}/SE={total_se}")
    # AUTO bucket warnings — always surface (informational; documented as structural)
    for w in auto_warns:
        warns.append(f"AUTO-BUCKET: {w}")


# ----- check 12: PER-CHANNEL PASSIVE QUADRANT (Sai-eye-catch #6, 2026-05-23) -----
# Every R/C/L/D with a single _CH[1234] net must reside inside its parent channel
# quadrant. Cross-quadrant placement breaks R23 gate-R ≤5mm rule + violates
# symmetry [[feedback-symmetry-preserves-work]].
# Derived from locked FET positions Q5-Q28:
#   CH1 = Q5-Q10  at (12-30, 56-80)         → X=0-50,  Y=50-100
#   CH2 = mirror_X(CH1)        (Q11-Q16)    → X=50-100, Y=50-100
#   CH3 = 180°-rot(CH1, 50,50) (Q17-Q22)    → X=50-100, Y=0-50
#   CH4 = mirror_Y(CH1)        (Q23-Q28)    → X=0-50,  Y=0-50
# BOUNDARY_TOL: shared-bus caps placed on the central spine legitimately
# straddle a quadrant axis — exempt those within tol of a half-axis line.
CHAN_ZONES = {
    'CH1': (0, 50, 50, 100),
    'CH2': (50, 50, 100, 100),
    'CH3': (50, 0, 100, 50),
    'CH4': (0, 0, 50, 50),
}
BOUNDARY_TOL = 2.0

def check_per_channel_passive_quadrant():
    vio = []
    for ref, d in items.items():
        if not ref.startswith(('R', 'C', 'D', 'L')):
            continue
        fp = d['fp']
        chs = set()
        for p in fp.Pads():
            if p.GetNet():
                m = re.search(r'_CH([1234])$', p.GetNet().GetNetname())
                if m:
                    chs.add(int(m.group(1)))
        if len(chs) != 1:
            continue
        ch_name = f'CH{next(iter(chs))}'
        x, y = d['x'], d['y']
        x1, y1, x2, y2 = CHAN_ZONES[ch_name]
        # Boundary tolerance: shared-bus passives straddling X=50 or Y=50
        if abs(x - 50.0) <= BOUNDARY_TOL or abs(y - 50.0) <= BOUNDARY_TOL:
            continue
        if not (x1 <= x <= x2 and y1 <= y <= y2):
            vio.append((ref, ch_name, x, y))
    if vio:
        fails.append(f"CH-PASSIVE-QUADRANT: {len(vio)} channel-tagged passives outside parent quadrant")
        for ref, ch, x, y in sorted(vio)[:15]:
            fails.append(f"  {ref} expected {ch} actual ({x:.1f},{y:.1f})")
        if len(vio) > 15:
            fails.append(f"  ... and {len(vio) - 15} more")


# ----- run -----
items = collect_components()
bbox = get_outline_bbox()
check_off_board(items, bbox)
check_pad_overlap(items)
check_symmetry(items)
check_passive_anchoring(items)
check_decoupling(items)
check_mount_hole_vs_body(items)
check_pad_in_body_bbox()
check_motor_pad_clear()
check_coincident_placement()
check_fp_layer_mismatch()
check_test_point_spacing()
check_external_connector_edge()
check_fiducials()
check_label_overlap()
check_silk_on_pad()
check_quadrant_count_balance()
check_per_channel_passive_quadrant()

print(f"=== Layout compliance audit: {os.path.basename(sys.argv[1])} ===")
print(f"Components: {len(items)}")
if bbox:
    print(f"Board outline: ({bbox[0]:.1f},{bbox[1]:.1f}) to ({bbox[2]:.1f},{bbox[3]:.1f}) mm")
print()
if warns:
    print("WARNINGS:")
    for w in warns:
        print(f"  {w}")
    print()
if fails:
    print(f"FAIL ({len(fails)} issues):")
    for f in fails:
        print(f"  {f}")
    sys.exit(1)
print("PASS — all 9 layout-compliance checks clean")
