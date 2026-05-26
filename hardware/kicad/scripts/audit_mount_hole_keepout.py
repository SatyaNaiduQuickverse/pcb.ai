#!/usr/bin/env python3
"""audit_mount_hole_keepout.py — G_M7 / G_M8 / G_M9 / G_M10 / G_M11 / G_M12 / G_M13

Class of mistake this prevents (Sai 2026-05-26 mandate after H5-H8 cinematic-mount
fiasco): adding/modifying a mechanical feature (mount hole, fixed connector, motor pad)
WITHOUT checking it against every nearby pre-existing fixed feature, every reserved
highway corridor, every defined subsystem zone, every other mount hole, and the
board outline.

The PR-#122/#136 incident: added 4 cinematic mounts H5-H8 at 75mm pitch. They:
  - Caused 2 marginal TP keep-out clearances (TP2 1.0mm, TP7 1.15mm vs 4mm KO)
  - Blocked the TLM/AUX bus highway corridor at x≈8-16 + x≈83-91
  - Required FOLLOW-UP PRs (#136 + this one) to resolve, instead of catching pre-merge

This audit runs 7 sub-gates exhaustively over every mount-hole-vs-* combination:

  G_M7  mount_hole_keepout      — every TP/connector/fiducial/motor_pad ≥ KO_RADIUS from every mount hole
  G_M8  highway_keepout         — every highway corridor clear of every mount-hole keep-out circle
  G_M9  mount_hole_in_zone      — every mount hole inside a defined subsystem zone (or explicit mount_hole_zone)
  G_M10 mount_hole_pattern      — mount-hole pattern matches a documented frame standard
                                  (90mm corner / 75mm cinematic / 30.5mm mini / custom-LOCKED)
  G_M11 mount_hole_symmetry     — mount holes come in symmetric pairs about x=50 and/or y=50 per R20
  G_M12 mount_hole_pair_spacing — no two mount holes < 10mm center-to-center (stress concentration)
  G_M13 mount_hole_edge_clear   — every mount hole ≥ 3mm from board edge (drill structural)

Exit code: 0 = all PASS, 1 = any violation.

Per [[feedback-sai-catches-are-samples]]: this audit treats every Sai-catch as a CLASS;
any new mechanical feature must pass ALL 7 sub-gates before merge.
"""
import os, sys, yaml, re, math

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LOCKFILE = os.path.join(REPO, "docs", "PHASE4V3_LOCKFILES", "mechanical_anchors.yaml")
INVARIANTS = os.path.join(REPO, "docs", "BOARD_INVARIANTS.md")

BOARD_W = 100.0
BOARD_H = 100.0
DEFAULT_KO_RADIUS = 4.0  # mm (M3 washer 6.5mm + 0.75mm component clearance)
MIN_PAIR_SPACING = 10.0  # mm (stress concentration limit)
MIN_EDGE_CLEAR = 3.0     # mm (drill-to-edge structural minimum)

# Documented frame standards (pitch_mm, family_name, valid_count)
FRAME_STANDARDS = [
    (90.0,  "90mm corner (custom large-board)",      4),
    (75.0,  "75mm cinematic FPV X-class",            4),
    (30.5,  "30.5×30.5mm mini-quad standard",        4),
    (20.0,  "20×20mm whoop/micro standard",          4),
    (36.0,  "36×36mm T-Motor V-class",               4),
]

def load_holes():
    d = yaml.safe_load(open(LOCKFILE))
    return [(m['ref'], float(m['pos'][0]), float(m['pos'][1]),
             float(m.get('keepout_radius_mm', DEFAULT_KO_RADIUS)))
            for m in d.get('mount_holes', [])]

def load_fixed_features():
    """Return list of (ref, x, y, kind) for every fixed feature."""
    d = yaml.safe_load(open(LOCKFILE))
    out = []
    for tp in d.get('test_points', []):
        out.append((tp['ref'], float(tp['pos'][0]), float(tp['pos'][1]), 'TP'))
    for c in d.get('connectors', []):
        if 'pos' in c:
            out.append((c['ref'], float(c['pos'][0]), float(c['pos'][1]), 'CONN'))
    for f in d.get('fiducials', []):
        out.append((f['ref'], float(f['pos'][0]), float(f['pos'][1]), 'FID'))
    for m in d.get('motor_pads', []):
        out.append((m['ref'], float(m['pos'][0]), float(m['pos'][1]), 'MOTOR'))
    return out

def load_highways():
    """Parse | Highway | x_min | y_min | x_max | y_max | rows."""
    text = open(INVARIANTS).read()
    out = []
    in_table = False
    for ln in text.splitlines():
        if "Highway | x_min | y_min | x_max | y_max" in ln:
            in_table = True; continue
        if in_table:
            if not ln.startswith('|') or '---' in ln[:5]:
                if not ln.strip(): break
                if '---' in ln[:5]: continue
                if not ln.startswith('|'): break
            cells = [c.strip() for c in ln.strip().strip('|').split('|')]
            if len(cells) >= 5:
                try:
                    out.append((cells[0], float(cells[1]), float(cells[2]),
                                          float(cells[3]), float(cells[4])))
                except ValueError:
                    continue
    return out

def load_zones():
    text = open(INVARIANTS).read()
    out = []
    in_table = False
    for ln in text.splitlines():
        if "Subsystem | x_min | y_min | x_max | y_max" in ln:
            in_table = True; continue
        if in_table:
            if not ln.startswith('|') or '---' in ln[:5]:
                if not ln.strip(): break
                if '---' in ln[:5]: continue
                if not ln.startswith('|'): break
            cells = [c.strip() for c in ln.strip().strip('|').split('|')]
            if len(cells) >= 5:
                try:
                    out.append((cells[0], float(cells[1]), float(cells[2]),
                                          float(cells[3]), float(cells[4])))
                except ValueError:
                    continue
    return out

def circle_rect_intersects(cx, cy, r, x0, y0, x1, y1):
    """True if circle (cx,cy,r) intersects rect (x0,y0,x1,y1)."""
    nx = max(x0, min(cx, x1))
    ny = max(y0, min(cy, y1))
    return (cx-nx)**2 + (cy-ny)**2 < r*r

def main():
    holes = load_holes()
    features = load_fixed_features()
    highways = load_highways()
    zones = load_zones()

    failures = []
    passed = []

    # G_M7: mount-hole vs fixed-feature keep-out
    g_m7_fail = []
    for fref, fx, fy, kind in features:
        for href, hx, hy, ko in holes:
            d = math.sqrt((fx-hx)**2 + (fy-hy)**2)
            if d < ko:
                g_m7_fail.append(f"  [HARD] {kind} {fref} ({fx},{fy}) ↔ {href} ({hx},{hy}): {d:.2f}mm < KO {ko}mm (margin {d-ko:.2f}mm)")
            elif d < ko + 1.0:
                g_m7_fail.append(f"  [MARG] {kind} {fref} ({fx},{fy}) ↔ {href} ({hx},{hy}): {d:.2f}mm (KO {ko}mm, margin only {d-ko:.2f}mm < 1.0mm)")
    if g_m7_fail:
        failures.append(("G_M7 mount_hole_keepout", g_m7_fail))
    else:
        passed.append("G_M7 mount_hole_keepout")

    # G_M8: highway vs mount-hole keep-out
    g_m8_fail = []
    for hwy_name, x0, y0, x1, y1 in highways:
        for href, hx, hy, ko in holes:
            if circle_rect_intersects(hx, hy, ko, x0, y0, x1, y1):
                g_m8_fail.append(f"  Highway '{hwy_name}' ({x0},{y0})-({x1},{y1}) intersects {href} KO circle ({hx},{hy}, r={ko})")
    if g_m8_fail:
        failures.append(("G_M8 highway_keepout", g_m8_fail))
    else:
        passed.append("G_M8 highway_keepout")

    # G_M9: every mount hole inside some defined zone (informational — corner mounts may be in zone boundary)
    g_m9_fail = []
    for href, hx, hy, ko in holes:
        found = [zn for zn, x0, y0, x1, y1 in zones if x0 <= hx <= x1 and y0 <= hy <= y1]
        if not found:
            g_m9_fail.append(f"  {href} ({hx},{hy}) not inside any defined zone (will fall in implicit board area)")
    if g_m9_fail:
        # Treat as warning for corner-pattern (informational), strict for others
        # For 90mm corner pattern, H1-H4 land on/near zone boundaries which is OK
        # Only escalate to failure if hole is INTERIOR (away from corners + edges)
        hard = [m for m in g_m9_fail if not any(
            ref in m and (px < 6 or px > 94 or py < 6 or py > 94)
            for ref, px, py, _ in holes)]
        if hard:
            failures.append(("G_M9 mount_hole_in_zone", hard))
        else:
            passed.append("G_M9 mount_hole_in_zone (corner mounts OK at edge)")
    else:
        passed.append("G_M9 mount_hole_in_zone")

    # G_M10: pattern matches documented frame standard
    n = len(holes)
    # Identify pitch (assume rectangular pattern)
    coords = sorted([(round(h[1],2), round(h[2],2)) for h in holes])
    pitch_x_set = set(c[0] for c in coords)
    pitch_y_set = set(c[1] for c in coords)
    if len(pitch_x_set) == 2 and len(pitch_y_set) == 2 and n == 4:
        xs = sorted(pitch_x_set); ys = sorted(pitch_y_set)
        px = xs[1] - xs[0]; py = ys[1] - ys[0]
        match = None
        for pitch, name, count in FRAME_STANDARDS:
            if abs(px - pitch) < 0.5 and abs(py - pitch) < 0.5 and count == n:
                match = name; break
        if match:
            passed.append(f"G_M10 mount_hole_pattern → {match} (pitch {px}×{py}mm)")
        else:
            failures.append(("G_M10 mount_hole_pattern",
                [f"  Pattern {px}×{py}mm × {n} holes matches NO documented frame standard. Add to FRAME_STANDARDS or change pitch."]))
    elif n == 4:
        # 4 holes but not rectangular pattern — needs explicit doc
        failures.append(("G_M10 mount_hole_pattern",
            [f"  4 holes but pattern not rectangular: {coords}. Document custom pattern in BOARD_INVARIANTS.md."]))
    elif n == 0:
        failures.append(("G_M10 mount_hole_pattern", ["  ZERO mount holes — board cannot be mounted to frame"]))
    else:
        # Multi-pattern (e.g., 8 holes = 2 patterns overlaid) — must be explicitly OK'd
        failures.append(("G_M10 mount_hole_pattern",
            [f"  {n} holes detected — multi-pattern not allowed without explicit [invariant-change] PR (Sai 2026-05-26)"]))

    # G_M11: symmetry pairs (R20)
    g_m11_fail = []
    by_mirror_x = {}
    for href, hx, hy, ko in holes:
        mx = round(100.0 - hx, 2)
        by_mirror_x.setdefault((mx, round(hy,2)), []).append(href)
    for href, hx, hy, ko in holes:
        key = (round(hx,2), round(hy,2))
        if key not in by_mirror_x:
            g_m11_fail.append(f"  {href} ({hx},{hy}) has no mirror_X(50) partner")
    if g_m11_fail:
        failures.append(("G_M11 mount_hole_symmetry", g_m11_fail))
    else:
        passed.append("G_M11 mount_hole_symmetry")

    # G_M12: mount-hole pair spacing >= 10mm
    g_m12_fail = []
    for i in range(len(holes)):
        for j in range(i+1, len(holes)):
            r1, x1, y1, _ = holes[i]; r2, x2, y2, _ = holes[j]
            d = math.sqrt((x1-x2)**2 + (y1-y2)**2)
            if d < MIN_PAIR_SPACING:
                g_m12_fail.append(f"  {r1}↔{r2}: {d:.2f}mm < {MIN_PAIR_SPACING}mm (stress concentration)")
    if g_m12_fail:
        failures.append(("G_M12 mount_hole_pair_spacing", g_m12_fail))
    else:
        passed.append("G_M12 mount_hole_pair_spacing")

    # G_M13: edge clearance
    g_m13_fail = []
    for href, hx, hy, ko in holes:
        e = min(hx, BOARD_W - hx, hy, BOARD_H - hy)
        if e < MIN_EDGE_CLEAR:
            g_m13_fail.append(f"  {href} ({hx},{hy}): {e:.2f}mm from nearest edge < {MIN_EDGE_CLEAR}mm")
    if g_m13_fail:
        failures.append(("G_M13 mount_hole_edge_clear", g_m13_fail))
    else:
        passed.append("G_M13 mount_hole_edge_clear")

    print("=" * 70)
    print(f"audit_mount_hole_keepout.py — {len(holes)} mount holes, {len(features)} fixed features, {len(highways)} highways, {len(zones)} zones")
    print("=" * 70)
    for g in passed:
        print(f"  ✅ {g}")
    if failures:
        print()
        for g, fails in failures:
            print(f"  ❌ {g}:")
            for f in fails:
                print(f)
        print()
        print(f"FAIL — {len(failures)} sub-gate(s) violated")
        return 1
    print()
    print(f"PASS — all {len(passed)} sub-gate(s) green")
    return 0

if __name__ == "__main__":
    sys.exit(main())
