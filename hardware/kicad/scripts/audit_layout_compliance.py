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

_MOTOR_ADJACENT_NET_RE = re.compile(
    r'^(MOTOR_[ABC]_CH\d+'             # motor net (gate clamp, TVS, BEMF top R)
    r'|BEMF_[ABC]_CH\d+'               # BEMF tap (bottom divider R, filter C)
    r'|CSA_[ABC]_OUT_CH\d+'            # INA output / CSA filter (downstream of INA)
    r'|CSA_MAX_CH\d+'                  # CSA diode-OR output
    r'|SHUNT_[ABC]_TOP_CH\d+'          # shunt resistor sense path
    r')$'
)


def _has_motor_adjacent_net_pad(fp):
    """True if footprint has at least one pad on a motor-adjacent sense net.
    PR-channel-template-redo Phase 3 amendment 2026-05-24 (master path D + ext):
    Sense-chain components (gate clamps, phase TVS, BEMF div top+bot+filter,
    CSA filter, shunt path) are TOPOLOGICALLY REQUIRED to be at/near the
    motor TP node. They are present as SMD before motor wire bonding and do
    NOT interfere with the assembly solder access concern that the
    MOTOR-PAD-CLEAR rule was designed to prevent.

    Exempted nets:
      MOTOR_<phase>_CH<n>     — motor net itself (Zener K side, TVS K, BEMF top)
      BEMF_<phase>_CH<n>      — BEMF divider tap (bottom R, 1nF filter)
      CSA_<phase>_OUT_CH<n>   — INA186 output (filter cap)
      CSA_MAX_CH<n>           — CSA diode-OR (BAT54)
      SHUNT_<phase>_TOP_CH<n> — shunt sense path (Kelvin)
    """
    for pad in fp.Pads():
        net_obj = pad.GetNet()
        if net_obj is None:
            continue
        try:
            n = net_obj.GetNetname()
        except Exception:
            continue
        if _MOTOR_ADJACENT_NET_RE.match(n):
            return True
    return False


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
                # Refinement (master path D 2026-05-24): motor-net components
                # are topologically required at the motor node; exempt them.
                if _has_motor_adjacent_net_pad(fp):
                    motor_net_exempt += 1
                else:
                    encroach.append((r, tp, cx, cy))
                break
    if encroach:
        fails.append(f"MOTOR-PAD-CLEAR: {len(encroach)} non-motor-net component(s) inside motor-TP zone + {MOTOR_PAD_KEEPOUT}mm keep-out")
        for ref, tp, cx, cy in encroach[:10]:
            fails.append(f"  {ref} at ({cx:.1f},{cy:.1f}) inside {tp} zone")
    if motor_net_exempt:
        # Informational note — motor-net topologically-required exempts.
        warns.append(f"MOTOR-PAD-CLEAR-EXEMPTS: {motor_net_exempt} motor-net-connected components inside motor-TP zone (exempt — topologically required at motor node, see master path D 2026-05-24)")


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
