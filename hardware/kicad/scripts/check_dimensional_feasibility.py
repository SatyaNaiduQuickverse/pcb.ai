#!/usr/bin/env python3
"""check_dimensional_feasibility.py — PRE-PLACEMENT gate per master 2026-05-23 R23 dispatch.

Catches the dispatch-error class master ran into with Y=17 spec (assumed FET half-Y=2.5mm,
actual 5.4mm). BEFORE any placement step, this script asks: given the requested
target geometry (FET row pitch, channel quadrant boundaries, S1/S6 strips, JLC clearance
rules), is the layout DIMENSIONALLY POSSIBLE?

Inputs:
  - Component bbox dimensions (look up from KiCad footprint library; assume nominal
    for now: AOTL66912 TO-263 16.15×10.8, BSC014N06NS SuperSO8 5.0×6.0, etc.)
  - Requested target coords (passed in via TARGET_GEOMETRY)
  - JLC clearance rule: 1mm pad-pad minimum
  - Board outline: 100×95 mm

Output: PASS/FAIL with concrete deltas (how much short / how much margin).

Run: python3 check_dimensional_feasibility.py
"""
import sys

# Component bbox dimensions (mm) — half-extents (x_half, y_half)
COMPONENT_BBOX = {
    'AOTL66912': (8.08, 5.40),   # TO-263 H-FET, channel-FET pad bbox
    'BSC014N06NS': (3.00, 3.50), # SuperSO8 5×6 rev-pol FET (S1)
    'ACS770ECB-200B': (9.80, 13.50),  # Allegro CB_PFF Hall, body 19.6×27mm
    'AT32F421K8T7': (3.50, 3.50), # LQFP-32 MCU (J18)
    'DRV8300DRGER': (2.00, 2.00), # HVQFN-24 gate driver (J19)
    'TPS54560': (3.0, 3.0),   # buck IC SOIC-8
    'AOZ1284': (3.0, 3.0),    # buck IC SOIC-8
    '0402': (0.8, 0.4),       # generic 0402 R/C
    '0805': (1.0, 0.625),     # 0805 ferrite L
    '2512': (3.2, 1.6),       # 2512 R (shunt)
}

# Locked target geometry (master A4-redo dispatch 2026-05-23)
TARGET_GEOMETRY = {
    'board_w': 100.0,
    'board_h': 100.0,                         # PR-A4-redo Option-A refined (was 95)
    'symmetry_y': 50.0,                       # mirror about board center Y=50
    'symmetry_x': 50.0,
    's1_zone_y_max': 13.0,
    's6_zone_y_min': 87.0,                    # S6 strip shifted to Y=87-100
    'ch_row_pitch': 12.0,
    'ch_x_pitch': 18.0,
    'jlc_clearance': 1.0,
    'ch_top_rows_y': [56.0, 68.0, 80.0],      # CH1/2
    'ch_bot_rows_y': [20.0, 32.0, 44.0],      # CH3/4 (mirror about Y=50)
    's1_fet_y': 7.5,
}


def check_ch_row_clearance_s1():
    """CH3/4 bottom-row clearance from S1 strip top edge."""
    fet_h = COMPONENT_BBOX['AOTL66912'][1]
    s1_fet_h = COMPONENT_BBOX['BSC014N06NS'][1]
    s1_y = TARGET_GEOMETRY['s1_fet_y']
    s1_top = s1_y + s1_fet_h
    ch_bot = min(TARGET_GEOMETRY['ch_bot_rows_y'])
    ch_bot_edge = ch_bot - fet_h
    gap = ch_bot_edge - s1_top
    ok = gap >= TARGET_GEOMETRY['jlc_clearance']
    status = "PASS" if ok else "FAIL"
    print(f"[CH3/4 ↔ S1] S1 FET top={s1_top:.2f}, CH bot edge={ch_bot_edge:.2f}, gap={gap:.2f}mm (need ≥{TARGET_GEOMETRY['jlc_clearance']}mm) — {status}")
    return ok


def check_ch_ch_clearance():
    """CH1/2 bottom-row clearance from CH3/4 top-row (CH-CH boundary at symmetry axis)."""
    fet_h = COMPONENT_BBOX['AOTL66912'][1]
    ch_top_bot = min(TARGET_GEOMETRY['ch_top_rows_y'])
    ch_bot_top = max(TARGET_GEOMETRY['ch_bot_rows_y'])
    top_edge_of_bot_ch = ch_bot_top + fet_h
    bot_edge_of_top_ch = ch_top_bot - fet_h
    gap = bot_edge_of_top_ch - top_edge_of_bot_ch
    ok = gap >= TARGET_GEOMETRY['jlc_clearance']
    status = "PASS" if ok else "FAIL"
    print(f"[CH1/2 ↔ CH3/4] top of CH3/4={top_edge_of_bot_ch:.2f}, bot of CH1/2={bot_edge_of_top_ch:.2f}, gap={gap:.2f}mm — {status}")
    return ok


def check_ch_row_clearance_s6():
    """CH1/2 top-row clearance from S6 strip bottom."""
    fet_h = COMPONENT_BBOX['AOTL66912'][1]
    ch_top = max(TARGET_GEOMETRY['ch_top_rows_y'])
    ch_top_edge = ch_top + fet_h
    s6 = TARGET_GEOMETRY['s6_zone_y_min']
    gap = s6 - ch_top_edge
    ok = gap >= TARGET_GEOMETRY['jlc_clearance']
    status = "PASS" if ok else "FAIL"
    print(f"[CH1/2 ↔ S6] CH top edge={ch_top_edge:.2f}, S6 zone start={s6}, gap={gap:.2f}mm — {status}")
    return ok


def check_symmetry_y_split():
    """CH1/2 top rows mirror_Y of CH3/4 bottom rows about Y=47.5."""
    syy = TARGET_GEOMETRY['symmetry_y']
    top = sorted(TARGET_GEOMETRY['ch_top_rows_y'])
    bot = sorted(TARGET_GEOMETRY['ch_bot_rows_y'])
    fails = []
    for t, b in zip(top, bot[::-1]):
        expected_t = 2 * syy - b
        if abs(t - expected_t) > 0.01:
            fails.append((t, b, expected_t))
    status = "PASS" if not fails else "FAIL"
    print(f"[Y-symmetry] top rows {top} ↔ bot rows {bot} about {syy} — {status}")
    for t, b, e in fails:
        print(f"  Top={t} expected {e} (mirror of bot={b}) — diff {abs(t-e):.2f}mm")
    return not fails


def check_row_pitch():
    """All channel rows at exactly P=12."""
    p = TARGET_GEOMETRY['ch_row_pitch']
    ok = True
    for label, rows in [('CH1/2', TARGET_GEOMETRY['ch_top_rows_y']),
                        ('CH3/4', TARGET_GEOMETRY['ch_bot_rows_y'])]:
        rs = sorted(rows)
        deltas = [rs[i+1] - rs[i] for i in range(len(rs)-1)]
        for d in deltas:
            if abs(d - p) > 0.01:
                ok = False
                print(f"[Row pitch] {label} {rs}: delta {d:.2f}mm ≠ P={p}")
    if ok:
        print(f"[Row pitch] All channels P={p}mm ✓ — PASS")
    return ok


def check_board_bounds():
    """All FETs within board outline + margin."""
    w, h = TARGET_GEOMETRY['board_w'], TARGET_GEOMETRY['board_h']
    fet_h = COMPONENT_BBOX['AOTL66912'][1]
    bot_min = min(TARGET_GEOMETRY['ch_bot_rows_y']) - fet_h
    top_max = max(TARGET_GEOMETRY['ch_top_rows_y']) + fet_h
    ok = bot_min >= 0 and top_max <= h
    status = "PASS" if ok else "FAIL"
    print(f"[Board bounds] FET y-range [{bot_min:.2f}, {top_max:.2f}] vs board [0, {h}] — {status}")
    return ok


def main():
    print("=== Pre-placement dimensional feasibility check ===")
    print(f"Board: {TARGET_GEOMETRY['board_w']}×{TARGET_GEOMETRY['board_h']} mm")
    print(f"FET package half-bbox: {COMPONENT_BBOX['AOTL66912']} (AOTL66912 TO-263)")
    print(f"JLC clearance: ≥{TARGET_GEOMETRY['jlc_clearance']}mm pad-pad\n")
    checks = [
        check_row_pitch(),
        check_symmetry_y_split(),
        check_ch_row_clearance_s1(),
        check_ch_ch_clearance(),
        check_ch_row_clearance_s6(),
        check_board_bounds(),
    ]
    if all(checks):
        print("\n=== OVERALL: PASS — geometry is dimensionally feasible ===")
        sys.exit(0)
    else:
        print(f"\n=== OVERALL: FAIL — {checks.count(False)} dimensional issue(s) ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
