"""Phase 4b-redo4-R1 — center-cluster placement.

R1 architecture (master Task #38 dispatch 2026-05-22):
  - 4 MCUs in 2×2 center cluster
  - Per-channel passives radiate OUTWARD from MCU toward board edges
  - MOSFETs on B.Cu under MCU's quadrant
  - Motor pads on outer edges (per channel's quadrant)
  - BEC + battery + Hall sensor + supervisor + AUX header in the
    non-channel zones (top edge band + cluster gaps)

Board: 100×85 mm, 8L stackup (Phase 4a-restack-8L).
Total footprints: ~581 (some Phase 3-redo components skipped by kinet2pcb
due to footprint library gaps — CP_Elec_10x16.5, TO-220-5_Vertical).

KiCad screen convention: +Y is DOWN.

Per-channel quadrant ownership (KiCad screen):
  CH1 → NW (top-left)    MCU @ (40, 35)
  CH2 → NE (top-right)   MCU @ (60, 35)
  CH3 → SW (bottom-left) MCU @ (40, 50)
  CH4 → SE (bottom-right) MCU @ (60, 50)
"""

import re
from pathlib import Path
from collections import defaultdict

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
BOARD_W = 100.0
BOARD_H = 85.0
CLUSTER_CX = 50.0
CLUSTER_CY = 42.5

# ─── R1 center cluster: 4 MCUs in 2×2 ───
CHANNEL_MCU_POS = {
    1: (40.0, 35.0),  # CH1 NW
    2: (60.0, 35.0),  # CH2 NE
    3: (40.0, 50.0),  # CH3 SW
    4: (60.0, 50.0),  # CH4 SE
}
# Channel quadrant labels for diagnostics
CHANNEL_LABEL = {1: 'NW', 2: 'NE', 3: 'SW', 4: 'SE'}
# Outward direction for each channel (from cluster center)
CHANNEL_OUTWARD = {
    1: (-1, -1),  # NW: -X-Y
    2: ( 1, -1),  # NE: +X-Y
    3: (-1,  1),  # SW: -X+Y
    4: ( 1,  1),  # SE: +X+Y
}
# R1 architecture: MCU rotation puts PWM corner facing OUTWARD (away from cluster)
# so per-channel passives radiate outward. PWM corner = chip's SE in chip frame.
# To face NW (CH1), rotate 180°; NE (CH2) → 270°; SW (CH3) → 90°; SE (CH4) → 0°.
CHANNEL_MCU_ROTATION = {1: 180, 2: 270, 3: 90, 4: 0}

# Channel passive zones — outward of each MCU, with 30×30mm pack area:
#   NW: x=5..38, y=5..32   (lower-right corner anchors near MCU1)
#   NE: x=62..95, y=5..32  (lower-left corner near MCU2)
#   SW: x=5..38, y=53..80  (upper-right corner near MCU3)
#   SE: x=62..95, y=53..80 (upper-left corner near MCU4)
CHANNEL_PACK_ZONE = {
    1: {'x0':  5.0, 'x1': 38.0, 'y0':  5.0, 'y1': 32.0},
    2: {'x0': 62.0, 'x1': 95.0, 'y0':  5.0, 'y1': 32.0},
    3: {'x0':  5.0, 'x1': 38.0, 'y0': 53.0, 'y1': 80.0},
    4: {'x0': 62.0, 'x1': 95.0, 'y0': 53.0, 'y1': 80.0},
}
# Densely-packed sub-grid for per-channel passives (1.4mm pitch).
# Each zone is 33×27 mm = ~23 cols × 19 rows = ~437 cells. Adequate
# for the ~120 per-channel passives expected.
PASSIVE_PITCH_MM = 1.4

# ─── Per-channel MOSFETs (B.Cu, 24 total = 6 per channel) ───
# 6×4 grid centered under the MCU cluster — heatsink zone covers it.
# Each channel's 6 FETs in a 3×2 sub-grid:
#   CH1 → upper-left (cols 0-2, rows 0-1)
#   CH2 → upper-right (cols 3-5, rows 0-1)
#   CH3 → lower-left (cols 0-2, rows 2-3)
#   CH4 → lower-right (cols 3-5, rows 2-3)
MOSFET_GRID = {
    'cols': 6, 'rows': 4,
    'cell_w': 7.0,                 # narrower cell so 6 cols fit central 42mm
    'cell_h': 7.5,                 # 4 rows × 7.5 = 30mm vertical
    'origin_x': 29.0,              # 50 - 42/2 = 29
    'origin_y': 27.5,              # 42.5 - 30/2 = 27.5
}
CH_TO_MOSFET_SUBGRID = {
    1: (0, 0), 2: (3, 0), 3: (0, 2), 4: (3, 2),
}

# ─── Per-channel motor solder pads (on outer edges of each quadrant) ───
# Each channel's 3 phase pads (A/B/C) on its corresponding board edge.
MOTOR_PADS = {
    (1, 'A'): (10.0, 2.0),  (1, 'B'): (15.0, 2.0),  (1, 'C'): (20.0, 2.0),   # CH1 top edge (low Y)
    (2, 'A'): (80.0, 2.0),  (2, 'B'): (85.0, 2.0),  (2, 'C'): (90.0, 2.0),   # CH2 top edge (low Y)
    (3, 'A'): (10.0, 83.0), (3, 'B'): (15.0, 83.0), (3, 'C'): (20.0, 83.0),  # CH3 bottom edge (high Y)
    (4, 'A'): (80.0, 83.0), (4, 'B'): (85.0, 83.0), (4, 'C'): (90.0, 83.0),  # CH4 bottom edge
}

# ─── SWD test pads (per channel, 2 each) ───
SWD_PADS = {
    (1, 'SWDIO'): (2.0, 10.0),  (1, 'SWCLK'): (2.0, 14.0),
    (2, 'SWDIO'): (98.0, 10.0), (2, 'SWCLK'): (98.0, 14.0),
    (3, 'SWDIO'): (2.0, 75.0),  (3, 'SWCLK'): (2.0, 79.0),
    (4, 'SWDIO'): (98.0, 75.0), (4, 'SWCLK'): (98.0, 79.0),
}

# ─── Top-edge battery section ───
BATT_PAD_POS = (5.0, 42.5)         # left edge, centered vertically (XT30 entry)
BULK_POS = [(12.0, 42.5), (12.0, 39.0), (12.0, 46.0), (15.0, 42.5)]  # 4× polymer caps near batt
RP_FET_POSITIONS = [(20.0, 39.0), (20.0, 41.5), (20.0, 44.0), (20.0, 46.5)]  # 4× RP FETs in column
TVS_POS = (24.0, 42.5)
NTC_BATT_POS = [(28.0, 40.0), (28.0, 45.0)]  # 2× MF72 5D25 in parallel

# ─── Bus-current Hall sensor (ACS770ECB-200B) — between batt section and FET cluster ───
HALL_POS = (32.0, 42.5)            # right of NTC, before MOSFET cluster
HALL_FILTER_POS = (35.0, 42.5)
HALL_DIVIDER_POS = (35.0, 39.0)

# ─── VMOTOR supervisor (TPS3700) ───
TPS3700_POS = (50.0, 12.0)
VMOTOR_DIV_POS = [(47.0, 8.0), (53.0, 8.0)]  # divider resistors

# ─── FC connector + ESD + AUX header (top edge) ───
FC_POS = (70.0, 82.0)
ESD_POS = [(60.0, 80.0), (65.0, 80.0), (75.0, 80.0)]
AUX_POS = (45.0, 82.0)             # JST SH BM06B-SRSS-TB

# ─── BEC strip (BEC bucks + safety + LDO) — bottom edge band, away from cluster ───
# Distributes the 5 buck columns across the bottom edge band y=72..82.
BEC_BUCK_POSITIONS = {
    1: (8.0,  68.0),   # V5_FC buck — left edge
    2: (8.0,  72.0),   # V5_PI5 buck
    3: (8.0,  76.0),   # V5_AI buck
    4: (92.0, 68.0),   # V9_VTX1 buck — right edge
    5: (92.0, 72.0),   # V9_VTX2 buck
}
LDO_POS = (92.0, 76.0)              # +V3V3 LDO
SUPERVISOR_POS = (8.0, 80.0)         # V5_PI5 voltage supervisor

# BEC solder pads — distributed on left/right edges (cleared center for channels)
BEC_PAD_POS = {
    'V5_FC_PLUS':  (3.0, 19.0),  'V5_FC_GND':   (3.0, 22.0),
    'V5_PI5_PLUS': (3.0, 28.0),  'V5_PI5_GND':  (3.0, 31.0),
    'V5_AI_PLUS':  (3.0, 37.0),  'V5_AI_GND':   (3.0, 40.0),
    'V9_VTX1_PLUS': (97.0, 19.0),'V9_VTX1_GND':  (97.0, 22.0),
    'V9_VTX2_PLUS': (97.0, 28.0),'V9_VTX2_GND':  (97.0, 31.0),
    'V3V3_PLUS':   (97.0, 37.0), 'V3V3_GND':    (97.0, 40.0),
    'GND_DIST_1':  (97.0, 46.0), 'GND_DIST_2':  (97.0, 49.0),
    'GND_DIST_3':  (3.0, 46.0),  'GND_DIST_4':  (3.0, 49.0),
}

# ─── Indicator LEDs ───
LED_PG_POS = (50.0, 8.0)            # power-good (V3V3 on)
LED_PWR_POS = (50.0, 15.0)          # battery present
LED_RPOL_POS = (50.0, 18.0)         # reverse-pol warning

# Per-channel firmware-status LEDs (PA11-driven, 4× RED_KILL_FW)
LED_STATUS_POS = {
    1: (32.0, 33.0),  2: (68.0, 33.0),
    3: (32.0, 52.0),  4: (68.0, 52.0),
}
# Per-channel HW protection-fault LEDs (kill_local_n driven, 4× RED_FAULT_HW)
LED_FAULT_HW_POS = {
    1: (32.0, 37.0),  2: (68.0, 37.0),
    3: (32.0, 48.0),  4: (68.0, 48.0),
}

# ─── Gate driver positions (between MCU and MOSFET cluster) ───
DRIVER_POS = {
    1: (40.0, 30.0),  2: (60.0, 30.0),
    3: (40.0, 55.0),  4: (60.0, 55.0),
}

# ─── CSAs (12 total, 3 per channel) — near MCU adc input pins ───
CSA_POS_PER_CH = {
    1: [(36.0, 32.0), (38.0, 32.0), (40.0, 32.0)],
    2: [(60.0, 32.0), (62.0, 32.0), (64.0, 32.0)],
    3: [(36.0, 53.0), (38.0, 53.0), (40.0, 53.0)],
    4: [(60.0, 53.0), (62.0, 53.0), (64.0, 53.0)],
}

# ─── Shunts (12 total, 3 per channel) — adjacent to MOSFETs on B.Cu ───
SHUNT_POS_PER_CH = {
    1: [(30.0, 26.0), (35.0, 26.0), (40.0, 26.0)],
    2: [(50.0, 26.0), (55.0, 26.0), (60.0, 26.0)],
    3: [(30.0, 60.0), (35.0, 60.0), (40.0, 60.0)],
    4: [(50.0, 60.0), (55.0, 60.0), (60.0, 60.0)],
}

# ─── Per-channel TL431 + LM393 + 74LVC1G08 (Phase 3-redo protection ICs) ───
# Position adjacent to MCU in its quadrant
PROTECTION_IC_POS = {
    # (TL431, LM393, 74LVC1G08) per channel
    1: [(35.0, 38.0), (33.0, 36.0), (33.0, 33.0)],
    2: [(65.0, 38.0), (67.0, 36.0), (67.0, 33.0)],
    3: [(35.0, 47.0), (33.0, 49.0), (33.0, 52.0)],
    4: [(65.0, 47.0), (67.0, 49.0), (67.0, 52.0)],
}

# ─── Manufacturing fiducials (3 corner fiducials) ───
FIDUCIAL_POS = [(3.0, 3.0), (97.0, 3.0), (3.0, 82.0)]

# Pogo-pin programming pads (B.Cu, one per MCU)
POGO_PADS_POS = {
    1: (15.0, 35.0),  2: (85.0, 35.0),
    3: (15.0, 50.0),  4: (85.0, 50.0),
}

# ────────────────────────────────────────────────────────────────────
# Footprint parser + categorize helpers
# ────────────────────────────────────────────────────────────────────


def parse_footprints(pcb_text):
    results = []
    pos = 0
    while True:
        idx = pcb_text.find("\n\t(footprint ", pos)
        if idx < 0:
            break
        start = idx + 1
        depth = 0
        end = start
        for i, c in enumerate(pcb_text[start:], start):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        block = pcb_text[start:end]
        lib_m = re.search(r'\(footprint "([^"]+)"', block)
        ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
        val_m = re.search(r'\(property "Value" "([^"]+)"', block)
        layer_m = re.search(r'\(layer "([^"]+)"\)', block)
        at_m = re.search(r'\(at ([0-9.\-]+) ([0-9.\-]+)(?: ([0-9.\-]+))?\)', block)
        results.append({
            'start': start, 'end': end, 'block': block,
            'lib': lib_m.group(1) if lib_m else None,
            'ref': ref_m.group(1) if ref_m else '?',
            'value': val_m.group(1) if val_m else '?',
            'layer': layer_m.group(1) if layer_m else '?',
            'x': float(at_m.group(1)) if at_m else 0.0,
            'y': float(at_m.group(2)) if at_m else 0.0,
            'rot': float(at_m.group(3)) if at_m and at_m.group(3) else 0.0,
        })
        pos = end
    return results


def categorize(fp):
    val = fp['value']
    ref = fp['ref']
    lib = fp['lib'] or ''
    if 'MountingHole' in lib:
        return ('mount_hole', None)
    if 'AOTL66912' in val:
        return ('phase_fet', ref)
    if 'AON6260' in val and ref in ('Q1', 'Q2', 'Q3', 'Q4'):
        return ('rp_fet', int(ref[1:]))
    if 'BSC014N06NS' in val or 'C113391' in val:
        return ('rp_fet', ref)
    if val == '0.2mR':
        return ('shunt', ref)
    if '470uF' in val or 'EEHZS1V471P' in val:
        return ('bulk_cap', ref)
    if val == 'SMBJ33A':
        return ('tvs', ref)
    if 'BATT_PAD' in val:
        return ('batt_pad', ref)
    if 'AT32F421' in val:
        return ('mcu', ref)
    if 'DRV8300' in val:
        return ('driver', ref)
    if 'INA186' in val:
        return ('csa', ref)
    if 'TPS54560' in val:
        return ('bec_buck_5v', ref)
    if 'AOZ1284' in val:
        return ('bec_buck_9v', ref)
    if 'TLV76733' in val:
        return ('ldo', ref)
    if val == 'SS54':
        return ('bec_schottky', ref)
    if 'TPS259251' in val:
        return ('bec_efuse', ref)
    if val == 'MF-MSMF200':
        return ('bec_polyfuse', ref)
    if val == 'SMAJ5.0A' or val == 'SMAJ9.0A':
        return ('bec_tvs', ref)
    if val == '600ohm@100MHz':
        return ('bec_ferrite', ref)
    if val.startswith('100uF_') or val == '100uF':
        return ('bec_polymer_cap', ref)
    if val == 'MF72_5D25':
        return ('ntc_icl', ref)
    if 'TPS3700' in val:
        return ('supervisor', ref)
    if val.startswith('TL431'):
        return ('tl431', ref)
    if val == 'LM393':
        return ('lm393', ref)
    if val == '74LVC1G08':
        return ('logic_and', ref)
    if val == 'BZT52C5V6':
        return ('zener_gate', ref)
    if val == 'BAT54':
        return ('schottky_small', ref)
    if 'ACS770' in val:
        return ('hall_sensor', ref)
    if val == 'SM08B-SRSS-TB' or 'SM08B-SRSS' in val:
        return ('fc_connector', ref)
    if 'BM06B-SRSS' in val:
        return ('aux_header', ref)
    if 'USBLC6' in val:
        return ('esd', ref)
    if val == 'GREEN':
        return ('led_pg', ref)
    if val == 'RED':
        # Per-channel status LED (inside channel sub-circuit) — placed in channel zone via membership
        return ('led_channel_red', ref)
    if val == 'GREEN_PWR':
        return ('led_pwr', ref)
    if val == 'RED_RPOL':
        return ('led_rpol', ref)
    if val == 'RED_KILL_FW':
        return ('led_status_fw', ref)
    if val == 'RED_FAULT_HW':
        return ('led_fault_hw', ref)
    if val.startswith('VSUP') or val == 'APX803':
        return ('bec_supervisor', ref)
    if val.startswith('PAD_'):
        return ('bec_pad', val)
    if val.startswith('BOOT_JUMPER') or val.startswith('BOOT_3V'):
        return ('boot_pad', ref)
    motor_m = re.match(r'MOTOR_([ABC])_CH([1-4])', val)
    if motor_m:
        return ('motor_pad', (int(motor_m.group(2)), motor_m.group(1)))
    swd_m = re.match(r'(SWDIO|SWCLK)_CH([1-4])', val)
    if swd_m:
        return ('swd_pad', (int(swd_m.group(2)), swd_m.group(1)))
    return ('passive', ref)


def parse_net_channel_membership(pcb_text):
    """Return a dict ref → channel(1-4) by analyzing which CHn nets each
    component pin connects to. A component whose pads connect to 'X_CHn'
    nets is assigned to channel n.

    Reads the .net file (S-expression netlist) — kinet2pcb output kicad_pcb
    files do NOT include per-pad net assignments, so we go to the source.
    """
    net_file = PCB.with_suffix('.net')
    if not net_file.exists():
        print(f"WARNING: {net_file} not found — channel membership inference will be empty")
        return {}
    txt = net_file.read_text()

    # Walk (net (code N) (name "NAME") (node (ref "REFA") (pin "X"))* ) blocks.
    result = defaultdict(lambda: defaultdict(int))  # ref → {ch → vote_count}
    # Simpler form: find each net's name + each (ref "X") child.
    # Net block starts with (net (code N) (name "NAME")) ... ends at depth-balanced ).
    pos = 0
    net_block_pat = re.compile(r'\(net\s+\(code (\d+)\)\s+\(name "([^"]+)"\)')
    for m in net_block_pat.finditer(txt):
        name = m.group(2)
        ch_match = re.search(r'_CH([1-4])', name)
        if not ch_match:
            continue
        ch = int(ch_match.group(1))
        # Walk forward from this net block, collecting (node (ref "REF")) until
        # balanced paren returns. Simple bracket-counting from m.start().
        i = m.end()
        depth = 1  # we opened on (net
        while i < len(txt) and depth > 0:
            if txt[i] == '(':
                depth += 1
            elif txt[i] == ')':
                depth -= 1
            i += 1
        net_block_end = i
        # Find all (ref "X") within this block
        for ref_m in re.finditer(r'\(ref "([^"]+)"\)', txt[m.start():net_block_end]):
            ref = ref_m.group(1)
            result[ref][ch] += 1
    # Reduce: pick the channel with the most votes per ref
    final = {}
    for ref, votes in result.items():
        best_ch = max(votes.items(), key=lambda kv: kv[1])[0]
        final[ref] = best_ch
    return final


def pack_grid_iter(zone, pitch, exclusion_set=None, exclusion_radius=1.5):
    """Yield (x, y) positions for a pack-zone, scanning rows then columns.
    Skip any cell within `exclusion_radius` mm of points in `exclusion_set`.
    """
    x0, x1 = zone['x0'], zone['x1']
    y0, y1 = zone['y0'], zone['y1']
    n_cols = max(1, int((x1 - x0) / pitch) + 1)
    n_rows = max(1, int((y1 - y0) / pitch) + 1)
    for row in range(n_rows):
        for col in range(n_cols):
            cx, cy = x0 + col * pitch, y0 + row * pitch
            if exclusion_set:
                blocked = False
                for ex, ey in exclusion_set:
                    if abs(cx - ex) < exclusion_radius and abs(cy - ey) < exclusion_radius:
                        blocked = True
                        break
                if blocked:
                    continue
            yield (cx, cy)


def get_f_cu_occupied_positions(placements):
    """Return set of (x, y) tuples for F.Cu placements (used as exclusion set
    for the per-channel passive packer)."""
    return {(p[0], p[1]) for p in placements.values() if p[2] == 'F.Cu'}


def dedup_mount_holes(txt):
    mh_blocks = []
    pos = 0
    while True:
        idx = txt.find('\n\t(footprint "MountingHole:', pos)
        if idx < 0:
            break
        start = idx + 1
        depth = 0
        end = start
        for i, c in enumerate(txt[start:], start):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        mh_blocks.append((idx, end))
        pos = end
    if len(mh_blocks) <= 4:
        return txt, 0
    deleted = 0
    for idx, end in reversed(mh_blocks[4:]):
        txt = txt[:idx] + txt[end:]
        deleted += 1
    return txt, deleted


def main():
    txt = PCB.read_text()
    txt, mh_deleted = dedup_mount_holes(txt)
    if mh_deleted:
        print(f"Pre-processing: removed {mh_deleted} duplicate mount holes")

    fps = parse_footprints(txt)
    print(f"Parsed {len(fps)} footprints")

    ch_membership = parse_net_channel_membership(txt)
    print(f"Per-channel membership inferred for {len(ch_membership)} parts (from net suffix _CHn)")

    groups = defaultdict(list)
    for fp in fps:
        cat, key = categorize(fp)
        groups[cat].append((fp, key))
    print("\nFootprints by category:")
    for cat, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"  {cat:20s} {len(items)}")

    placements = {}

    # 1) MCUs (4×, center cluster) — assign by net membership
    mcus_by_ch = defaultdict(list)
    for fp, _ in groups.get('mcu', []):
        ch = ch_membership.get(fp['ref'])
        if ch in (1, 2, 3, 4):
            mcus_by_ch[ch].append(fp)
    for ch in (1, 2, 3, 4):
        if mcus_by_ch[ch]:
            fp = mcus_by_ch[ch][0]
            x, y = CHANNEL_MCU_POS[ch]
            rot = CHANNEL_MCU_ROTATION[ch]
            placements[fp['ref']] = (x, y, 'F.Cu', rot)

    # 2) Gate drivers (4×) — by net membership
    drivers_by_ch = defaultdict(list)
    for fp, _ in groups.get('driver', []):
        ch = ch_membership.get(fp['ref'])
        if ch in (1, 2, 3, 4):
            drivers_by_ch[ch].append(fp)
    for ch in (1, 2, 3, 4):
        if drivers_by_ch[ch]:
            fp = drivers_by_ch[ch][0]
            x, y = DRIVER_POS[ch]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 3) Phase MOSFETs (24 = 6×4 grid, B.Cu) — by net membership + sub-grid
    g = MOSFET_GRID
    fets_by_ch = defaultdict(list)
    for fp, _ in groups.get('phase_fet', []):
        ch = ch_membership.get(fp['ref'])
        if ch in (1, 2, 3, 4):
            fets_by_ch[ch].append(fp)
    for ch in (1, 2, 3, 4):
        for idx_in_ch, fp in enumerate(fets_by_ch[ch][:6]):
            col0, row0 = CH_TO_MOSFET_SUBGRID[ch]
            sub_col = idx_in_ch % 3
            sub_row = idx_in_ch // 3
            col = col0 + sub_col
            row = row0 + sub_row
            x = g['origin_x'] + col * g['cell_w']
            y = g['origin_y'] + row * g['cell_h']
            placements[fp['ref']] = (x, y, 'B.Cu', 0.0)

    # 4) Reverse-pol FETs (4×, B.Cu, top edge column)
    for i, (fp, _) in enumerate(groups.get('rp_fet', [])[:4]):
        x, y = RP_FET_POSITIONS[i]
        placements[fp['ref']] = (x, y, 'B.Cu', 0.0)

    # 5) Bulk caps (4× polymer, B.Cu, near batt section)
    for i, (fp, _) in enumerate(groups.get('bulk_cap', [])[:4]):
        x, y = BULK_POS[i]
        placements[fp['ref']] = (x, y, 'B.Cu', 0.0)

    # 6) TVS — split by footprint: D_SMB = battery section (1×, near batt pad);
    # D_SMA = phase TVS (12×, motor-pad-adjacent per master ≤3mm spec).
    batt_tvs = [fp for fp, _ in groups.get('tvs', []) if 'D_SMB' in (fp['lib'] or '')]
    phase_tvs_all = [fp for fp, _ in groups.get('tvs', []) if 'D_SMA' in (fp['lib'] or '')]
    for fp in batt_tvs[:1]:
        placements[fp['ref']] = (TVS_POS[0], TVS_POS[1], 'B.Cu', 0.0)
    # Phase TVS placement via net-membership inference (per channel × 3 phases)
    smbj_extras = [(fp, None) for fp in phase_tvs_all]
    # Sort by inferred channel for deterministic per-channel grouping
    smbj_by_ch = defaultdict(list)
    for fp, _ in smbj_extras:
        ch = ch_membership.get(fp['ref'])
        if ch in (1, 2, 3, 4):
            smbj_by_ch[ch].append(fp)
    for ch in (1, 2, 3, 4):
        ch_tvs = smbj_by_ch[ch][:3]
        for phase_idx, fp in enumerate(ch_tvs):
            phase = ('A', 'B', 'C')[phase_idx]
            if (ch, phase) in MOTOR_PADS:
                mx, my = MOTOR_PADS[(ch, phase)]
                dx, dy = CHANNEL_OUTWARD[ch]
                # 3 mm inward from motor pad (away from edge)
                tvs_x = mx
                tvs_y = my - dy * 3.0
                placements[fp['ref']] = (tvs_x, tvs_y, 'F.Cu', 0.0)

    # 7) Battery pad
    for fp, _ in groups.get('batt_pad', [])[:1]:
        placements[fp['ref']] = (BATT_PAD_POS[0], BATT_PAD_POS[1], 'B.Cu', 0.0)

    # 8) Shunts (12, 3 per channel, B.Cu) — by net membership
    shunts_by_ch = defaultdict(list)
    for fp, _ in groups.get('shunt', []):
        ch = ch_membership.get(fp['ref'])
        if ch in (1, 2, 3, 4):
            shunts_by_ch[ch].append(fp)
    for ch in (1, 2, 3, 4):
        for idx, fp in enumerate(shunts_by_ch[ch][:3]):
            x, y = SHUNT_POS_PER_CH[ch][idx]
            placements[fp['ref']] = (x, y, 'B.Cu', 0.0)

    # 9) CSAs (12, 3 per channel, F.Cu near MCU) — by net membership
    csas_by_ch = defaultdict(list)
    for fp, _ in groups.get('csa', []):
        ch = ch_membership.get(fp['ref'])
        if ch in (1, 2, 3, 4):
            csas_by_ch[ch].append(fp)
    for ch in (1, 2, 3, 4):
        for idx, fp in enumerate(csas_by_ch[ch][:3]):
            x, y = CSA_POS_PER_CH[ch][idx]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 10) Phase 3-redo protection ICs per channel — TL431 + LM393 + 74LVC1G08
    # Use ch_membership inference (not sequential index) since SKiDL reference
    # assignment doesn't necessarily preserve make_channel call order.
    for cat, idx_in_set in [('tl431', 0), ('lm393', 1), ('logic_and', 2)]:
        for fp, _ in groups.get(cat, []):
            ch = ch_membership.get(fp['ref'])
            if ch in (1, 2, 3, 4):
                x, y = PROTECTION_IC_POS[ch][idx_in_set]
                placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 11) Hall sensor (ACS770ECB-200B) + filter cap + divider
    for fp, _ in groups.get('hall_sensor', [])[:1]:
        placements[fp['ref']] = (HALL_POS[0], HALL_POS[1], 'F.Cu', 0.0)

    # 12) Supervisor IC (TPS3700)
    for fp, _ in groups.get('supervisor', [])[:1]:
        placements[fp['ref']] = (TPS3700_POS[0], TPS3700_POS[1], 'F.Cu', 0.0)

    # 13) FC connector
    for fp, _ in groups.get('fc_connector', [])[:1]:
        placements[fp['ref']] = (FC_POS[0], FC_POS[1], 'F.Cu', 0.0)
    # AUX header
    for fp, _ in groups.get('aux_header', [])[:1]:
        placements[fp['ref']] = (AUX_POS[0], AUX_POS[1], 'F.Cu', 0.0)

    # 14) ESD arrays
    for i, (fp, _) in enumerate(groups.get('esd', [])[:3]):
        x, y = ESD_POS[i]
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 15) BEC bucks (5×)
    bec_5v = [fp for fp, _ in groups.get('bec_buck_5v', [])]
    bec_9v = [fp for fp, _ in groups.get('bec_buck_9v', [])]
    all_bucks = bec_5v[:3] + bec_9v[:2]
    for col_idx, fp in enumerate(all_bucks, start=1):
        if col_idx in BEC_BUCK_POSITIONS:
            x, y = BEC_BUCK_POSITIONS[col_idx]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # LDO
    for fp, _ in groups.get('ldo', [])[:1]:
        placements[fp['ref']] = (LDO_POS[0], LDO_POS[1], 'F.Cu', 0.0)
    # BEC support: schottky, efuse, polyfuse, TVS, ferrite, polymer caps —
    # pack into available bottom-edge band (y=63..82, away from channels)
    bec_support_zone = {'x0': 25.0, 'x1': 80.0, 'y0': 63.0, 'y1': 70.0}
    bec_packer = pack_grid_iter(bec_support_zone, PASSIVE_PITCH_MM)
    for cat in ('bec_schottky', 'bec_efuse', 'bec_polyfuse', 'bec_tvs',
                'bec_ferrite', 'bec_polymer_cap', 'bec_supervisor'):
        for fp, _ in groups.get(cat, []):
            x, y = next(bec_packer)
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 16) NTCs (2× MF72 5D25 in parallel, battery section)
    for i, (fp, _) in enumerate(groups.get('ntc_icl', [])[:2]):
        x, y = NTC_BATT_POS[i]
        placements[fp['ref']] = (x, y, 'B.Cu', 0.0)

    # 17) Indicator LEDs
    for fp, _ in groups.get('led_pg', [])[:1]:
        placements[fp['ref']] = (LED_PG_POS[0], LED_PG_POS[1], 'F.Cu', 0.0)
    for fp, _ in groups.get('led_pwr', [])[:1]:
        placements[fp['ref']] = (LED_PWR_POS[0], LED_PWR_POS[1], 'F.Cu', 0.0)
    for fp, _ in groups.get('led_rpol', [])[:1]:
        placements[fp['ref']] = (LED_RPOL_POS[0], LED_RPOL_POS[1], 'F.Cu', 0.0)
    # 4× firmware status LEDs (RED_KILL_FW) — by ch_membership
    for fp, _ in groups.get('led_status_fw', []):
        ch = ch_membership.get(fp['ref'])
        if ch in (1, 2, 3, 4):
            x, y = LED_STATUS_POS[ch]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)
    # 4× HW protection-fault LEDs (RED_FAULT_HW) — by ch_membership
    for fp, _ in groups.get('led_fault_hw', []):
        ch = ch_membership.get(fp['ref'])
        if ch in (1, 2, 3, 4):
            x, y = LED_FAULT_HW_POS[ch]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 18) Motor pads (12×, F.Cu, board edges)
    for fp, key in groups.get('motor_pad', []):
        if key in MOTOR_PADS:
            x, y = MOTOR_PADS[key]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 19) SWD pads (8×, F.Cu, side edges per channel)
    for fp, key in groups.get('swd_pad', []):
        if key in SWD_PADS:
            x, y = SWD_PADS[key]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 20) BEC solder pads
    for fp, key in groups.get('bec_pad', []):
        pad_key = key.replace('PAD_', '', 1)
        if pad_key in BEC_PAD_POS:
            x, y = BEC_PAD_POS[pad_key]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 21) Boot testpoints (2 per channel × 4 channels) — channel extracted
    # from VALUE string (e.g. "BOOT_3V_CH1" → CH1). Net-membership unreliable
    # because BOOT_3V_CHn touches +V3V3 (no _CHn net suffix).
    boot_by_ch = defaultdict(list)
    for fp, _ in groups.get('boot_pad', []):
        m = re.search(r'_CH([1-4])', fp['value'] or '')
        if m:
            boot_by_ch[int(m.group(1))].append(fp)
    for ch in (1, 2, 3, 4):
        mx, my = CHANNEL_MCU_POS[ch]
        dx, dy = CHANNEL_OUTWARD[ch]
        for j, fp in enumerate(boot_by_ch[ch][:2]):
            bx = mx + dx * 6.0
            by = my + dy * (6.0 + j * 2.5)
            placements[fp['ref']] = (bx, by, 'F.Cu', 0.0)

    # 22) Per-channel passives (everything categorized as 'passive') — pack
    # into each channel's outward quadrant zone. Use net-membership inference
    # to assign each passive to its channel; fallback to round-robin if
    # membership unknown.
    passives = [fp for fp, _ in groups.get('passive', [])]
    passives_unplaced = [fp for fp in passives if fp['ref'] not in placements]

    # Group passives by inferred channel
    by_ch = defaultdict(list)
    no_ch = []
    for fp in passives_unplaced:
        ch = ch_membership.get(fp['ref'])
        if ch in (1, 2, 3, 4):
            by_ch[ch].append(fp)
        else:
            no_ch.append(fp)
    print(f"Passive distribution by inferred channel: "
          f"CH1={len(by_ch[1])}, CH2={len(by_ch[2])}, CH3={len(by_ch[3])}, "
          f"CH4={len(by_ch[4])}, main/unknown={len(no_ch)}")

    # Build a single combined queue: per-channel passives + zener_gate +
    # schottky_small + led_channel_red, grouped by inferred channel; main/unknown
    # routed to BEC support zone.
    for cat in ('zener_gate', 'schottky_small', 'led_channel_red'):
        for fp, _ in groups.get(cat, []):
            if fp['ref'] in placements:
                continue
            ch = ch_membership.get(fp['ref'])
            if ch in (1, 2, 3, 4):
                by_ch[ch].append(fp)
            else:
                no_ch.append(fp)

    # Pack per-channel passives into channel zone, skipping cells near ICs.
    # Exclusion set is the SNAPSHOT before packing — packed passives are at
    # pitch 1.4mm so adjacency is intrinsic; don't expand exclusion as we go.
    # Use exclusion_radius = 2.5mm (large enough to clear IC pads + 1mm margin).
    occupied_f_cu_snapshot = get_f_cu_occupied_positions(placements)
    for ch in (1, 2, 3, 4):
        zone = CHANNEL_PACK_ZONE[ch]
        packer = pack_grid_iter(zone, PASSIVE_PITCH_MM,
                                exclusion_set=occupied_f_cu_snapshot,
                                exclusion_radius=2.5)
        for fp in by_ch[ch]:
            try:
                x, y = next(packer)
            except StopIteration:
                print(f"WARNING: pack zone CH{ch} exhausted; ref {fp['ref']} overflow")
                break
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # Main / unknown passives → pack into bottom-edge BEC support zone
    main_zone = {'x0': 25.0, 'x1': 80.0, 'y0': 70.0, 'y1': 80.0}
    main_packer = pack_grid_iter(main_zone, PASSIVE_PITCH_MM,
                                 exclusion_set=occupied_f_cu_snapshot,
                                 exclusion_radius=2.5)
    for fp in no_ch:
        try:
            x, y = next(main_packer)
        except StopIteration:
            print(f"WARNING: main pack zone exhausted; ref {fp['ref']} overflow")
            break
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # Apply placements: rewrite each footprint block
    replacements = []
    for fp in fps:
        ref = fp['ref']
        if ref not in placements:
            continue
        x, y, layer, rot = placements[ref]
        block = fp['block']
        new_block = re.sub(r'\(at [0-9.\-]+ [0-9.\-]+(?: [0-9.\-]+)?\)',
                           f'(at {x:.2f} {y:.2f} {rot:.1f})',
                           block, count=1)
        new_block = re.sub(r'\(layer "[^"]+"\)', f'(layer "{layer}")',
                           new_block, count=1)
        replacements.append((fp['start'], fp['end'], new_block))

    new_txt = txt
    for start, end, new_block in sorted(replacements, key=lambda r: -r[0]):
        new_txt = new_txt[:start] + new_block + new_txt[end:]

    PCB.write_text(new_txt)
    print(f"\nWrote: {PCB} ({PCB.stat().st_size:,} bytes)")
    print(f"Footprints placed: {len(replacements)} / {len(fps)}")
    unplaced = [fp for fp in fps if fp['ref'] not in placements]
    if unplaced:
        print(f"WARNING: {len(unplaced)} unplaced footprints (left at origin):")
        for fp in unplaced[:10]:
            print(f"  {fp['ref']:8s} {fp['value']:30s} ({fp['lib']})")


if __name__ == "__main__":
    main()
