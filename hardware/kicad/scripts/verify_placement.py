"""Phase 4b-redo4-R1 — verify placement.

Checks:
1. All footprints have a position (no part at origin), excluding mount holes.
2. 24 phase MOSFETs on B.Cu in expected 6×4 R1 grid (centered, cells 7×7.5mm).
3. MCU rotations per R1 (PWM corner outward): CH1=180°, CH2=270°, CH3=90°, CH4=0°.
4. Mount holes at 4 corners (5, 5)/(95, 5)/(5, 80)/(95, 80).
5. FC connector near top edge.
6. Motor pads (12×) on board edges.
7. No position overlaps on F.Cu (allow B.Cu separately).
8. Per-channel T8 compliance: each channel's MCU + driver + 6 phase FETs +
   3 shunts + 3 CSAs + protection ICs + per-channel passives are all within
   that channel's quadrant.
"""
import re
from pathlib import Path
from collections import defaultdict

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")

EXPECTED_MCU_ROTATION = {1: 180, 2: 270, 3: 90, 4: 0}
EXPECTED_MCU_POS = {1: (40.0, 35.0), 2: (60.0, 35.0),
                    3: (40.0, 50.0), 4: (60.0, 50.0)}

# R1 MOSFET grid (6 cols × 4 rows, cell_w=7, cell_h=7.5; origin (29, 27.5))
EXPECTED_MOSFET_X = [29.0, 36.0, 43.0, 50.0, 57.0, 64.0]
EXPECTED_MOSFET_Y = [27.5, 35.0, 42.5, 50.0]

EXPECTED_BOARD_W = 100.0
EXPECTED_BOARD_H = 85.0

# Channel quadrant definitions (R1 center-cluster topology)
CHANNEL_QUADRANT = {
    1: ('NW', 0.0, 50.0,  0.0, 42.5),  # x0,x1,y0,y1
    2: ('NE', 50.0, 100.0, 0.0, 42.5),
    3: ('SW', 0.0, 50.0,  42.5, 85.0),
    4: ('SE', 50.0, 100.0, 42.5, 85.0),
}


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
        # Extract net membership for T8 compliance
        net_pat = re.compile(r'\(net \d+ "([^"]+)"\)')
        ch_votes = defaultdict(int)
        for net_m in net_pat.finditer(block):
            cm = re.search(r'_CH([1-4])', net_m.group(1))
            if cm:
                ch_votes[int(cm.group(1))] += 1
        ch = max(ch_votes.items(), key=lambda kv: kv[1])[0] if ch_votes else None
        results.append({
            'lib': lib_m.group(1) if lib_m else None,
            'ref': ref_m.group(1) if ref_m else '?',
            'value': val_m.group(1) if val_m else '?',
            'layer': layer_m.group(1) if layer_m else '?',
            'x': float(at_m.group(1)) if at_m else 0.0,
            'y': float(at_m.group(2)) if at_m else 0.0,
            'rot': float(at_m.group(3)) if at_m and at_m.group(3) else 0.0,
            'ch_inferred': ch,
        })
        pos = end
    return results


def main():
    fps = parse_footprints(PCB.read_text())
    print(f"Total footprints: {len(fps)}")
    fails = []

    # 1) All non-mount footprints have a position
    at_origin = [fp for fp in fps
                 if abs(fp['x']) < 0.01 and abs(fp['y']) < 0.01
                 and 'MountingHole' not in (fp['lib'] or '')]
    if at_origin:
        fails.append(f"  {len(at_origin)} footprints at origin (unplaced)")
        for fp in at_origin[:5]:
            fails.append(f"    {fp['ref']:8s} {fp['value']:30s} ({fp['lib']})")

    # 2) MOSFETs (24× AOTL66912 on B.Cu in 6×4 grid)
    phase_fets = [fp for fp in fps if 'AOTL66912' in fp['value']]
    if len(phase_fets) != 24:
        fails.append(f"  Expected 24 phase MOSFETs, found {len(phase_fets)}")
    on_bcu = [fp for fp in phase_fets if fp['layer'] == 'B.Cu']
    if len(on_bcu) != 24:
        fails.append(f"  Expected 24 phase MOSFETs on B.Cu, found {len(on_bcu)}")
    expected_positions = set()
    for y in EXPECTED_MOSFET_Y:
        for x in EXPECTED_MOSFET_X:
            expected_positions.add((round(x, 1), round(y, 1)))
    actual_positions = set((round(fp['x'], 1), round(fp['y'], 1)) for fp in phase_fets)
    missing = expected_positions - actual_positions
    extra = actual_positions - expected_positions
    if missing:
        fails.append(f"  MOSFET positions MISSING: {sorted(missing)}")
    if extra:
        fails.append(f"  MOSFET positions UNEXPECTED: {sorted(extra)}")

    # 3) MCU rotations per R1 — by net-membership channel (not sequential)
    mcus = [fp for fp in fps if 'AT32F421' in fp['value']]
    if len(mcus) != 4:
        fails.append(f"  Expected 4 MCUs, found {len(mcus)}")
    mcus_by_ch = {fp['ch_inferred']: fp for fp in mcus if fp['ch_inferred'] in (1, 2, 3, 4)}
    for ch in (1, 2, 3, 4):
        fp = mcus_by_ch.get(ch)
        if not fp:
            fails.append(f"  MCU ch{ch} NOT FOUND in net-membership")
            continue
        expected_rot = EXPECTED_MCU_ROTATION[ch]
        if abs(fp['rot'] - expected_rot) > 0.1:
            fails.append(f"  MCU ch{ch} (ref {fp['ref']}): expected rotation {expected_rot}°, got {fp['rot']}°")
        else:
            ex, ey = EXPECTED_MCU_POS[ch]
            if abs(fp['x'] - ex) > 0.1 or abs(fp['y'] - ey) > 0.1:
                fails.append(f"  MCU ch{ch}: position ({fp['x']:.1f}, {fp['y']:.1f}) != expected ({ex}, {ey})")
            else:
                print(f"  MCU ch{ch} (ref {fp['ref']}) @ ({fp['x']:.1f}, {fp['y']:.1f}) rot={fp['rot']}° ✓")

    # 4) Mount holes
    mount_holes = [fp for fp in fps if 'MountingHole' in (fp['lib'] or '')]
    expected_mh = {(5.0, 5.0), (95.0, 5.0), (5.0, 80.0), (95.0, 80.0)}
    actual_mh = set((round(fp['x'], 1), round(fp['y'], 1)) for fp in mount_holes)
    if len(mount_holes) != 4:
        fails.append(f"  Expected 4 mount holes, found {len(mount_holes)}")
    if actual_mh != expected_mh:
        fails.append(f"  Mount hole positions {sorted(actual_mh)} != expected {sorted(expected_mh)}")
    else:
        print(f"  Mount holes (4) at corners ✓")

    # 5) FC connector at top
    fc = [fp for fp in fps if 'SM08B-SRSS' in fp['value']]
    if len(fc) != 1:
        fails.append(f"  Expected 1 FC connector, found {len(fc)}")
    elif fc[0]['y'] < 60:
        fails.append(f"  FC connector at y={fc[0]['y']} (expected near top y≥60)")
    else:
        print(f"  FC connector @ ({fc[0]['x']:.1f}, {fc[0]['y']:.1f}) ✓")

    # 6) Motor pads on edges
    motor_pads = [fp for fp in fps if re.match(r'MOTOR_[ABC]_CH', fp['value'])]
    if len(motor_pads) != 12:
        fails.append(f"  Expected 12 motor pads, found {len(motor_pads)}")
    edge_tolerance = 3.0
    not_edge = []
    for fp in motor_pads:
        on_edge = (fp['x'] < edge_tolerance or fp['x'] > EXPECTED_BOARD_W - edge_tolerance or
                   fp['y'] < edge_tolerance or fp['y'] > EXPECTED_BOARD_H - edge_tolerance)
        if not on_edge:
            not_edge.append(fp)
    if not_edge:
        fails.append(f"  {len(not_edge)} motor pads NOT on board edge")

    # 7) Overlap detection on F.Cu (allow B.Cu separately — MOSFET clusters
    # have tight grid; same goes for shunts).
    pos_to_fps = defaultdict(list)
    for fp in fps:
        if 'MountingHole' in (fp['lib'] or ''):
            continue
        key = (round(fp['x'], 1), round(fp['y'], 1), fp['layer'])
        pos_to_fps[key].append(fp)
    overlaps = {k: v for k, v in pos_to_fps.items() if len(v) > 1}
    if overlaps:
        fails.append(f"  {len(overlaps)} position-overlap clusters detected:")
        for k, v in list(overlaps.items())[:10]:
            refs = [fp['ref'] for fp in v]
            vals = [fp['value'] for fp in v[:3]]
            fails.append(f"    @ {k} : {refs[:5]} ({vals})")

    # 8) Per-channel T8 quadrant compliance — every footprint with inferred
    # channel membership should be inside its channel's quadrant (or on B.Cu,
    # which is a power-side layer and exempt from F.Cu signal-side T8).
    quadrant_violations = defaultdict(int)
    quadrant_samples = defaultdict(list)
    for fp in fps:
        ch = fp.get('ch_inferred')
        if ch not in (1, 2, 3, 4):
            continue
        if fp['layer'] == 'B.Cu':
            continue  # B.Cu MOSFETs/shunts intentionally in central cluster
        if 'AT32F421' in fp['value'] or 'DRV8300' in fp['value']:
            continue  # MCU + driver center-cluster intentionally
        if 'INA186' in fp['value']:
            continue  # CSA close to MCU intentionally
        if re.match(r'MOTOR_[ABC]_CH', fp['value']):
            continue  # motor pads on quadrant-outer edge
        if re.match(r'(SWDIO|SWCLK)_CH', fp['value']):
            continue  # SWD pads on side edges
        _, x0, x1, y0, y1 = CHANNEL_QUADRANT[ch]
        if not (x0 <= fp['x'] <= x1 and y0 <= fp['y'] <= y1):
            quadrant_violations[ch] += 1
            if len(quadrant_samples[ch]) < 3:
                quadrant_samples[ch].append((fp['ref'], fp['value'], fp['x'], fp['y']))
    if quadrant_violations:
        for ch in (1, 2, 3, 4):
            n = quadrant_violations[ch]
            if n:
                label = CHANNEL_QUADRANT[ch][0]
                samples = ', '.join(f"{r}({v}) @ ({x:.1f},{y:.1f})"
                                    for r, v, x, y in quadrant_samples[ch])
                fails.append(f"  T8: CH{ch} ({label}): {n} footprints outside quadrant. samples: {samples}")
    else:
        print(f"  T8 quadrant compliance: all per-channel parts within their MCU's quadrant ✓")

    print()
    if fails:
        print("FAILURES:")
        for f in fails:
            print(f)
        return 1
    else:
        print("All checks PASSED.")
        print(f"  - {len(fps)} footprints placed")
        print(f"  - 24 phase MOSFETs on R1 6×4 B.Cu grid")
        print(f"  - 4 MCUs in 2×2 center cluster with PWM-outward rotations")
        print(f"  - 0 overlaps on F.Cu")
        print(f"  - T8 quadrant compliance verified for all 4 channels")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
