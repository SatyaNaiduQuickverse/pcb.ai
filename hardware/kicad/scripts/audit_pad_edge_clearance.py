#!/usr/bin/env python3
"""audit_pad_edge_clearance.py — G_M14 board-edge pad clearance audit.

Class of mistake this gate prevents (master self-caught 2026-05-26 after my own
PR #137 created TP2 OFF-BOARD-PAD G17 fail):

  My PR #137 moved TP2 from (5,90) -> (2,89) to gain mount-hole H1 clearance.
  But TP2 has footprint TestPoint_Pad_D4.0mm (4mm diameter pad, radius 2mm).
  At center (2,89), the pad bbox extends from x=0 to x=4 — flush against board
  edge at x=0! This caused G17 board-edge keepout fail + G5 OFF-BOARD-PAD fail.

  My G_M7-M13 mount-hole audits added in same PR check pad-vs-mount-hole and
  highway-vs-mount-hole, but NOTHING checked pad-vs-board-edge. Same class of
  mistake (foundation feature placed without checking ALL surrounding constraints).

This audit closes the gap: every fixed pad (TP, connector, fiducial, motor pad)
must have its OUTER BBOX (center ± pad_size/2) ≥ MIN_PAD_EDGE_CLEAR from the
board outline. Default 0.5mm (standard fab DRC). Configurable per pad footprint.

Also checks that no pad CENTER is outside the board outline (0,0)-(BOARD_W,BOARD_H).

Exit 0 = PASS, 1 = FAIL.

Per [[feedback-codify-not-patch]] + [[feedback-sai-catches-are-samples]]: my own
mistake becomes a permanent gate so this class never recurs.
"""
import os, sys, yaml

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LOCKFILE = os.path.join(REPO, "docs", "PHASE4V3_LOCKFILES", "mechanical_anchors.yaml")

BOARD_W = 100.0
BOARD_H = 100.0
MIN_PAD_EDGE_CLEAR = 0.5  # mm (fab DRC default; many fabs require ≥0.3mm)

# Pad size lookup by footprint name (radius in mm — half of diameter/longest-side).
# Conservative: use largest bbox dimension.
PAD_SIZES = {
    "TestPoint_Pad_D4.0mm":  2.0,
    "TestPoint_Pad_D3.0mm":  1.5,
    "TestPoint_Pad_D2.5mm":  1.25,
    "TestPoint_Pad_D1.5mm":  0.75,
    "TestPoint_Pad_D1.0mm":  0.5,
    "Fiducial_1mm_Mask2mm":  1.0,   # mask opening determines reflow-safe area
    "ESCMotorPad_4x4mm_5via": 2.0,  # 4×4mm square; half-diag = 2.83mm but use 2 for axis-aligned
    "MountingHole_3.2mm_M3": 1.6,
    "BAT_PAD_4mm":           2.0,   # custom solder pad
    "BAT_PAD_5mm":           2.5,
    # JST + headers: variable; use conservative 1.5mm
    "Conn_JST_PH_2x05":      1.5,
    "Conn_JST_GH_2x07":      1.5,
}

def pad_extent(fp_name, fallback=1.5):
    return PAD_SIZES.get(fp_name, fallback)

def main():
    d = yaml.safe_load(open(LOCKFILE))
    fails = []
    margins = []

    def check(ref, x, y, fp_name, kind):
        r = pad_extent(fp_name)
        # bbox: (x-r, y-r) to (x+r, y+r)
        x0 = x - r; y0 = y - r; x1 = x + r; y1 = y + r
        edge_clears = [x0, BOARD_W - x1, y0, BOARD_H - y1]
        worst = min(edge_clears)
        if worst < 0:
            fails.append(f"  [HARD] {kind} {ref} ({x},{y}) fp={fp_name}: bbox extends OUTSIDE board "
                         f"(bbox=({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f}); worst clear={worst:.2f}mm)")
        elif worst < MIN_PAD_EDGE_CLEAR:
            fails.append(f"  [HARD] {kind} {ref} ({x},{y}) fp={fp_name}: bbox clear {worst:.2f}mm < {MIN_PAD_EDGE_CLEAR}mm min")
        elif worst < MIN_PAD_EDGE_CLEAR + 1.0:
            margins.append(f"  [MARG] {kind} {ref} ({x},{y}) fp={fp_name}: bbox clear {worst:.2f}mm (min {MIN_PAD_EDGE_CLEAR}mm; margin < 1mm)")

    for tp in d.get('test_points', []):
        check(tp['ref'], float(tp['pos'][0]), float(tp['pos'][1]),
              tp.get('footprint', '?'), 'TP')
    for c in d.get('connectors', []):
        if 'pos' in c:
            check(c['ref'], float(c['pos'][0]), float(c['pos'][1]),
                  c.get('footprint', '?'), 'CONN')
    for f in d.get('fiducials', []):
        check(f['ref'], float(f['pos'][0]), float(f['pos'][1]),
              f.get('footprint', '?'), 'FID')
    for m in d.get('motor_pads', []):
        check(m['ref'], float(m['pos'][0]), float(m['pos'][1]),
              m.get('footprint', '?'), 'MOTOR')
    for m in d.get('mount_holes', []):
        check(m['ref'], float(m['pos'][0]), float(m['pos'][1]),
              m.get('footprint', '?'), 'MOUNT')

    print("=" * 70)
    print(f"audit_pad_edge_clearance.py G_M14 — board {BOARD_W}×{BOARD_H}mm, min edge clear {MIN_PAD_EDGE_CLEAR}mm")
    print("=" * 70)
    if margins:
        print()
        print("MARGINS (within 1mm of threshold):")
        for m in margins: print(m)
    if fails:
        print()
        print(f"FAIL — {len(fails)} pad(s) violate edge clearance:")
        for f in fails: print(f)
        return 1
    print()
    print("PASS — all fixed pads clear board edge ≥ threshold")
    return 0

if __name__ == "__main__":
    sys.exit(main())
