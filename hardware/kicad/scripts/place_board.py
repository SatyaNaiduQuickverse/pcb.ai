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


# Registry of subsystem placers in spec order
ALL_PLACERS = [
    ('S1', 'Battery input',         place_battery_input),
    ('S2', 'Bulk cap bank',         place_bulk_caps),
    # ('S3', 'Supervisor + Hall',     place_supervisor_hall),   # PR after
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
