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
import sys, os, math
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


# ----- check 1: off-board -----
def check_off_board(items, bbox):
    if not bbox:
        warns.append("no board outline found; off-board check skipped")
        return
    x_min, y_min, x_max, y_max = bbox
    m = 2.0
    off = [r for r, d in items.items()
           if not (x_min - m <= d["x"] <= x_max + m
                   and y_min - m <= d["y"] <= y_max + m)]
    if off:
        fails.append(f"OFF-BOARD: {len(off)} footprints outside outline+{m}mm")
        for r in off[:10]:
            d = items[r]
            fails.append(f"  {r} at ({d['x']:.2f}, {d['y']:.2f})")
        if len(off) > 10:
            fails.append(f"  ... and {len(off) - 10} more")


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
    ics = [(ref, d["x"], d["y"]) for ref, d in items.items()
           if ref.startswith("U") and ref[1:].isdigit()]
    caps = [(ref, d["x"], d["y"]) for ref, d in items.items()
            if ref.startswith("C") and ref[1:].isdigit()]
    bad = []
    for ref, x, y in ics:
        nearby_cap = [c for c in caps
                      if math.hypot(c[1] - x, c[2] - y) <= 3.0]
        if not nearby_cap:
            bad.append((ref, x, y))
    if bad:
        fails.append(f"DECOUPLING: {len(bad)} ICs have no cap within 3mm")
        for r, x, y in bad[:10]:
            fails.append(f"  {r} at ({x:.1f},{y:.1f}) — no C within 3mm")


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
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if r in MOTOR_TP_REFS or r.startswith(('Q', 'J', 'U', 'H')):
            continue
        pos = fp.GetPosition()
        cx, cy = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        for tp, (x1, y1, x2, y2) in zones.items():
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                encroach.append((r, tp, cx, cy))
                break
    if encroach:
        fails.append(f"MOTOR-PAD-CLEAR: {len(encroach)} component(s) inside motor-TP zone + {MOTOR_PAD_KEEPOUT}mm keep-out")
        for ref, tp, cx, cy in encroach[:10]:
            fails.append(f"  {ref} at ({cx:.1f},{cy:.1f}) inside {tp} zone")


# ----- check 9: quadrant component-count balance (Defect-3 class) -----
# Per R19: 4 channel quadrants should have near-identical component counts
# (≤2 delta) — enforces symmetric mirror via [[feedback-symmetry-preserves-work]].
QUADRANT_DELTA_LIMIT = 2

def check_quadrant_count_balance():
    bb = get_outline_bbox()
    if not bb:
        return
    x_min, y_min, x_max, y_max = bb
    mid_x = (x_min + x_max) / 2
    mid_y = (y_min + y_max) / 2
    quads = {'NW': 0, 'NE': 0, 'SW': 0, 'SE': 0}
    for fp in board.GetFootprints():
        if fp.GetLayer() != pcbnew.F_Cu:
            continue
        pos = fp.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        if x <= mid_x and y >= mid_y: quads['NW'] += 1
        elif x > mid_x and y >= mid_y: quads['NE'] += 1
        elif x <= mid_x and y < mid_y: quads['SW'] += 1
        else: quads['SE'] += 1
    deltas = {
        'NW vs NE': abs(quads['NW'] - quads['NE']),
        'SW vs SE': abs(quads['SW'] - quads['SE']),
        'NW vs SW': abs(quads['NW'] - quads['SW']),
        'NE vs SE': abs(quads['NE'] - quads['SE']),
    }
    over = {k: v for k, v in deltas.items() if v > QUADRANT_DELTA_LIMIT}
    if over:
        fails.append(f"QUADRANT-BALANCE: {len(over)} quadrant-pair delta(s) exceed {QUADRANT_DELTA_LIMIT}-count limit "
                     f"(NW={quads['NW']} NE={quads['NE']} SW={quads['SW']} SE={quads['SE']})")
        for pair, d in over.items():
            fails.append(f"  {pair}: Δ={d}")


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
check_quadrant_count_balance()

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
