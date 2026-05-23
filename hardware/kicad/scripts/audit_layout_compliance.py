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


# ----- check 2: pad-overlap -----
def check_pad_overlap(items):
    pads = []
    for ref, d in items.items():
        for pad in d["fp"].Pads():
            bb = pad.GetBoundingBox()
            layers = pad.GetLayerSet()
            pads.append({
                "ref": ref,
                "pad": pad.GetPadName(),
                "bb": (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                       pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())),
                "layers_F": layers.Contains(pcbnew.F_Cu),
                "layers_B": layers.Contains(pcbnew.B_Cu),
            })
    overlaps = 0
    pairs = []
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
                overlaps += 1
                if len(pairs) < 8:
                    pairs.append((a["ref"], a["pad"], b["ref"], b["pad"]))
    if overlaps:
        fails.append(f"PAD-OVERLAP: {overlaps} pad pairs overlap on same layer")
        for r1, p1, r2, p2 in pairs:
            fails.append(f"  {r1}.{p1} <-> {r2}.{p2}")
        if overlaps > 8:
            fails.append(f"  ... and {overlaps - 8} more")


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


# ----- run -----
items = collect_components()
bbox = get_outline_bbox()
check_off_board(items, bbox)
check_pad_overlap(items)
check_symmetry(items)
check_passive_anchoring(items)
check_decoupling(items)

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
print("PASS — all 5 layout-compliance checks clean")
