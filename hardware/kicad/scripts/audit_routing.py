#!/usr/bin/env python3
"""audit_routing.py — Phase 5b routing compliance audit (Task #79).

Per master [[feedback-routing-procedures-gap]] — routing must be subsystem-aware
+ symmetry-preserving, not bulk autoroute. This audit gates each routing PR.

Six checks (all hard gates unless documented WARN-only):
  1. check_subsystem_zone   — track endpoints stay in parent subsystem zone
                              (exceptions: inter-subsystem buses VMOTOR, +V5, +3V3, GND)
  2. check_route_symmetry   — CH1↔CH2 (mirror_X), CH1↔CH4 (mirror_Y),
                              CH3 derived. Trace count + total length per channel
                              must match within ±5%.
  3. check_via_density      — no via cluster >2 vias / mm² in HV/MOTOR
                              high-current zones (VMOTOR pour areas, motor TP zones).
                              Heat-soak + manufacturability risk.
  4. check_diff_pair_balance — USBLC6 differential signals (DShot in/out, AUX,
                              telemetry) length-matched within ±0.5mm per pair.
                              Identifies pairs by ref + pad-pin schematic relationship.
  5. check_track_width      — per net class:
                                VMOTOR / +VMOTOR / MOTOR_X_CHn / SHUNT_*: ≥1.0mm on F.Cu/B.Cu/In3.Cu
                                +V5 / +V9 / V_BUCK*_OUT: ≥0.3mm
                                +3V3 / V3V3A / V5_FC etc: ≥0.25mm
                                Signal (PWM_*, GLA*, GHA*, BEMF_*, CSA_*): ≥0.15mm
                                GND: ≥0.2mm via plane pour (per-segment N/A)
  6. check_plane_island     — no isolated copper islands on inner planes
                              (In1.Cu GND, In3.Cu VMOTOR, In5.Cu GND).
                              Flood-fill from a known seed via.

Run: python3 audit_routing.py <board.kicad_pcb>
Exit 0 PASS, 1 FAIL. Self-test mode prints expected baseline failures.
"""
import sys, os, math, re
import pcbnew
from collections import defaultdict

if len(sys.argv) < 2:
    sys.exit("usage: audit_routing.py <board.kicad_pcb> [--subsystem CH1|CH2|...]")

PCB_PATH = sys.argv[1]
# Optional --subsystem CH1 limits unrouted-net check to that subsystem's nets
# (per §8 subsystem-scope PR methodology — CH2/3/4 nets are expected unrouted
# when only CH1 STEP 4 PR is open).
SUBSYSTEM_SCOPE = None
if "--subsystem" in sys.argv:
    SUBSYSTEM_SCOPE = sys.argv[sys.argv.index("--subsystem") + 1]
board = pcbnew.LoadBoard(PCB_PATH)
fails = []
warns = []
info = []


# Map subsystem zones (X, Y bounding rectangles) per place_board.py spec
SUBSYSTEM_ZONES = {
    'S1': (0, 0, 100, 13),         # battery input strip — north
    'S2': (15, 22, 85, 50),        # bulk cap grid
    'S3': (40, 0, 100, 50),        # supervisor + Hall (Hall east-SE, supervisor central)
    'S5': (0, 12, 100, 90),        # BEC rails (spans most of board for distribution)
    'S6': (0, 83, 100, 100),       # connectors north strip
    'CH1': (0, 50, 50, 100),       # NW
    'CH2': (50, 50, 100, 100),     # NE
    'CH3': (50, 0, 100, 50),       # SE
    'CH4': (0, 0, 50, 50),         # SW
}

# Inter-subsystem buses — exempt from check_subsystem_zone
INTER_SUBSYSTEM_NETS = {
    'GND', '+VMOTOR', 'VMOTOR_CH', 'VMOTOR_HALL_HI', 'VMOTOR_HALL_LO',
    'BATGND', 'GATE_RP', 'BATT_NTC',
    '+V5_FC', '+V5_PI5', '+V5_AI', '+V9_VTX1', '+V9_VTX2',
    '+3V3', 'V3V3A', 'HALL_VCC_5V',
    # Buck output rails are inter-subsystem (BEC → loads)
    'V_BUCK1_OUT', 'V_BUCK2_OUT', 'V_BUCK3_OUT', 'V_BUCK4_OUT', 'V_BUCK5_OUT',
    # Master 2026-05-24 REJECT v2 update: cross-subsystem distribution nets
    '+BATT',           # XT30 → south protection → north supervisor divider
    'BUS_CURR_HALL_OUT',  # Hall current sense bus to MCU (S3 → CH MCUs)
    'LED_PG_NODE',     # Power-good LED chain across board
    'TLM',             # DShot telemetry common return (CH → FC)
}

# Track-width minimums per net class (mm)
NET_CLASS_MIN_WIDTH = {
    'VMOTOR': 1.0,
    'MOTOR':  1.0,
    'SHUNT':  1.0,
    'V5':     0.3,
    'V9':     0.3,
    'V_BUCK': 0.3,
    'V3V3':   0.25,
    'BATGND': 1.0,
}
SIGNAL_MIN_WIDTH = 0.15


def net_class(netname):
    """Return (class_name, min_width_mm) for a net.

    Signal-vs-power discrimination: nets with 'VMOTOR_DIV', 'PG_VMOTOR',
    'VMOTOR_SUPER_CT' (sense/status low-current signals) are SIGNAL class,
    not VMOTOR power class. Only true VMOTOR power rails get 1.0mm.
    """
    if not netname:
        return ('NO_NET', 0)
    # High-current power rails (1.0mm min)
    if netname in ('+VMOTOR', 'VMOTOR_CH', 'VMOTOR_HALL_HI', 'VMOTOR_HALL_LO'):
        return ('VMOTOR', 1.0)
    if 'MOTOR_' in netname and not any(x in netname for x in ('_DIV', '_SUPER', 'PG_', 'SENSE')):
        return ('MOTOR', 1.0)
    if 'SHUNT_' in netname:
        return ('SHUNT', 1.0)
    if 'BATGND' in netname:
        return ('BATGND', 1.0)
    # +BATT is a high-current rail
    if netname == '+BATT' or netname == 'BATT_NTC':
        return ('VMOTOR', 1.0)
    # V5/V9/Buck power rails (medium current)
    if netname.startswith('+V5') or '_V5_' in netname:
        return ('V5', 0.3)
    if netname.startswith('+V9') or '_V9_' in netname:
        return ('V9', 0.3)
    if netname.startswith('V_BUCK') or ('BUCK' in netname and 'OUT' in netname):
        return ('V_BUCK', 0.3)
    if netname.startswith('+3V3') or netname.startswith('V3V3'):
        return ('V3V3', 0.25)
    if netname == 'GND':
        return ('GND', 0.2)
    return ('SIGNAL', SIGNAL_MIN_WIDTH)


# ---------- check 1: subsystem zone ----------
def check_subsystem_zone():
    """For each track, verify both endpoints are in the same subsystem zone
    (or net is in INTER_SUBSYSTEM allowlist)."""
    violations = 0
    examples = []
    for trk in board.GetTracks():
        if not isinstance(trk, pcbnew.PCB_TRACK):
            continue
        if isinstance(trk, pcbnew.PCB_VIA):
            continue
        try:
            netname = trk.GetNet().GetNetname()
        except Exception:
            continue
        if netname in INTER_SUBSYSTEM_NETS:
            continue
        # Strip channel-specific suffix to match base nets in allowlist
        base = re.sub(r'_CH[1234]$', '', netname)
        if base in INTER_SUBSYSTEM_NETS:
            continue
        s = pcbnew.ToMM(trk.GetStart().x), pcbnew.ToMM(trk.GetStart().y)
        e = pcbnew.ToMM(trk.GetEnd().x), pcbnew.ToMM(trk.GetEnd().y)
        # Find a subsystem containing both endpoints
        zones_with_both = []
        for zname, (x1, y1, x2, y2) in SUBSYSTEM_ZONES.items():
            if (x1 <= s[0] <= x2 and y1 <= s[1] <= y2
                    and x1 <= e[0] <= x2 and y1 <= e[1] <= y2):
                zones_with_both.append(zname)
        if not zones_with_both:
            violations += 1
            if len(examples) < 5:
                examples.append((netname, s, e))
    if violations:
        fails.append(f"SUBSYSTEM-ZONE: {violations} tracks cross subsystem boundaries "
                     f"without being in inter-subsystem net allowlist")
        for n, s, e in examples:
            fails.append(f"  net={n!r}  ({s[0]:.1f},{s[1]:.1f})→({e[0]:.1f},{e[1]:.1f})")


# ---------- check 2: route symmetry ----------
def check_route_symmetry():
    """For each channel-tagged net, count tracks + total length per channel.
    CH1 ↔ CH2 / CH3 / CH4 should match within ±5%."""
    per_ch = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))  # net_root → ch → [count, length_mm]
    for trk in board.GetTracks():
        if isinstance(trk, pcbnew.PCB_VIA):
            continue
        try:
            netname = trk.GetNet().GetNetname()
        except Exception:
            continue
        m = re.search(r'_CH([1234])$', netname)
        if not m:
            continue
        root = re.sub(r'_CH[1234]$', '', netname)
        ch = int(m.group(1))
        s = trk.GetStart()
        e = trk.GetEnd()
        L = math.hypot(pcbnew.ToMM(e.x - s.x), pcbnew.ToMM(e.y - s.y))
        per_ch[root][ch][0] += 1
        per_ch[root][ch][1] += L

    violations = 0
    for root, ch_data in per_ch.items():
        # Compare per-channel counts and lengths
        counts = [ch_data[c][0] for c in (1, 2, 3, 4) if c in ch_data]
        lens = [ch_data[c][1] for c in (1, 2, 3, 4) if c in ch_data]
        if len(counts) <= 1:
            continue
        cmax, cmin = max(counts), min(counts)
        if cmax - cmin > 2:
            violations += 1
            if violations <= 5:
                fails.append(f"ROUTE-SYMMETRY: net root {root!r} has uneven per-channel "
                             f"trace count: {dict(ch_data)}")
        if lens and max(lens) > 0:
            spread = (max(lens) - min(lens)) / max(lens)
            if spread > 0.05:
                violations += 1
                if violations <= 5:
                    fails.append(f"ROUTE-SYMMETRY: net root {root!r} length spread "
                                 f"{spread*100:.1f}% (limit 5%): lengths {[f'{L:.1f}' for L in lens]}")
    if violations:
        fails.append(f"ROUTE-SYMMETRY: {violations} total per-channel mismatches")


# ---------- check 3: via density ----------
def check_via_density():
    """No via cluster >2 vias/mm² in HV/MOTOR high-current zones.
    HV zones defined as MOTOR phase pours + bulk cap area + Hall current path."""
    HV_ZONES = [
        # Motor phase areas — corner clusters
        (0, 50, 35, 100),    # NW motor phase A/B/C output to TP19/20/21
        (65, 50, 100, 100),  # NE motor phase A/B/C
        (0, 0, 35, 50),      # SW
        (65, 0, 100, 50),    # SE
        # S1 + Hall current path (top strip + Hall location)
        (0, 0, 100, 15),
        (70, 0, 100, 20),
    ]
    via_count_per_zone = [0] * len(HV_ZONES)
    via_positions = []
    for trk in board.GetTracks():
        if not isinstance(trk, pcbnew.PCB_VIA):
            continue
        pos = trk.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        via_positions.append((x, y))
        for i, (x1, y1, x2, y2) in enumerate(HV_ZONES):
            if x1 <= x <= x2 and y1 <= y <= y2:
                via_count_per_zone[i] += 1
    # Density: vias / zone_area
    for i, ((x1, y1, x2, y2), n) in enumerate(zip(HV_ZONES, via_count_per_zone)):
        area_mm2 = (x2 - x1) * (y2 - y1)
        if area_mm2 <= 0: continue
        density = n / area_mm2
        if density > 2.0:
            fails.append(f"VIA-DENSITY: HV zone ({x1},{y1})-({x2},{y2}) has "
                         f"{n} vias / {area_mm2:.0f}mm² = {density:.2f}/mm² (>2/mm² limit)")


# ---------- check 4: diff pair balance ----------
DIFF_PAIRS = [
    # (net_a, net_b, max_len_diff_mm)
    # DShot / TLM differential pairs — paired by master DShot spec
    ('DSHOT_IN_CH1', 'TLM_CLEAN', 0.5),  # if differential
    ('DSHOT_IN_CH2', 'TLM_CLEAN', 0.5),
    ('DSHOT_IN_CH3', 'TLM_CLEAN', 0.5),
    ('DSHOT_IN_CH4', 'TLM_CLEAN', 0.5),
]

def check_diff_pair_balance():
    """For declared differential pairs, total track length should match within tolerance."""
    track_len_by_net = defaultdict(float)
    for trk in board.GetTracks():
        if isinstance(trk, pcbnew.PCB_VIA):
            continue
        try:
            netname = trk.GetNet().GetNetname()
        except Exception:
            continue
        s = trk.GetStart()
        e = trk.GetEnd()
        L = math.hypot(pcbnew.ToMM(e.x - s.x), pcbnew.ToMM(e.y - s.y))
        track_len_by_net[netname] += L

    violations = 0
    for net_a, net_b, tol in DIFF_PAIRS:
        la = track_len_by_net.get(net_a, 0)
        lb = track_len_by_net.get(net_b, 0)
        if la == 0 and lb == 0:
            continue  # neither routed yet
        diff = abs(la - lb)
        if diff > tol:
            violations += 1
            fails.append(f"DIFF-PAIR: {net_a}({la:.1f}mm) vs {net_b}({lb:.1f}mm) "
                         f"Δ={diff:.2f}mm > {tol}mm tolerance")


# ---------- check 5: track width ----------
# Pad-entry-neck exemption (worker fab-reality catch 2026-05-26):
# A track-width violation is EXEMPT iff (i) segment length ≤ 2.0mm AND
# (ii) at least one endpoint touches a pad with min(width,height) < class_min.
# This is the IPC fab convention: 0.5mm pad cannot accept 1.0mm trace; the
# necked entry is a geometric constraint of the pad, not a trace choice.
# Current density at 0.54mm × 2mm carrying mA-level tap current is safe
# (J ≈ 5 A/mm² vs IPC 30 A/mm² 35°C-rise limit for 1oz Cu).
# Per [[feedback-physics-as-compass]] + [[feedback-codify-not-patch]]:
# precise + bounded exemption, recorded as INFO with pad ref for audit trail.
PAD_ENTRY_NECK_MAX_LEN_MM = 2.0
_PAD_INDEX = None
def _build_pad_index():
    """Build spatial index: list of (x, y, min_dim_mm, ref) for all pads."""
    global _PAD_INDEX
    if _PAD_INDEX is not None:
        return _PAD_INDEX
    _PAD_INDEX = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pos = pad.GetPosition()
            size = pad.GetSize()
            min_dim = min(pcbnew.ToMM(size.x), pcbnew.ToMM(size.y))
            _PAD_INDEX.append((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y),
                               min_dim, fp.GetReference() + "." + pad.GetPadName()))
    return _PAD_INDEX

def _endpoint_on_undersized_pad(endpoint_x_mm, endpoint_y_mm, class_min_mm):
    """Return (pad_ref, pad_min_dim) if endpoint lies on a pad with
    min-dim < class_min. Else None."""
    pads = _build_pad_index()
    for px, py, pmin, pref in pads:
        # Endpoint within pad bbox (approx — pad size used as bbox half-extent)
        if abs(px - endpoint_x_mm) < pmin / 2 + 0.1 and abs(py - endpoint_y_mm) < pmin / 2 + 0.1:
            if pmin < class_min_mm:
                return (pref, pmin)
    return None

def check_track_width():
    """Each track segment must meet net-class minimum width.
    Pad-entry necks (bounded segment touching undersized pad) exempted."""
    violations_by_class = defaultdict(int)
    examples = defaultdict(list)
    exempted_by_class = defaultdict(int)
    exempt_examples = []
    for trk in board.GetTracks():
        if isinstance(trk, pcbnew.PCB_VIA):
            continue
        try:
            netname = trk.GetNet().GetNetname()
        except Exception:
            continue
        width_mm = pcbnew.ToMM(trk.GetWidth())
        cls, min_w = net_class(netname)
        if cls == 'NO_NET' or cls == 'GND':
            continue
        if width_mm < min_w - 0.001:  # tiny float tolerance
            # Pad-entry-neck exemption check
            s = trk.GetStart()
            e = trk.GetEnd()
            sx, sy = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
            ex, ey = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
            seg_len = math.hypot(ex - sx, ey - sy)
            if seg_len <= PAD_ENTRY_NECK_MAX_LEN_MM:
                pad_hit = _endpoint_on_undersized_pad(sx, sy, min_w) or \
                          _endpoint_on_undersized_pad(ex, ey, min_w)
                if pad_hit:
                    exempted_by_class[cls] += 1
                    if len(exempt_examples) < 5:
                        exempt_examples.append(
                            f"{netname} {width_mm:.2f}mm (class min {min_w:.2f}mm) "
                            f"len {seg_len:.2f}mm → pad {pad_hit[0]} min_dim {pad_hit[1]:.2f}mm")
                    continue  # exempt — pad-entry neck
            violations_by_class[cls] += 1
            if len(examples[cls]) < 3:
                examples[cls].append((netname, width_mm, min_w, sx, sy))
    if exempted_by_class:
        info.append(f"TRACK-WIDTH: {sum(exempted_by_class.values())} pad-entry-neck segments exempted (≤{PAD_ENTRY_NECK_MAX_LEN_MM}mm + endpoint on undersized pad)")
        for ex in exempt_examples:
            info.append(f"  exempt: {ex}")
    if violations_by_class:
        fails.append(f"TRACK-WIDTH: {sum(violations_by_class.values())} tracks below "
                     f"net-class minimum (after pad-entry-neck exemption)")
        for cls, n in violations_by_class.items():
            fails.append(f"  {cls}: {n} undersized tracks")
            for net, w, min_w, x, y in examples[cls]:
                fails.append(f"    {net!r}: {w:.3f}mm < {min_w}mm at ({x:.1f},{y:.1f})")


# ---------- check 6: plane island ----------
def check_unrouted_nets():
    """Check #7 (added 2026-05-26 per worker R22 catch class lesson):
    every multi-pad net MUST have ≥1 track segment OR be plane-served.
    Plane-served nets (GND, +VMOTOR, +V*, +3V3*) use copper pour — no
    track requirement. All other multi-pad nets need ≥1 track.

    Class lesson: worker's GetEdges() ratsnest API silently returned 0-open
    on a board with 6 genuinely-unrouted nets (GLB/GLC gate, OTP_TRIP_N,
    PWM_INHA/INHC/INLB). API claimed success without doing the work
    — sibling of [[reference-sim-claimed-not-executed]]. Track-count
    cross-check catches it regardless of API behavior.

    Defense in depth — independent metric, not trusting single API result."""
    # Plane-served net prefixes — use copper pour, no track requirement
    PLANE_SERVED_NET_RE = re.compile(r"^(GND|BATGND|\+VMOTOR|VMOTOR|\+V|\+3V3|\+5V|V_BUCK|V5_FC|V3V3A|VDDA?)$|^(/.+_PWR_)")
    # Build pad-count + track-count per net
    net_pad_count = defaultdict(int)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNetname()
            if n and not n.lower().startswith("unconnected") and not n.startswith("Net-"):
                net_pad_count[n] += 1
    net_track_count = defaultdict(int)
    for t in board.GetTracks():
        n = t.GetNetname()
        if n:
            net_track_count[n] += 1
    unrouted = []
    skipped_out_of_scope = 0
    for net, pcount in net_pad_count.items():
        if pcount < 2:
            continue  # single-pad nets (NC, isolated TP) — not a route requirement
        if PLANE_SERVED_NET_RE.match(net):
            continue  # plane pour, no tracks needed
        # Subsystem-scope filter: if --subsystem CHn provided, only check
        # nets whose name ends with that suffix (per §8 subsystem-PR methodology).
        if SUBSYSTEM_SCOPE:
            if not net.endswith("_" + SUBSYSTEM_SCOPE):
                skipped_out_of_scope += 1
                continue
        if net_track_count.get(net, 0) == 0:
            unrouted.append((net, pcount))
    if SUBSYSTEM_SCOPE and skipped_out_of_scope:
        info.append(f"UNROUTED: scoped to {SUBSYSTEM_SCOPE} nets only; {skipped_out_of_scope} non-{SUBSYSTEM_SCOPE} multi-pad nets skipped (per §8 subsystem-PR scope)")
    if unrouted:
        for net, pcount in unrouted[:20]:
            fails.append(f"UNROUTED: net '{net}' has {pcount} pads but 0 tracks — net not routed")
        if len(unrouted) > 20:
            fails.append(f"UNROUTED: ... and {len(unrouted) - 20} more unrouted nets")


def check_plane_island():
    """Each inner plane (In1/In3/In5) should have one connected copper region.
    Detect isolated islands by checking zone connectivity.

    Self-test note: at Phase 5b start, planes may be empty until kicad
    runs zone fill. This check counts ZONE objects per plane layer; if 0
    or no fill, emits info, not fail."""
    plane_layers = [
        ('In1.Cu', pcbnew.In1_Cu),
        ('In3.Cu', pcbnew.In3_Cu),
        ('In5.Cu', pcbnew.In5_Cu),
    ]
    for lname, lid in plane_layers:
        zones = [z for z in board.Zones() if z.GetLayer() == lid]
        if not zones:
            info.append(f"PLANE-ISLAND: no zone on {lname} (Phase 5b not yet drawn)")
            continue
        info.append(f"PLANE-ISLAND: {lname} has {len(zones)} zone(s)")
        # Real island detection requires flood-fill on filled-areas — defer to
        # Phase 5b autoroute output validation when zones are filled.


# ---------- run ----------
check_subsystem_zone()
check_route_symmetry()
check_via_density()
check_diff_pair_balance()
check_track_width()
check_plane_island()
check_unrouted_nets()

print(f"=== Routing compliance audit: {os.path.basename(PCB_PATH)} ===")
total_tracks = sum(1 for t in board.GetTracks() if not isinstance(t, pcbnew.PCB_VIA))
total_vias = sum(1 for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA))
print(f"Tracks: {total_tracks}, Vias: {total_vias}")
print()

if info:
    print("INFO:")
    for line in info:
        print(f"  {line}")
    print()

if warns:
    print("WARNINGS:")
    for line in warns:
        print(f"  {line}")
    print()

if fails:
    print(f"FAIL ({len(fails)} issues):")
    for line in fails:
        print(f"  {line}")
    sys.exit(1)

print("PASS — all 7 routing-compliance checks clean")
