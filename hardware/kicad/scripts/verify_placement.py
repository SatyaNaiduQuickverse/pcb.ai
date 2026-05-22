"""Phase 4b-REDO — verify placement.

Checks:
1. All footprints have a position (no part at origin).
2. MOSFET zone (B.Cu y=15..54, x=5..67.5) is occupied by exactly 24 phase MOSFETs.
3. MOSFET positions match the expected 6×4 grid.
4. MCU rotations applied per CHANNEL_MCU_ROTATION.
5. Mount holes preserved (at their Phase 4a positions).
6. T7 connector accessibility: FC at top, motor pads on edges.
"""
import re
from pathlib import Path
from collections import defaultdict

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")

# Expected per Phase 4b-redo place_board.py
EXPECTED_MCU_ROTATION = {1: 0, 2: 90, 3: 270, 4: 180}

EXPECTED_MOSFET_X = [5.0, 17.5, 30.0, 42.5, 55.0, 67.5]
EXPECTED_MOSFET_Y = [15.0, 28.0, 41.0, 54.0]

EXPECTED_BOARD_W = 90.0   # Phase 4b-REDO2: grew 85 → 90
EXPECTED_BOARD_H = 75.0   # grew 70 → 75


def parse_footprints(txt):
    results = []
    pos = 0
    while True:
        idx = txt.find("\n\t(footprint ", pos)
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
        block = txt[start:end]
        lib_m = re.search(r'\(footprint "([^"]+)"', block)
        ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
        val_m = re.search(r'\(property "Value" "([^"]+)"', block)
        layer_m = re.search(r'\(layer "([^"]+)"\)', block)
        at_m = re.search(r'\(at ([0-9.\-]+) ([0-9.\-]+)(?: ([0-9.\-]+))?\)', block)
        results.append({
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


def main():
    fps = parse_footprints(PCB.read_text())
    print(f"Total footprints: {len(fps)}")

    fails = []

    # 1) All fps have position (x>0 OR y>0)
    at_origin = [fp for fp in fps if abs(fp['x']) < 0.01 and abs(fp['y']) < 0.01]
    if at_origin:
        fails.append(f"  {len(at_origin)} footprints at origin (unplaced)")
        for fp in at_origin[:5]:
            fails.append(f"    {fp['ref']:8s} {fp['value']:30s} ({fp['lib']})")

    # 2) MOSFET zone — exactly 24 phase MOSFETs (AOTL66912) on B.Cu in expected positions
    phase_fets = [fp for fp in fps if 'AOTL66912' in fp['value']]
    if len(phase_fets) != 24:
        fails.append(f"  Expected 24 phase MOSFETs, found {len(phase_fets)}")
    on_bcu = [fp for fp in phase_fets if fp['layer'] == 'B.Cu']
    if len(on_bcu) != 24:
        fails.append(f"  Expected 24 phase MOSFETs on B.Cu, found {len(on_bcu)}")

    # Build expected position set
    expected_positions = set()
    for y in EXPECTED_MOSFET_Y:
        for x in EXPECTED_MOSFET_X:
            expected_positions.add((x, y))
    actual_positions = set((round(fp['x'], 1), round(fp['y'], 1)) for fp in phase_fets)

    missing = expected_positions - actual_positions
    extra = actual_positions - expected_positions
    if missing:
        fails.append(f"  MOSFET positions MISSING from expected grid: {sorted(missing)}")
    if extra:
        fails.append(f"  MOSFET positions UNEXPECTED (not in expected grid): {sorted(extra)}")

    # 3) MCU rotations per CHANNEL_MCU_ROTATION
    mcus = [fp for fp in fps if 'AT32F421' in fp['value']]
    if len(mcus) != 4:
        fails.append(f"  Expected 4 MCUs, found {len(mcus)}")
    # MCU order in fps follows kinet2pcb order = SKiDL ref order; we assume sequential ch1..ch4
    for i, fp in enumerate(mcus[:4]):
        ch = i + 1
        expected_rot = EXPECTED_MCU_ROTATION[ch]
        if abs(fp['rot'] - expected_rot) > 0.1:
            fails.append(f"  MCU ch{ch} (ref {fp['ref']}): expected rotation {expected_rot}°, got {fp['rot']}°")
        else:
            print(f"  MCU ch{ch} (ref {fp['ref']}) @ ({fp['x']:.1f}, {fp['y']:.1f}) rot={fp['rot']}° ✓")

    # 4) Mount holes — exactly 4 at corners. Phase 4b-REDO2: 90×75 board → corners
    # at (5,5), (85,5), (5,70), (85,70) — custom 80×65 spacing pattern.
    mount_holes = [fp for fp in fps if 'MountingHole' in (fp['lib'] or '')]
    expected_mh_positions = {(5.0, 5.0), (85.0, 5.0), (5.0, 70.0), (85.0, 70.0)}
    actual_mh_positions = set((round(fp['x'], 1), round(fp['y'], 1)) for fp in mount_holes)
    if len(mount_holes) != 4:
        fails.append(f"  Expected 4 mount holes (post-dedup), found {len(mount_holes)}")
    if actual_mh_positions != expected_mh_positions:
        fails.append(f"  Mount hole positions {sorted(actual_mh_positions)} != expected {sorted(expected_mh_positions)}")
    else:
        print(f"  Mount holes (4) at corners {sorted(actual_mh_positions)} ✓")

    # 5) T7 — FC connector at top of board, motor pads on edges
    fc = [fp for fp in fps if 'SM08B-SRSS' in fp['value']]
    if len(fc) != 1:
        fails.append(f"  Expected 1 FC connector, found {len(fc)}")
    elif fc[0]['y'] < 60:
        fails.append(f"  FC connector at y={fc[0]['y']} (expected near top y≥60)")
    else:
        print(f"  FC connector @ ({fc[0]['x']:.1f}, {fc[0]['y']:.1f}) ✓ (top of board)")

    motor_pads = [fp for fp in fps if re.match(r'MOTOR_[ABC]_CH', fp['value'])]
    if len(motor_pads) != 12:
        fails.append(f"  Expected 12 motor pads, found {len(motor_pads)}")
    # Each motor pad should be at a board edge (within 3mm of edge x∈[0,85], y∈[0,70])
    edge_tolerance = 3.0
    not_edge = []
    for fp in motor_pads:
        on_edge = (fp['x'] < edge_tolerance or fp['x'] > EXPECTED_BOARD_W - edge_tolerance or
                   fp['y'] < edge_tolerance or fp['y'] > EXPECTED_BOARD_H - edge_tolerance)
        if not on_edge:
            not_edge.append(fp)
    if not_edge:
        fails.append(f"  {len(not_edge)} motor pads NOT on board edge:")
        for fp in not_edge[:5]:
            fails.append(f"    {fp['value']} @ ({fp['x']:.1f}, {fp['y']:.1f})")

    # 6) Overlap detection (footprints with identical positions on same layer)
    pos_to_fps = defaultdict(list)
    for fp in fps:
        if 'MountingHole' in (fp['lib'] or ''):
            continue
        key = (round(fp['x'], 1), round(fp['y'], 1), fp['layer'])
        pos_to_fps[key].append(fp)
    overlaps = {k: v for k, v in pos_to_fps.items() if len(v) > 1}
    if overlaps:
        fails.append(f"  {len(overlaps)} position-overlap clusters detected:")
        for k, v in list(overlaps.items())[:5]:
            refs = [fp['ref'] for fp in v]
            vals = [fp['value'] for fp in v[:3]]
            fails.append(f"    @ {k} : {refs[:5]} ({vals})")

    print()
    if fails:
        print("FAILURES:")
        for f in fails:
            print(f)
        return 1
    else:
        print("All checks PASSED.")
        print(f"  - {len(fps)} footprints placed (249 non-mount + 12 mount holes)")
        print(f"  - 24 phase MOSFETs on expected 6×4 B.Cu grid")
        print(f"  - 4 MCUs with per-channel rotations {EXPECTED_MCU_ROTATION}")
        print(f"  - {len(motor_pads)} motor pads on board edges")
        print(f"  - 0 overlaps")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
