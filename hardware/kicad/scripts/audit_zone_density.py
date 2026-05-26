#!/usr/bin/env python3
"""audit_zone_density.py — G_PP20 per-zone density budget audit.

Per Sai 2026-05-26: "you have to do placement that way you get headroom to edit".

Verifies each subsystem zone's component-area / routing-reserve / headroom
fractions are within parametric budget:
  - max_component_area_fraction (default 55%)
  - min_routing_reserve_fraction (≥20%)
  - min_headroom_fraction (≥25%)

Reports per-zone breakdown. FAILS if any zone exceeds component budget.
"""
import os, re, sys

def main():
    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not available", file=sys.stderr); return 1

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from parametric_placement import BoardParameters, headroom_per_zone

    pcb_path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
    board = pcbnew.LoadBoard(pcb_path)
    mm = 1000000.0
    p = BoardParameters()

    # Parse zones from BOARD_INVARIANTS.md
    inv = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "..", "..", "docs", "BOARD_INVARIANTS.md")).read()
    zones = []
    in_table = False
    for ln in inv.splitlines():
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
                    zones.append((cells[0], float(cells[1]), float(cells[2]),
                                              float(cells[3]), float(cells[4])))
                except ValueError:
                    continue

    # Sum component bbox area per zone (both layers)
    zone_areas = {z[0]: 0.0 for z in zones}
    for fp in board.GetFootprints():
        pos = fp.GetPosition()
        x = pos.x/mm; y = pos.y/mm
        if x < -5 or x > 200 or y < -5 or y > 200: continue
        bbox = fp.GetBoundingBox(False, False)
        area = (bbox.GetWidth()/mm) * (bbox.GetHeight()/mm)
        for zname, x0, y0, x1, y1 in zones:
            if x0 <= x <= x1 and y0 <= y <= y1:
                zone_areas[zname] += area
                break  # first zone match wins

    print("=" * 70)
    print(f"audit_zone_density.py G_PP20 — per-zone density budget (≤{p.max_component_area_fraction*100:.0f}% comp, ≥{p.min_routing_reserve_fraction*100:.0f}% route, ≥{p.min_headroom_fraction*100:.0f}% headroom)")
    print("=" * 70)
    fails = []
    print(f"  {'Zone':<35} {'Area':>8} {'CompArea':>10} {'CompPct':>8} {'Status':>10}")
    for zname, x0, y0, x1, y1 in zones:
        h = headroom_per_zone((x0,y0,x1,y1), zone_areas[zname], p)
        status = "OVER" if h['over_budget'] else "OK"
        if h['over_budget']: fails.append((zname, h))
        print(f"  {zname:<35} {h['zone_area_mm2']:>8.1f} {h['component_area_mm2']:>10.1f} {h['component_fraction']*100:>7.1f}% {status:>10}")

    if fails:
        print()
        print(f"  ❌ FAIL — {len(fails)} zone(s) over component-area budget")
        return 1
    print()
    print(f"  ✅ PASS — all zones within density budget")
    return 0

if __name__ == "__main__":
    sys.exit(main())
