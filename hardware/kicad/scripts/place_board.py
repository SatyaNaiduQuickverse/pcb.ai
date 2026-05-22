"""Phase 4 subsystem-aware placement (R6 motor-pad-anchored architecture).

Per docs/PHASE4_SUBSYSTEMS.md (Phase 4-subsystem-spec, master Task #48,
landed in PR #31). Replaces the previous R1 center-cluster placement which
had 1301 same-layer body-bbox defects from grid-stacking bugs.

Sub-phase ordering (one PR per subsystem per spec §5):
  S1 battery input — implemented here
  S2 bulk caps — Phase 4-place-bulk-caps (next)
  S3 supervisor + Hall — Phase 4-place-supervisor-hall
  S4 channel template (×4) — Phase 4-place-channel-template / -channels-x4
  S5 BEC — Phase 4-place-bec
  S6 FC + AUX — Phase 4-place-connectors
  S7 Edge.Cuts + mount holes — already in setup_board.py

Each sub-phase places ONLY its assigned components. Other 570+ components
remain at kinet2pcb-default positions in this phase; subsequent sub-phases
place them.

This file's structure:
  ALL_PLACERS: list of (name, function) tuples. Each function takes the
  list of footprints + the placements dict; appends ref→(x, y, layer, rot)
  entries for its subsystem only.

  main() runs all enabled placers in order.

CLI:
  python3 place_board.py                — run all enabled subsystem placers
  python3 place_board.py --only=S1      — run only the named subsystem
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")

# ────────────────────────────────────────────────────────────────────
# S1: Battery input subsystem (per docs/PHASE4_SUBSYSTEMS.md §S1)
# Zone: X=20-80, Y=0-13 (bottom edge band, but RP FET 2×2 cluster spills
# to y=18 due to SuperSO8 5×6 body + minimum-clearance requirement;
# acceptable since adjacent S2 bulk-cap zone (Y=13-42) is empty at PR-time).
# ────────────────────────────────────────────────────────────────────
S1_POSITIONS = {
    # ref          (x,    y,   layer,  rot)   notes
    # Bottom-edge row at y=4-5 — XT30 + TVS
    'J1':         (50.0,  4.0, 'F.Cu',  0.0),   # BATT_PAD (XT30) center-bottom
    'D26':        (32.0,  5.0, 'B.Cu',  0.0),   # SMBJ33A TVS (D_SMB), left of XT30
    # Second row at y=10 — NTCs flanking + FET 2×2 cluster centered
    'R1':         (28.0, 10.0, 'F.Cu',  0.0),   # MF72_5D25 NTC inrush #1
    'R2':         (72.0, 10.0, 'F.Cu',  0.0),   # MF72_5D25 NTC inrush #2
    # 2×2 RP FET cluster around (50, 13.5)
    'Q1':         (40.0, 10.0, 'B.Cu',  0.0),   # BSC014N06NS rev-pol #1 (top-left)
    'Q2':         (60.0, 10.0, 'B.Cu',  0.0),   # BSC014N06NS rev-pol #2 (top-right)
    'Q3':         (40.0, 17.0, 'B.Cu',  0.0),   # BSC014N06NS rev-pol #3 (bot-left)
    'Q4':         (60.0, 17.0, 'B.Cu',  0.0),   # BSC014N06NS rev-pol #4 (bot-right)
    # Note: Q3/Q4 spill into Y=13-17 (nominally bulk-cap S2 zone) — RP FET
    # SuperSO8 5×6 body × 2 rows requires ≥12mm vertical span; spec'd Y=0-13
    # zone is too tight. Per master spec §S1 the 2×2 cluster centers at (50, 11);
    # we adopt a slightly south-offset cluster (50, 13.5) to keep ≥1mm gap to
    # row-1 (J1, D26) bbox. S2 bulk caps will avoid the (40-60, 13-17) range.
}
# Expected SKiDL values per ref (sanity check; abort if mismatched)
S1_EXPECTED_VALUES = {
    'J1':  'BATT_PAD',
    'D26': 'SMBJ33A',
    'R1':  'MF72_5D25',
    'R2':  'MF72_5D25',
    'Q1':  'BSC014N06NS',
    'Q2':  'BSC014N06NS',
    'Q3':  'BSC014N06NS',
    'Q4':  'BSC014N06NS',
}


def place_battery_input(fps_by_ref, placements):
    """S1 — battery input subsystem placement (docs/PHASE4_SUBSYSTEMS.md §S1)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, expected_value in S1_EXPECTED_VALUES.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        actual_value = fp['value']
        if expected_value not in actual_value:
            mismatched.append((ref, expected_value, actual_value))
            continue
        x, y, layer, rot = S1_POSITIONS[ref]
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S1 components missing in netlist: {missing}")
    if mismatched:
        print(f"  WARN: S1 ref/value mismatch (sanity-check failed):")
        for ref, exp, act in mismatched:
            print(f"    {ref}: expected '{exp}', got '{act}'")
    return placed


# ────────────────────────────────────────────────────────────────────
# S2: Bulk cap bank (docs/PHASE4_SUBSYSTEMS.md §S2, amended zone Y=20-42)
# CBULK1-4 (C1-C4) in 2×2 linear bank at central spine X=42-58, Y=25-35.
# NOTE: master spec §S2 also lists 8× ceramic decouplers (4× 100nF + 4× 10nF).
# These are NOT present in the netlist — flagged as Phase 5 SKiDL follow-up.
# ────────────────────────────────────────────────────────────────────
S2_POSITIONS = {
    # CP_Elec_10x14.3 actual bbox = 13.59×11.05 mm. Master 2026-05-22 stage-3
    # amendment: Hall (S3 U1) placed vertical at (50, 45) 0° rot → body bbox
    # (42.1, 20.3)..(61.7, 46.0). S2 caps must clear this. Shifted outward:
    # C1/C3 at x=30, C2/C4 at x=70 — outside Hall body bbox by ≥1mm.
    # This pushes caps into what will become NW/NE channel zones (master
    # amended channel inner-edges to X=39/61); Phase 4-place-channels-x4
    # will coordinate (likely shifts channel passive zone to clear bulk caps).
    'C1': (30.0, 24.0, 'F.Cu', 0.0),
    'C2': (70.0, 24.0, 'F.Cu', 0.0),
    'C3': (30.0, 40.0, 'F.Cu', 0.0),
    'C4': (70.0, 40.0, 'F.Cu', 0.0),
}
S2_EXPECTED_VALUE = "EEHZS1V471P"


def place_bulk_caps(fps_by_ref, placements):
    """S2 — bulk cap bank placement (docs/PHASE4_SUBSYSTEMS.md §S2)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, pos in S2_POSITIONS.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        if S2_EXPECTED_VALUE not in fp['value']:
            mismatched.append((ref, S2_EXPECTED_VALUE, fp['value']))
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S2 components missing in netlist: {missing}")
    if mismatched:
        for ref, exp, act in mismatched:
            print(f"  WARN: S2 ref {ref} value mismatch — expected '{exp}', got '{act}'")
    return placed


# ────────────────────────────────────────────────────────────────────
# S3: Supervisor + Hall sensor (docs/PHASE4_SUBSYSTEMS.md §S3)
# Central spine middle, zone X=42-58, Y=42-58.
# Components:
#   J11 TPS3700 supervisor (Conn_01x08 SOT-23-8 placeholder; Phase 5b SKiDL
#     swap to real TPS3700 symbol)
#   U1 ACS770ECB-200B Hall sensor (Allegro_CB_PFF; large body 13.6×27 mm —
#     rotated 90° to fit horizontally in middle band; primary leads carry +VMOTOR)
#   R19 348K + R20 23K2: VMOTOR OVP/UVP divider (27V trip / 18V trip via 0.0625 ratio)
#   C41 100nF: 10 ms inrush delay cap (CT pin)
#   R21 10K: PG_VMOTOR open-drain pull-up to +3V3
#   R30 0R: Hall VCC bridge (V5 → HALL_VCC, optional filter location)
#   C42 1uF, C43 100nF: Hall VCC bypass
#   R31 10K + R32 20K: Hall VOUT divider 5V → 3.3V (FC-ADC compatible)
#   C44 10nF: Hall output post-divider noise filter
#   R33 0Ω 2512, R34 0Ω 2512: VMOTOR primary copper-bridge jumpers
#     (placement-layout aids; physical realization is Phase 5b 3 oz copper bar
#     through Hall primary)
# Total: 14 components (10 in immediate zone + 2 VMOTOR jumpers + supervisor + Hall)
# ────────────────────────────────────────────────────────────────────
S3_POSITIONS = {
    # Hall vertical orientation (0° rot) per master 2026-05-22 stage-3 amendment.
    # Symmetric placement at central spine middle Y=45 — all 4 channels are
    # equidistant ~30 mm from Hall (premium-ESC reference for thermal symmetry).
    # Body bbox at 0° rot = (42.1, 20.3)..(61.7, 46.0); pad 4 (primary current)
    # at (52.96, 22.97) extends north. Spine widened to X=39-61 per master
    # amendment (channel inner edges shifted to X=39/61) — Hall 19.65mm fits.
    'U1':  (50.0, 45.0, 'F.Cu', 0.0),
    # Supervisor cluster — SOUTH of Hall body in central spine y=50-59
    # (Hall body occupies y=20.3-46; spine middle y=46-58 is clear).
    'J11': (50.0, 55.0, 'F.Cu', 0.0),    # TPS3700 supervisor SOT-23-8
    'R19': (45.0, 53.0, 'F.Cu', 0.0),    # 348K OVP/UVP divider top
    'R20': (55.0, 53.0, 'F.Cu', 0.0),    # 23K2 OVP/UVP divider bot
    'C41': (50.0, 59.0, 'F.Cu', 0.0),    # 100nF 10ms inrush-delay cap
    'R21': (45.0, 57.0, 'F.Cu', 0.0),    # 10K PG_VMOTOR pullup
    # Hall VCC bridge + bypass — east of Hall pad 2/3 signal pads at y=45
    # Pad 2 V_CC @ (51.91, 45), pad 3 GND @ (53.82, 45). Decouplers immediately east.
    'R30': (54.0, 47.5, 'F.Cu', 0.0),    # 0Ω V5 → HALL_VCC bridge
    'C42': (56.0, 47.5, 'F.Cu', 0.0),    # 1uF bypass
    'C43': (58.0, 47.5, 'F.Cu', 0.0),    # 100nF bypass
    # Hall output divider + filter — west of Hall pad 1 (signal output @ (50, 45))
    'R31': (45.0, 47.5, 'F.Cu', 0.0),    # 10K div top (5V→3.3V)
    'R32': (45.0, 49.5, 'F.Cu', 0.0),    # 20K div bot
    'C44': (47.0, 49.5, 'F.Cu', 0.0),    # 10nF output filter
    # VMOTOR copper-bridge jumpers (0Ω 2512) on B.Cu — Hall primary path
    # Hall vertical at (50, 45) 0° rot → pad 4 (primary IN) at (52.96, 22.97).
    # Pad 5 (primary OUT) at south end of body near y=46.
    # Bridges placed on B.Cu to backside-route +VMOTOR via PTH to primary pads.
    'R33': (50.0, 25.0, 'B.Cu', 0.0),    # +VMOTOR → Hall pad 4 (north end, IP+)
    'R34': (50.0, 65.0, 'B.Cu', 0.0),    # Hall pad 5 (south end) → +VMOTOR_CH
}
S3_EXPECTED_VALUES = {
    'U1':  'ACS770ECB',
    'J11': 'TPS3700',
    'R19': '348K',
    'R20': '23K2',
    'C41': '100nF',
    'R21': '10K',
    'R30': '0R',
    'C42': '1uF',
    'C43': '100nF',
    'R31': '10K',
    'R32': '20K',
    'C44': '10nF',
    'R33': '0R',
    'R34': '0R',
}


def place_supervisor_hall(fps_by_ref, placements):
    """S3 — supervisor + Hall sensor placement (docs/PHASE4_SUBSYSTEMS.md §S3)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, pos in S3_POSITIONS.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        expected = S3_EXPECTED_VALUES[ref]
        if expected not in fp['value']:
            mismatched.append((ref, expected, fp['value']))
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S3 components missing in netlist: {missing}")
    if mismatched:
        for ref, exp, act in mismatched:
            print(f"  WARN: S3 ref {ref} value mismatch — expected '{exp}', got '{act}'")
    return placed


# ────────────────────────────────────────────────────────────────────
# S6: FC + AUX connectors (docs/PHASE4_SUBSYSTEMS.md §S6)
# Top edge zone Y=72-85 (avoid mount holes H3 at (5,80) and H4 at (95,80)
# with ≥3mm clearance — keep S6 inside x=10..90).
# Master reorder 2026-05-22: S6 before S5 (low-EMC tier-2 anchor before
# introducing BEC tier-3 switching noise).
# Components in netlist:
#   J12 BM06B-SRSS-TB AUX 6-pin (Hall + NTC + AUX_GPIO)
#   J14 SM08B-SRSS-TB FC 8-pin (DShot×4 + TLM + VBAT_SENSE + CURR + GND)
#   J15/J16/J17 USBLC6-2SC6 ESD arrays (3 chips covering 4×DShot + TLM + spare)
#   R36 100K, R37 14K VBAT_SENSE divider (8.143:1 ratio)
#   C49 100nF VBAT filter cap
# Total: 8 components (LEDs come from S1/S3 already; master "4 per-channel
# kill LEDs" are part of S4 channel template, not S6 — honest deviation flag)
# ────────────────────────────────────────────────────────────────────
S6_POSITIONS = {
    'J12': (15.0, 80.0, 'F.Cu',   0.0),    # AUX BM06B-SRSS-TB west top
    'J14': (50.0, 80.0, 'F.Cu',   0.0),    # FC SM08B-SRSS-TB central top
    'J15': (40.0, 75.0, 'F.Cu',   0.0),    # USBLC6 ESD ch1+ch2 DShot
    'J16': (60.0, 75.0, 'F.Cu',   0.0),    # USBLC6 ESD ch3+ch4 DShot
    'J17': (75.0, 75.0, 'F.Cu',   0.0),    # USBLC6 ESD TLM + spare
    'R36': (47.0, 76.0, 'F.Cu',   0.0),    # VBAT divider top 100K
    'R37': (47.0, 74.0, 'F.Cu',   0.0),    # VBAT divider bot 14K
    'C49': (45.0, 74.0, 'F.Cu',   0.0),    # VBAT filter 100nF
}
S6_EXPECTED_VALUES = {
    'J12': 'BM06B',
    'J14': 'SM08B',
    'J15': 'USBLC6',
    'J16': 'USBLC6',
    'J17': 'USBLC6',
    'R36': '100K',
    'R37': '14K',
    'C49': '100nF',
}


def place_connectors(fps_by_ref, placements):
    """S6 — FC + AUX connectors placement (docs/PHASE4_SUBSYSTEMS.md §S6)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, pos in S6_POSITIONS.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        expected = S6_EXPECTED_VALUES[ref]
        if expected not in fp['value']:
            mismatched.append((ref, expected, fp['value']))
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S6 components missing in netlist: {missing}")
    if mismatched:
        for ref, exp, act in mismatched:
            print(f"  WARN: S6 ref {ref} value mismatch — expected '{exp}', got '{act}'")
    return placed


# Registry of subsystem placers in spec order
ALL_PLACERS = [
    ('S1', 'Battery input',         place_battery_input),
    ('S2', 'Bulk cap bank',         place_bulk_caps),
    ('S3', 'Supervisor + Hall',     place_supervisor_hall),
    ('S6', 'FC + AUX connectors',   place_connectors),
    # ('S4', 'Channel template (×4)', place_channels),          # PR ×2
    # ('S5', 'BEC subsystem',         place_bec),               # PR after
]


# ────────────────────────────────────────────────────────────────────
# Footprint parser + helpers
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


def dedup_mount_holes(txt):
    """Drop duplicate MountingHole footprints (setup_board.py is non-idempotent
    on mount-hole addition; keep first 4 at intended corners)."""
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
    only = None
    for arg in sys.argv[1:]:
        if arg.startswith('--only='):
            only = arg.split('=', 1)[1]

    txt = PCB.read_text()

    txt, mh_deleted = dedup_mount_holes(txt)
    if mh_deleted:
        print(f"Pre-processing: removed {mh_deleted} duplicate mount holes")

    fps = parse_footprints(txt)
    print(f"Parsed {len(fps)} footprints")
    fps_by_ref = {fp['ref']: fp for fp in fps}

    # Build placements: ref → (x, y, layer, rot)
    placements = {}
    for name, label, placer in ALL_PLACERS:
        if only and name != only:
            print(f"\nSkipping {name} ({label}) — --only={only} filter")
            continue
        print(f"\nSub-phase {name} ({label}):")
        n = placer(fps_by_ref, placements)
        print(f"  Placed: {n} components")

    print(f"\nTotal placements: {len(placements)} of {len(fps)} footprints")

    # Apply placements by rewriting (at ...) + (layer ...) lines per footprint
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
    print(f"Subsystem components placed: {len(replacements)}")
    if len(replacements) < len(fps):
        print(f"Remaining {len(fps) - len(replacements)} footprints stay at "
              f"kinet2pcb default positions (will be placed in subsequent sub-phases)")


if __name__ == "__main__":
    main()
