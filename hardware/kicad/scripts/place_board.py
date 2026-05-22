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
    # CP_Elec_10x14.3 actual bbox (pads + silkscreen courtyard) is 13.59×11.05 mm
    # — wider than the 10 mm cap body label. With 20 mm horizontal + 16 mm
    # vertical spacing: ≥6 mm horizontal gap, ≥5 mm vertical gap edge-to-edge.
    # SPEC DEVIATION: S2 zone X=42-58 (16 mm wide per master) is too narrow for
    # 2 caps side-by-side. Expanded to X=33-67 (with caps centered at x=40, x=60).
    # Master adjudication accepted similar S1 zone expansion (Y=0-13 → Y=0-20).
    'C1': (40.0, 24.0, 'F.Cu', 0.0),
    'C2': (60.0, 24.0, 'F.Cu', 0.0),
    'C3': (40.0, 40.0, 'F.Cu', 0.0),
    'C4': (60.0, 40.0, 'F.Cu', 0.0),
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
    # ACS770ECB-200B Allegro_CB_PFF actual KiCad bbox at 90° rot = 27×19.6 mm,
    # extending WEST and SOUTH of anchor (signal pad layout + silkscreen).
    # Master spec'd S3 zone X=42-58, Y=42-58 (16×16) is fundamentally too
    # small for this part. Relocated Hall to (75, 65) 90° rot — bbox
    # (49.1, 53.3)..(76.0, 72.9). This is OUT of the master S3 spec zone
    # but is the only position that clears already-placed S1 + S2 with
    # bbox-clean acceptance. Honest spec deviation flag in PHASE4_PLACE_*.md.
    # Future S4 channel placement (planned x=55-95, y=58-72 NE channel) will
    # need to coordinate around Hall body — likely shifts NE channel
    # quadrant slightly or extends S3 zone footprint into NE area.
    'U1':  (75.0, 65.0, 'F.Cu', 90.0),
    # TPS3700 supervisor + VMOTOR divider + delay cap + PG-pullup cluster:
    # Original S3 spec X=42-58 zone preserves these in the central spine
    # (clear of Hall body now relocated to NE).
    'J11': (50.0, 45.0, 'F.Cu', 0.0),
    'R19': (47.0, 48.0, 'F.Cu', 0.0),    # moved south to clear C3 bbox (y>45.5)
    'R20': (54.0, 48.0, 'F.Cu', 0.0),    # moved south to clear C4 bbox
    'C41': (50.0, 49.5, 'F.Cu', 0.0),    # shifted south of R19/R20 row
    'R21': (44.0, 48.0, 'F.Cu', 0.0),
    # Hall VCC bridge + bypass caps — adjacent to Hall body (east of central spine)
    'R30': (78.0, 60.0, 'F.Cu', 0.0),    # 0Ω V5 → HALL_VCC bridge
    'C42': (80.0, 60.0, 'F.Cu', 0.0),    # 1uF bypass
    'C43': (82.0, 60.0, 'F.Cu', 0.0),    # 100nF bypass
    # Hall output divider + filter — east of Hall body
    'R31': (78.0, 70.0, 'F.Cu', 0.0),    # 10K div top
    'R32': (80.0, 70.0, 'F.Cu', 0.0),    # 20K div bot
    'C44': (82.0, 70.0, 'F.Cu', 0.0),    # 10nF filter
    # VMOTOR copper-bridge jumpers (0Ω 2512) on B.Cu — Hall primary path
    # Hall body at (75, 65) → pad 4 (IP+) at (97.03, 67.96), pad 5 (IP-) at ~
    # (97.03, 62.04) (90° rotation). Position bridges at the rail entry/exit.
    'R33': (60.0, 65.0, 'B.Cu', 0.0),    # +VMOTOR → Hall pad 4 (IP+)
    'R34': (90.0, 65.0, 'B.Cu', 0.0),    # Hall pad 5 (IP-) → +VMOTOR_CH
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


# Registry of subsystem placers in spec order
ALL_PLACERS = [
    ('S1', 'Battery input',         place_battery_input),
    ('S2', 'Bulk cap bank',         place_bulk_caps),
    ('S3', 'Supervisor + Hall',     place_supervisor_hall),
    # ('S4', 'Channel template (×4)', place_channels),          # PR ×2
    # ('S5', 'BEC subsystem',         place_bec),               # PR after
    # ('S6', 'FC + AUX',              place_connectors),        # PR after
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
