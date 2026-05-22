"""Phase 4b-REDO — scripted placement with per-MCU pin-side connectivity analysis.

Reads the .kicad_pcb and writes back with each footprint placed for routability
per playbook trap T8 + LQFP-32 pin-side analysis (see PHASE4B_REDO_PLACEMENT.md
for the derivation).

Key change vs Phase 4b: per-channel MCU rotation + FET-to-channel sub-grid
remapping. Each channel's MCU now has its PWM corner (chip's RIGHT+BOTTOM
corner at default, where PA8-10 PWM-HIGH + PA7/PB0/PB1 PWM-LOW pins exit)
facing the board's interior, where its gate driver + MOSFETs sit. FETs are
re-grouped from row-per-channel (62 mm horizontal spread) to 3×2 corner
sub-grids (25×13 mm cluster per channel) — same 24 physical (x,y) positions,
different schematic-ref-to-position assignment. Heatsink validity preserved.

KiCad screen convention used throughout: +Y is DOWN. Channel labels (TL/TR/BL/BR)
refer to position in the KiCad-rendered view (NOT a flipped-Y "user view").
"""

import re
from pathlib import Path
from collections import defaultdict

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
BOARD_W = 90.0   # Phase 4b-REDO2: grew 85 → 90 mm for BEC absorption
BOARD_H = 75.0   # grew 70 → 75 mm

# ───────────── Placement regions (Phase 4b-REDO2 per playbook trap T8) ─────────────

# Channel corner anchors (F.Cu): MCU CENTER coordinates. In KiCad screen
# convention (+Y down), CH1=top-left, CH2=top-right, CH3=bottom-left, CH4=bottom-right.
# Bumped to 8mm inset to keep LQFP-32 7×7mm body on-board with ~5mm clearance.
CHANNEL_CORNERS = {
    1: (8.0,  8.0,  'TL'),  # top-left in KiCad screen view
    2: (82.0, 8.0,  'TR'),  # top-right (was 77 on 85-wide board)
    3: (8.0,  67.0, 'BL'),  # bottom-left (was 62 on 70-tall board)
    4: (82.0, 67.0, 'BR'),  # bottom-right
}

# Per-channel MCU rotation (KiCad CCW degrees) — derived from LQFP-32 pin-side
# analysis: the chip's PWM corner (RIGHT+BOTTOM in chip frame at θ=0, where
# PA8/PA9/PA10 PWM-HIGH on RIGHT and PA7/PB0/PB1 PWM-LOW on BOTTOM exit) must
# face the board's INNER direction (toward gate driver + MOSFETs at board center).
# See docs/PHASE4B_REDO_PLACEMENT.md §3 for full derivation.
CHANNEL_MCU_ROTATION = {
    1: 0,    # PWM corner (chip SE) faces +X+Y (down-right) = inward from CH1 (top-left)
    2: 90,   # CCW 90° → PWM corner faces -X+Y (down-left) = inward from CH2 (top-right)
    3: 270,  # CW 90° → PWM corner faces +X-Y (up-right) = inward from CH3 (bottom-left)
    4: 180,  # 180° → PWM corner faces -X-Y (up-left) = inward from CH4 (bottom-right)
}

# Per-channel "PWM-corner direction" unit vector in board frame. Gate driver,
# CSAs, decoupling caps cluster on this side of the MCU. Derived from rotation:
# chip frame +X+Y rotated by θ.
CHANNEL_PWM_DIR = {
    1: ( 1,  1),  # +X+Y
    2: (-1,  1),  # -X+Y
    3: ( 1, -1),  # +X-Y
    4: (-1, -1),  # -X-Y
}

# MOSFET 6×4 grid (B.Cu, heatsink zone): 6 cols × 4 rows centered on board.
# Per Phase 2.5 sketch: fet 5×6 mm + spacing → 6×7 cols, 4×7.5 rows = 42×30 mm grid.
MOSFET_GRID = {
    'cols': 6,
    'rows': 4,
    'cell_w': 12.5,     # TOLL-8L ~9.5×11 + 1.5mm spacing
    'cell_h': 13.0,
    'origin_x': 5.0,    # 85 - 6×12.5 = 10, so 5mm border each side
    'origin_y': 15.0,   # leaves room for bulk caps + RP FETs + shunts below/above
}

# Bulk caps at left/right edges of B.Cu (scaled for 90×75)
BULK_POS = [(10.0, 67.0), (80.0, 67.0)]

# Reverse-polarity FETs (4× AON6260) — bottom row B.Cu (battery section)
RP_FET_ROW_Y = 5.0
RP_FET_X0 = 30.0
RP_FET_DX = 7.0

# TVS near battery input
TVS_POS = (78.0, 5.0)

# Battery solder pads — bottom edge B.Cu
BATT_PAD_POS = (10.0, 5.0)

# FC connector — top of F.Cu, centered (board height grew, recentered)
FC_POS = (40.0, 71.0)

# 3× ESD near FC
ESD_POS = [(33.0, 66.0), (39.0, 66.0), (45.0, 66.0)]

# Status LEDs (channel indicator LEDs near each MCU)
LED_STATUS_POS = {1: (16.0, 18.0), 2: (74.0, 18.0), 3: (16.0, 57.0), 4: (74.0, 57.0)}
# Power-good LED (existing, on V3V3 — channel-shared)
LED_PG_POS = (45.0, 21.0)

# ─── Phase 4b-REDO2 NEW BEC component positions ───
# NTC pair (2× MF72 5D25 in parallel) — top of board, between battery pads and bulk caps.
# Battery line series element, so positioned in battery zone.
NTC_POS = {1: (15.0, 9.0), 2: (20.0, 9.0)}

# Indicator LEDs (LED_PWR green = battery present; LED_RPOL red = polarity reversed)
LED_PWR_POS = (28.0, 9.0)        # green, near battery section
LED_RPOL_POS = (33.0, 9.0)       # red, adjacent
R_LED_PWR_POS = (28.0, 12.0)
R_LED_RPOL_POS = (33.0, 12.0)

# BEC zone: middle band y=24..40 on F.Cu, x=10..80 (over B.Cu MOSFET grid — different layer).
# 5 buck columns + safety stack per column.
# Buck IC + inductor + LC filter + safety stack each takes ~10×12 mm column.
BEC_BUCK_ZONE = {
    'origin_y': 24.0,             # top of band
    'rows': 4,                    # 4 vertical positions per buck (IC, L, cap-stack, eFuse+TVS)
    'col_w': 13.0,                # column width
    'col_y_spacing': 4.0,         # vertical pitch within a column
}
# Per-buck column origins (5 bucks = 5 columns starting at x=12, spaced 13mm = ends at x=64)
BEC_BUCK_COL_X = {
    1: 12.0,   # V5_FC
    2: 25.0,   # V5_PI5
    3: 38.0,   # V5_AI
    4: 51.0,   # V9_VTX1
    5: 64.0,   # V9_VTX2
}

# Voltage supervisor for V5_PI5 — adjacent to Buck #2 column
SUPERVISOR_POS = (25.0, 39.0)

# Schottky catch diodes (1 per buck) — placed below each buck IC
# BEC solder pads — distributed on board edges per T7, with proper edge clearance.
# 6 rail pads × 2 (V + GND) + 4 GND distribution = 16 total.
# All pads positioned ≥ 2 mm from any board edge to keep pad bodies on-board
# (D 4.0mm pads have 2mm radius → need ≥2 mm inset).
BEC_PAD_POS = {
    # V5_FC: top edge (high Y in script = top in user view), left of FC connector
    'V5_FC_PLUS':  (10.0, 72.0),
    'V5_FC_GND':   (15.0, 72.0),
    # V5_PI5: right edge, mid (between CH2 SWD and CH4 SWD)
    'V5_PI5_PLUS': (87.0, 35.0),
    'V5_PI5_GND':  (87.0, 40.0),
    # V5_AI: right edge, lower-mid (adjacent V5_PI5)
    'V5_AI_PLUS':  (87.0, 45.0),
    'V5_AI_GND':   (87.0, 50.0),
    # V9_VTX1: left edge, mid (between CH1 SWD and CH3 motors)
    'V9_VTX1_PLUS': (3.0, 25.0),
    'V9_VTX1_GND':  (3.0, 30.0),
    # V9_VTX2: left edge, mid-lower
    'V9_VTX2_PLUS': (3.0, 42.0),
    'V9_VTX2_GND':  (3.0, 47.0),
    # V3V3: top edge, right side (away from CH4 motors)
    'V3V3_PLUS':   (75.0, 72.0),
    'V3V3_GND':    (80.0, 72.0),
    # GND distribution × 4 — spread
    'GND_DIST_1':  (85.0, 72.0),
    'GND_DIST_2':  (87.0, 18.0),  # right edge, between motor pads + SWD
    'GND_DIST_3':  (3.0, 18.0),   # left edge, between SWD and battery
    'GND_DIST_4':  (3.0, 70.0),   # left edge, below CH3 motor pads
}

# Motor solder pads: 3 per edge, one channel per edge (T7). 2mm edge clearance.
MOTOR_PADS = {
    # CH1 → bottom edge in user view (low Y in script)
    (1, 'A'): (15.0, 2.0),  (1, 'B'): (18.0, 2.0),  (1, 'C'): (21.0, 2.0),
    # CH2 → right edge (board 90 wide → x=88 for 2mm clearance)
    (2, 'A'): (88.0, 15.0), (2, 'B'): (88.0, 18.0), (2, 'C'): (88.0, 21.0),
    # CH3 → left edge (board 75 tall, CH3 in upper region in user view)
    (3, 'A'): (2.0, 55.0),  (3, 'B'): (2.0, 58.0),  (3, 'C'): (2.0, 61.0),
    # CH4 → top edge in user view (high Y, board 75 tall → y=73 with 2mm clearance)
    (4, 'A'): (62.0, 73.0), (4, 'B'): (65.0, 73.0), (4, 'C'): (68.0, 73.0),
}

# SWD test pads: 2 per channel (SWDIO + SWCLK), on board edges near each MCU
SWD_PADS = {
    (1, 'SWDIO'): (2.0, 14.0),  (1, 'SWCLK'): (2.0, 17.0),
    (2, 'SWDIO'): (88.0, 28.0), (2, 'SWCLK'): (88.0, 31.0),
    (3, 'SWDIO'): (2.0, 64.0),  (3, 'SWCLK'): (2.0, 67.0),
    (4, 'SWDIO'): (88.0, 55.0), (4, 'SWCLK'): (88.0, 58.0),
}

# ───────────── Per-channel passive cluster offsets ─────────────
# 10×10 mm region around each MCU, partitioned into sub-grid for the
# ~50 per-channel passives (decoupling + BEMF + bootstrap + CSAs + driver + etc.)
# We use a dense 7×7 = 49 cell sub-grid at 1.4 mm pitch starting from the MCU's
# anchor + (12, 0) offset (right of MCU).
CHANNEL_PASSIVE_GRID = {
    'cols': 7,
    'rows': 7,
    'cell_w': 1.4,
    'cell_h': 1.4,
}


def parse_footprints(pcb_text):
    """Find all (footprint ...) blocks. Return list of dicts with metadata + (start, end) char indices."""
    # KiCad .kicad_pcb format: footprint blocks are nested S-expr. Find each
    # block by locating "(footprint " at line start, then walking parens.
    results = []
    pos = 0
    while True:
        idx = pcb_text.find("\n\t(footprint ", pos)
        if idx < 0:
            break
        # Walk balanced parens from the open '('
        start = idx + 1  # skip leading \n
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
        # Extract metadata. Block starts with `\t(footprint "..."` (leading tab),
        # so use re.search (not re.match) for the lib name — fixes a pre-existing
        # bug that misclassified all mount holes as 'passive' (Phase 4b-REDO fix).
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
    """Map a footprint to a placement category based on value + ref + lib."""
    val = fp['value']
    ref = fp['ref']
    lib = fp['lib'] or ''

    # Mounting holes — leave alone (already placed in Phase 4a)
    if 'MountingHole' in lib:
        return ('mount_hole', None)

    # MOSFETs — reverse-pol (Q1-Q4, AON6260 stays per Phase 2e) vs phase (AOTL66912 per 4c-resume Option C)
    if 'AOTL66912' in val:
        return ('phase_fet', ref)
    if 'AON6260' in val:
        if ref in ('Q1', 'Q2', 'Q3', 'Q4'):
            return ('rp_fet', int(ref[1:]))
        return ('phase_fet', ref)  # legacy fallback

    # Shunts
    if val == '0.2mR':
        return ('shunt', ref)

    # Bulk caps
    if '470uF' in val:
        return ('bulk_cap', ref)

    # TVS
    if val == 'SMBJ33A':
        return ('tvs', ref)

    # Battery solder pads
    if val == 'BATT_PAD':
        return ('batt_pad', ref)

    # MCUs
    if 'AT32F421' in val:
        # Channel determined by position in for-loop creation order; we'll match by index via channel detection in placement
        return ('mcu', ref)

    # Gate drivers
    if 'DRV8300' in val:
        return ('driver', ref)

    # CSAs
    if 'INA186' in val:
        return ('csa', ref)

    # Buck/LDO/inductor/ferrite
    if 'LMR51420' in val:
        return ('buck', ref)
    if 'TLV76733' in val:
        return ('ldo', ref)
    if '0.47uH' in val:
        return ('buck_inductor', ref)
    if '120ohm' in val:
        return ('ferrite_vdda', ref)

    # FC connector
    if 'SM08B-SRSS' in val:
        return ('fc_connector', ref)

    # ESD arrays
    if 'USBLC6' in val:
        return ('esd', ref)

    # LEDs (distinct values per Phase 4b-REDO2 — was ambiguous in Phase 4b)
    if val == 'GREEN':
        return ('led_pg', ref)            # power-good (on V3V3)
    if val == 'RED':
        return ('led_status', ref)        # 4× channel status LEDs
    if val == 'GREEN_PWR':
        return ('led_pwr', ref)           # NEW: battery present indicator
    if val == 'RED_RPOL':
        return ('led_rpol', ref)          # NEW: rev-pol warning indicator

    # Phase 4b-REDO2 new BEC components
    if val == 'MF72_5D25':
        return ('ntc_icl', ref)           # 2× NTC inrush limiter in parallel
    if 'TPS54560' in val:
        return ('bec_buck_5v', ref)        # 3× 5V bucks
    if 'AOZ1284' in val:
        return ('bec_buck_9v', ref)        # 2× 9V bucks
    if val == 'SS54':
        return ('bec_schottky', ref)       # 5× Schottky catch diodes
    if 'TPS259251' in val:
        return ('bec_efuse', ref)          # 3× 5V eFuses
    if val == 'MF-MSMF200':
        return ('bec_polyfuse', ref)       # 2× 9V polyfuses
    if 'VSUP' in val or 'APX803' in val:
        return ('bec_supervisor', ref)     # voltage supervisor for V5_PI5
    if val == 'SMAJ5.0A' or val == 'SMAJ9.0A':
        return ('bec_tvs', ref)            # 5× per-rail TVS
    if val.startswith('100uF_'):
        return ('bec_polymer_cap', ref)    # 2× polymer electrolytic (enhanced filter)
    if val == '600ohm@100MHz':
        return ('bec_ferrite', ref)        # 5× LC filter ferrite beads

    # BEC solder pads — values like PAD_V5_FC_PLUS, PAD_V3V3_GND, PAD_GND_DIST_1
    # Regex: PAD_ + (V<digits-letters>_<suffix> OR GND_DIST_<n>)
    if val.startswith('PAD_'):
        return ('bec_pad', val)            # key by full value for BEC_PAD_POS lookup

    # Motor + SWD pads (by value pattern from SKiDL)
    motor_m = re.match(r'MOTOR_([ABC])_CH([1-4])', val)
    if motor_m:
        return ('motor_pad', (int(motor_m.group(2)), motor_m.group(1)))
    swd_m = re.match(r'(SWDIO|SWCLK)_CH([1-4])', val)
    if swd_m:
        return ('swd_pad', (int(swd_m.group(2)), swd_m.group(1)))

    # Default: per-channel passive (cap / resistor / diode etc.)
    return ('passive', ref)


def dedup_mount_holes(txt):
    """Remove duplicate mount-hole footprint blocks (Phase 4a/4c-resume legacy bug:
    setup_board.py was non-idempotent and accumulated 12 holes stacked at one position).
    Keep first 4 blocks; delete the rest. Reposition the kept 4 at proper board corners.
    """
    # Find all mount hole footprint block char-ranges.
    mh_blocks = []
    pos = 0
    while True:
        idx = txt.find('\n\t(footprint "MountingHole:', pos)
        if idx < 0:
            break
        start = idx + 1  # skip leading \n; include \t(footprint...
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
        mh_blocks.append((idx, end))  # idx points to \n before \t — include the \n in deletion
        pos = end

    if len(mh_blocks) <= 4:
        return txt, len(mh_blocks)

    # Delete blocks 4..end (in reverse to preserve earlier indices)
    deleted = 0
    for idx, end in reversed(mh_blocks[4:]):
        txt = txt[:idx] + txt[end:]
        deleted += 1

    # Reposition the kept 4 holes at proper corners for current 90×75 board
    # (per setup_board.py MOUNT_X_PAD=5, MOUNT_Y_PAD=5, BOARD_W=90, BOARD_H=75).
    # Custom 80×65 spacing pattern (Phase 4b-REDO2 commercial-product class).
    corners = [(5.0, 5.0), (85.0, 5.0), (5.0, 70.0), (85.0, 70.0)]
    # Re-scan after deletion to get fresh positions of the kept 4
    pos = 0
    kept = []
    while len(kept) < 4:
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
        kept.append((start, end))
        pos = end

    # Rewrite each (at ...) to the corner position (in reverse to preserve offsets)
    for i, (start, end) in enumerate(reversed(kept)):
        cx, cy = corners[len(kept) - 1 - i]
        block = txt[start:end]
        new_block = re.sub(r'\(at [0-9.\-]+ [0-9.\-]+(?: [0-9.\-]+)?\)',
                           f'(at {cx} {cy} 0.0)', block, count=1)
        txt = txt[:start] + new_block + txt[end:]

    return txt, deleted


def main():
    txt = PCB.read_text()

    # Pre-processing: dedup mount holes + reposition to proper corners (90×75 board)
    txt, mh_deleted = dedup_mount_holes(txt)
    if mh_deleted:
        print(f"Pre-processing: removed {mh_deleted} duplicate mount holes; "
              f"4 remaining repositioned to corners (5,5), (85,5), (5,70), (85,70)")

    fps = parse_footprints(txt)
    print(f"Parsed {len(fps)} footprints")

    # Group by category
    groups = defaultdict(list)
    for fp in fps:
        cat, key = categorize(fp)
        groups[cat].append((fp, key))
    print("\nFootprints by category:")
    for cat, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"  {cat:18s} {len(items)}")

    # Build placement assignments
    placements = {}  # ref → (x, y, layer, rotation)

    # 1) MOSFETs (phase) — 6×4 grid on B.Cu, RE-MAPPED into per-channel 3×2 sub-grids.
    # Phase 4b had FETs in a row-per-channel layout (each channel's 6 FETs spanned
    # x=5..67.5, 62mm horizontal). New layout: each channel's 6 FETs in a 3×2 sub-grid
    # at the corresponding quadrant of the 6×4 grid (25mm × 13mm cluster).
    # Per netlist ordering: Q5..Q10 = CH1, Q11..Q16 = CH2, Q17..Q22 = CH3, Q23..Q28 = CH4.
    # SAME 24 physical (x,y) positions — only schematic-ref-to-position assignment changes.
    # Heatsink (80×55 Al6061) covers all 24 positions → thermal verdict preserved.
    phase_fets = [fp for fp, _ in groups.get('phase_fet', [])]
    g = MOSFET_GRID
    # CH→sub-grid quadrant (col_start, row_start). Each ch gets 3 cols × 2 rows.
    ch_to_quadrant = {
        1: (0, 0),   # CH1 top-left in KiCad screen (low Y) → upper-left grid quadrant
        2: (3, 0),   # CH2 top-right → upper-right quadrant
        3: (0, 2),   # CH3 bottom-left → lower-left quadrant
        4: (3, 2),   # CH4 bottom-right → lower-right quadrant
    }
    for i, fp in enumerate(phase_fets[:g['cols'] * g['rows']]):
        ch = (i // 6) + 1                   # 6 FETs per channel
        idx_in_ch = i % 6                   # 0..5 within channel
        col0, row0 = ch_to_quadrant[ch]
        sub_col = idx_in_ch % 3             # 0..2 within 3-col sub-grid
        sub_row = idx_in_ch // 3            # 0..1 within 2-row sub-grid
        col = col0 + sub_col
        row = row0 + sub_row
        x = g['origin_x'] + col * g['cell_w']
        y = g['origin_y'] + row * g['cell_h']
        placements[fp['ref']] = (x, y, 'B.Cu', 0.0)

    # 2) Reverse-polarity FETs (Q1-Q4) — B.Cu bottom row
    for fp, idx in groups.get('rp_fet', []):
        i = idx - 1
        x = RP_FET_X0 + i * RP_FET_DX
        y = RP_FET_ROW_Y
        placements[fp['ref']] = (x, y, 'B.Cu', 0.0)

    # 3) Bulk caps (2× 470µF)
    for i, (fp, _) in enumerate(groups.get('bulk_cap', [])[:2]):
        x, y = BULK_POS[i]
        placements[fp['ref']] = (x, y, 'B.Cu', 0.0)

    # 4) TVS
    for fp, _ in groups.get('tvs', []):
        placements[fp['ref']] = (TVS_POS[0], TVS_POS[1], 'B.Cu', 0.0)

    # 5) Battery pad
    for fp, _ in groups.get('batt_pad', []):
        placements[fp['ref']] = (BATT_PAD_POS[0], BATT_PAD_POS[1], 'B.Cu', 0.0)

    # 6) Shunts — row right above the MOSFET grid (B.Cu)
    shunts = [fp for fp, _ in groups.get('shunt', [])]
    shunt_y = MOSFET_GRID['origin_y'] - 4.0
    for i, fp in enumerate(shunts[:12]):
        x = MOSFET_GRID['origin_x'] + (i % 6) * MOSFET_GRID['cell_w']
        y = shunt_y - (i // 6) * 3.0  # 2 rows if more than 6
        placements[fp['ref']] = (x, y, 'B.Cu', 0.0)

    # 7) MCUs (4× AT32F421) — F.Cu corners, with per-channel rotation per pin-side analysis
    mcus = [fp for fp, _ in groups.get('mcu', [])]
    for i, fp in enumerate(mcus[:4]):
        ch = i + 1
        x, y, label = CHANNEL_CORNERS[ch]
        rot = CHANNEL_MCU_ROTATION[ch]
        placements[fp['ref']] = (x, y, 'F.Cu', rot)

    # 8) Gate drivers (4× DRV8300) — F.Cu adjacent to MCU's PWM corner.
    # Offset is 8mm along the PWM-direction vector (chip's PWM corner = chip's
    # bottom-right in chip frame, rotated by channel rotation).
    drivers = [fp for fp, _ in groups.get('driver', [])]
    GATE_DRIVER_OFFSET_MM = 7.0  # 7 mm from MCU center to gate driver center
    for i, fp in enumerate(drivers[:4]):
        ch = i + 1
        mx, my, _ = CHANNEL_CORNERS[ch]
        dx, dy = CHANNEL_PWM_DIR[ch]
        # Place gate driver along PWM-corner direction
        x = mx + dx * GATE_DRIVER_OFFSET_MM
        y = my + dy * GATE_DRIVER_OFFSET_MM
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 9) CSAs (12×) — F.Cu clustered 3 per channel, along the PWM-corner direction
    # (between MCU and shunt row, since CSAs need short shunt → CSA → ADC paths).
    # CSAs are in a 3-in-a-row layout perpendicular to the PWM-direction vector.
    csas = [fp for fp, _ in groups.get('csa', [])]
    CSA_RADIAL_OFFSET_MM = 11.0   # from MCU center along PWM direction
    CSA_TANGENTIAL_SPACING_MM = 2.5
    for i, fp in enumerate(csas[:12]):
        ch = (i // 3) + 1
        sub = i % 3
        mx, my, _ = CHANNEL_CORNERS[ch]
        dx, dy = CHANNEL_PWM_DIR[ch]
        # Tangential vector perpendicular to PWM direction (rotate 90° CCW: (dx,dy) → (-dy,dx))
        tx, ty = -dy, dx
        cx = mx + dx * CSA_RADIAL_OFFSET_MM + tx * (sub - 1) * CSA_TANGENTIAL_SPACING_MM
        cy = my + dy * CSA_RADIAL_OFFSET_MM + ty * (sub - 1) * CSA_TANGENTIAL_SPACING_MM
        placements[fp['ref']] = (cx, cy, 'F.Cu', 0.0)

    # 10a) Legacy single buck/LDO (now replaced by Phase 2d-redo BEC bucks below)
    # — but old SKiDL refs still exist for ferrite_vdda + LDO. Keep LDO at original
    # right-side position; ferrite_vdda near analog references.
    for fp, _ in groups.get('ldo', []):
        placements[fp['ref']] = (75.0, 38.0, 'F.Cu', 0.0)
    for fp, _ in groups.get('ferrite_vdda', []):
        placements[fp['ref']] = (40.0, 30.0, 'F.Cu', 0.0)

    # 10b) Phase 4b-REDO2 NEW BEC components — 5 bucks + safety stacks
    # Layout: BEC strip in middle band y=24..40, 5 columns × 4 rows per column.
    # Each column hosts: buck IC (row 0) + inductor (row 1) + cap-stack (row 2) +
    # eFuse/polyfuse + TVS + ferrite (row 3).
    # NOTE: this strip overlaps with B.Cu MOSFET grid (y=15..54). Different layer:
    # F.Cu BEC components vs B.Cu MOSFETs → no physical conflict.

    # 5V bucks (Buck #1, #2, #3 = TPS54560 × 3 for V5_FC, V5_PI5, V5_AI)
    bec_buck_5v = [fp for fp, _ in groups.get('bec_buck_5v', [])]
    for i, fp in enumerate(bec_buck_5v[:3]):
        col_idx = i + 1   # buck cols 1, 2, 3
        x = BEC_BUCK_COL_X[col_idx]
        y = BEC_BUCK_ZONE['origin_y']
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 9V bucks (Buck #4, #5 = AOZ1284 × 2 for V9_VTX1, V9_VTX2)
    bec_buck_9v = [fp for fp, _ in groups.get('bec_buck_9v', [])]
    for i, fp in enumerate(bec_buck_9v[:2]):
        col_idx = i + 4   # buck cols 4, 5
        x = BEC_BUCK_COL_X[col_idx]
        y = BEC_BUCK_ZONE['origin_y']
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 5× Schottky catch diodes (one per buck, placed below the buck IC)
    bec_schottky = [fp for fp, _ in groups.get('bec_schottky', [])]
    for i, fp in enumerate(bec_schottky[:5]):
        col_idx = i + 1
        x = BEC_BUCK_COL_X[col_idx]
        y = BEC_BUCK_ZONE['origin_y'] + BEC_BUCK_ZONE['col_y_spacing']  # row 1
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 3× eFuses (5V rails) — placed in row 2 of cols 1, 2, 3
    bec_efuse = [fp for fp, _ in groups.get('bec_efuse', [])]
    for i, fp in enumerate(bec_efuse[:3]):
        col_idx = i + 1
        x = BEC_BUCK_COL_X[col_idx]
        y = BEC_BUCK_ZONE['origin_y'] + 2 * BEC_BUCK_ZONE['col_y_spacing']  # row 2
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 2× Polyfuses (9V rails) — placed in row 2 of cols 4, 5
    bec_polyfuse = [fp for fp, _ in groups.get('bec_polyfuse', [])]
    for i, fp in enumerate(bec_polyfuse[:2]):
        col_idx = i + 4
        x = BEC_BUCK_COL_X[col_idx]
        y = BEC_BUCK_ZONE['origin_y'] + 2 * BEC_BUCK_ZONE['col_y_spacing']  # row 2
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 5× TVS (one per rail) — placed in row 3
    bec_tvs = [fp for fp, _ in groups.get('bec_tvs', [])]
    for i, fp in enumerate(bec_tvs[:5]):
        col_idx = i + 1
        x = BEC_BUCK_COL_X[col_idx]
        y = BEC_BUCK_ZONE['origin_y'] + 3 * BEC_BUCK_ZONE['col_y_spacing']  # row 3
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 5× Ferrite beads (LC filter, one per rail) — placed in row 3 + 2mm offset
    bec_ferrite = [fp for fp, _ in groups.get('bec_ferrite', [])]
    for i, fp in enumerate(bec_ferrite[:5]):
        col_idx = i + 1
        x = BEC_BUCK_COL_X[col_idx]
        y = BEC_BUCK_ZONE['origin_y'] + 3 * BEC_BUCK_ZONE['col_y_spacing'] + 2.0
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 2× Polymer electrolytic (enhanced filter for V5_PI5 + V5_AI) — below ferrite
    bec_polymer = [fp for fp, _ in groups.get('bec_polymer_cap', [])]
    for i, fp in enumerate(bec_polymer[:2]):
        col_idx = i + 2   # cols 2 (V5_PI5), 3 (V5_AI)
        x = BEC_BUCK_COL_X[col_idx]
        y = BEC_BUCK_ZONE['origin_y'] + 3 * BEC_BUCK_ZONE['col_y_spacing'] + 4.5
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # Voltage supervisor for V5_PI5 — adjacent to buck #2 col
    for fp, _ in groups.get('bec_supervisor', []):
        placements[fp['ref']] = (SUPERVISOR_POS[0], SUPERVISOR_POS[1], 'F.Cu', 0.0)

    # 2× NTC inrush limiters (in parallel) — top of board, battery section
    bec_ntc = [fp for fp, _ in groups.get('ntc_icl', [])]
    for i, fp in enumerate(bec_ntc[:2]):
        x, y = NTC_POS[i + 1]
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # Indicator LEDs (battery + rev-pol) — in battery section
    for fp, _ in groups.get('led_pwr', []):
        placements[fp['ref']] = (LED_PWR_POS[0], LED_PWR_POS[1], 'F.Cu', 0.0)
    for fp, _ in groups.get('led_rpol', []):
        placements[fp['ref']] = (LED_RPOL_POS[0], LED_RPOL_POS[1], 'F.Cu', 0.0)

    # 16× BEC solder pads — distributed on board edges (T7)
    for fp, key in groups.get('bec_pad', []):
        # key is the value string like "PAD_V5_FC_PLUS"; strip "PAD_" prefix
        pad_key = key.replace('PAD_', '', 1)
        if pad_key in BEC_PAD_POS:
            x, y = BEC_PAD_POS[pad_key]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 11) FC connector
    for fp, _ in groups.get('fc_connector', []):
        placements[fp['ref']] = (FC_POS[0], FC_POS[1], 'F.Cu', 0.0)

    # 12) ESD (3×)
    for i, (fp, _) in enumerate(groups.get('esd', [])[:3]):
        x, y = ESD_POS[i]
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 13) Status LEDs
    for fp, _ in groups.get('led_pg', []):
        placements[fp['ref']] = (LED_PG_POS[0], LED_PG_POS[1], 'F.Cu', 0.0)
    led_status_fps = [fp for fp, _ in groups.get('led_status', [])]
    for i, fp in enumerate(led_status_fps[:4]):
        ch = i + 1
        x, y = LED_STATUS_POS[ch]
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 14) Motor solder pads (12 × edge positions)
    for fp, key in groups.get('motor_pad', []):
        if key in MOTOR_PADS:
            x, y = MOTOR_PADS[key]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 15) SWD test pads (8× left edge)
    for fp, key in groups.get('swd_pad', []):
        if key in SWD_PADS:
            x, y = SWD_PADS[key]
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    # 16) Per-channel passive cluster — pack remaining "passive" footprints
    # into 4 zones (one per channel), 7×7 grid each, 1.4 mm pitch.
    # Zones are placed along each channel's PWM-corner direction (between MCU and
    # gate driver), so decoupling caps and BEMF dividers route to the chip side
    # with the most heavy-routing pins (PWM + ADC + BEMF on RIGHT+BOTTOM at θ=0).
    passives = [fp for fp, _ in groups.get('passive', [])]
    PASSIVE_ZONE_OFFSET_MM = 14.0   # from MCU center along PWM direction
    zones = {}
    for ch in (1, 2, 3, 4):
        mx, my, _ = CHANNEL_CORNERS[ch]
        dx, dy = CHANNEL_PWM_DIR[ch]
        # Zone origin = MCU center + PWM-direction offset, then back off by half grid
        # so the grid is roughly centered around the offset point
        pg = CHANNEL_PASSIVE_GRID
        grid_half_w = (pg['cols'] - 1) * pg['cell_w'] / 2.0
        grid_half_h = (pg['rows'] - 1) * pg['cell_h'] / 2.0
        zones[ch] = (mx + dx * PASSIVE_ZONE_OFFSET_MM - grid_half_w,
                     my + dy * PASSIVE_ZONE_OFFSET_MM - grid_half_h)
    # Phase 4b-REDO2: first ~65 "passive" components are BEC supporting passives
    # (buck input/output caps, feedback divider resistors, LC filter caps).
    # Send them to a dedicated BEC passive overflow zone in the lower-middle band
    # (y=44..56). The remaining ~160 are channel-specific decoupling/BEMF parts.
    BEC_PASSIVE_COUNT = 65            # first N passives go to BEC zone
    BEC_PASSIVE_ORIGIN = (12.0, 44.0)
    BEC_PASSIVE_COLS = 25
    BEC_PASSIVE_ROWS = 6
    BEC_PASSIVE_CELL = 1.4
    pg = CHANNEL_PASSIVE_GRID

    # Channel passives = passives[BEC_PASSIVE_COUNT:]
    channel_passives = passives[BEC_PASSIVE_COUNT:]
    per_zone = (len(channel_passives) + 3) // 4

    for i, fp in enumerate(passives):
        if i < BEC_PASSIVE_COUNT:
            # BEC passive zone — lower-middle band, 25×6 grid
            idx_in_bec = i
            col = idx_in_bec % BEC_PASSIVE_COLS
            row = idx_in_bec // BEC_PASSIVE_COLS
            x = BEC_PASSIVE_ORIGIN[0] + col * BEC_PASSIVE_CELL
            y = BEC_PASSIVE_ORIGIN[1] + row * BEC_PASSIVE_CELL
            placements[fp['ref']] = (x, y, 'F.Cu', 0.0)
            continue
        # Channel passive
        ch_idx = i - BEC_PASSIVE_COUNT
        ch = (ch_idx // per_zone) + 1
        ch = min(ch, 4)
        idx_in_zone = ch_idx % per_zone
        col = idx_in_zone % pg['cols']
        row = idx_in_zone // pg['cols']
        zx, zy = zones[ch]
        x = zx + col * pg['cell_w']
        y = zy + row * pg['cell_h']
        if row >= pg['rows']:
            # Overflow — extend BEC passive overflow strip
            extra = (i - BEC_PASSIVE_COUNT) - per_zone * pg['rows'] * pg['cols']
            x = BEC_PASSIVE_ORIGIN[0] + (extra % 25) * 1.4
            y = BEC_PASSIVE_ORIGIN[1] + BEC_PASSIVE_ROWS * BEC_PASSIVE_CELL + 1.5 + (extra // 25) * 1.5
        placements[fp['ref']] = (x, y, 'F.Cu', 0.0)

    print(f"\nAssigned positions: {len(placements)} / {len(fps)} footprints")

    # Apply placements: rewrite each footprint block with new (at ...) and (layer ...) lines
    # Build replacement list sorted by start index in reverse so offsets stay valid
    replacements = []
    for fp in fps:
        ref = fp['ref']
        if ref not in placements:
            continue
        x, y, layer, rot = placements[ref]
        block = fp['block']
        # Replace (at X Y Rot?) — the top-level (at ...) is the first one after (footprint "..."
        new_block = re.sub(r'\(at [0-9.\-]+ [0-9.\-]+(?: [0-9.\-]+)?\)',
                           f'(at {x:.2f} {y:.2f} {rot:.1f})',
                           block, count=1)
        # Replace (layer "...") for the top-level layer (also first occurrence)
        new_block = re.sub(r'\(layer "[^"]+"\)', f'(layer "{layer}")', new_block, count=1)
        replacements.append((fp['start'], fp['end'], new_block))

    # Apply in reverse order
    new_txt = txt
    for start, end, new_block in sorted(replacements, key=lambda r: -r[0]):
        new_txt = new_txt[:start] + new_block + new_txt[end:]

    PCB.write_text(new_txt)
    print(f"\nWrote: {PCB} ({PCB.stat().st_size:,} bytes)")
    print(f"Footprints placed: {len(replacements)}")


if __name__ == "__main__":
    main()
