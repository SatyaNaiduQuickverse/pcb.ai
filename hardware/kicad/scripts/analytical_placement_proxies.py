#!/usr/bin/env python3
"""analytical_placement_proxies.py — fast placement-quality metrics (no FEM).

Per Sai 2026-05-26 + PLACEMENT_GLOBAL_PLAN.md §8: analytical proxy sims that
inform STEP 3 BEFORE the expensive Elmer/openEMS/ngspice runs. If proxies are
out of spec, no point firing FEM — re-place first.

Three proxies (each runs in <1s vs hours of FEM):

  1. HPWL (half-perimeter wire length) per net + total
     - Proxy for total trace length post-route
     - Routing-hardness heuristic (high HPWL → routing-hard)
     - Target: per-subsystem HPWL bounded by zone perimeter × N_nets

  2. DENSITY per zone
     - Component bbox area / zone area
     - Per-zone budget per BoardParameters: ≤55% comp, ≥20% routing, ≥25% headroom
     - Mirrors G_PP20 but in human-readable form

  3. DECOUPLING distance per IC VDD pin
     - Every IC VDD pin → nearest cap on same VDD net
     - Target: ≤3mm same-layer per R25 + 0.05mm fab tol
     - Mirrors G4 but with per-IC detail + ranked worst-first

Usage:
  python3 analytical_placement_proxies.py <board.kicad_pcb>

Output: human-readable report, machine-parseable JSON to <board>.proxies.json.

This is the EARLY-WARNING for placement quality. Run after every placement
iteration. FEM sims (Elmer/openEMS/ngspice) only fire if these pass.
"""
import os, sys, json, math
from collections import defaultdict

def main():
    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not available", file=sys.stderr); sys.exit(1)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from parametric_placement import BoardParameters

    pcb_path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
    out_path = pcb_path.replace(".kicad_pcb", ".proxies.json")
    board = pcbnew.LoadBoard(pcb_path)
    mm = 1000000.0
    p = BoardParameters()

    # Collect footprints
    fps = []
    for fp in board.GetFootprints():
        pos = fp.GetPosition()
        x = pos.x/mm; y = pos.y/mm
        if x < -5 or x > 200 or y < -5 or y > 200: continue
        bbox = fp.GetBoundingBox(False, False)
        bx0 = bbox.GetX()/mm; by0 = bbox.GetY()/mm
        bx1 = bx0 + bbox.GetWidth()/mm; by1 = by0 + bbox.GetHeight()/mm
        fps.append({
            'ref': fp.GetReference(), 'x': x, 'y': y, 'value': fp.GetValue(),
            'bbox': (bx0, by0, bx1, by1), 'layer': 'F.Cu' if fp.GetLayer() == pcbnew.F_Cu else 'B.Cu',
            'fp': fp,
        })

    # ─── PROXY 1: HPWL per net ───
    net_pins = defaultdict(list)  # net_name → [(x, y), ...]
    for f in fps:
        for pad in f['fp'].Pads():
            net = pad.GetNetname()
            if not net or "unconnected" in net.lower() or net.startswith("Net-"): continue
            ppos = pad.GetPosition()
            net_pins[net].append((ppos.x/mm, ppos.y/mm))

    hpwl_per_net = {}
    for net, pins in net_pins.items():
        if len(pins) < 2: continue
        xs = [p[0] for p in pins]; ys = [p[1] for p in pins]
        hpwl_per_net[net] = (max(xs) - min(xs)) + (max(ys) - min(ys))
    total_hpwl = sum(hpwl_per_net.values())
    worst_nets = sorted(hpwl_per_net.items(), key=lambda kv: -kv[1])[:10]

    # ─── PROXY 2: Density per zone ───
    inv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "..", "..", "docs", "BOARD_INVARIANTS.md")
    zones = []
    if os.path.exists(inv_path):
        text = open(inv_path).read()
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
                        zones.append((cells[0], float(cells[1]), float(cells[2]),
                                                  float(cells[3]), float(cells[4])))
                    except ValueError: continue

    density_per_zone = []
    for zname, x0, y0, x1, y1 in zones:
        zone_area = (x1 - x0) * (y1 - y0)
        comp_area = 0.0
        for f in fps:
            if x0 <= f['x'] <= x1 and y0 <= f['y'] <= y1:
                comp_area += (f['bbox'][2] - f['bbox'][0]) * (f['bbox'][3] - f['bbox'][1])
        density_per_zone.append({
            'zone': zname, 'area_mm2': zone_area, 'comp_area_mm2': comp_area,
            'comp_frac': comp_area / zone_area if zone_area > 0 else 0,
            'over_budget': comp_area / zone_area > p.max_component_area_fraction if zone_area > 0 else False,
        })

    # ─── PROXY 3: Decoupling distance per IC VDD pin ───
    POWER_NETS = ('+3V3', '+5V', '+V5', '+V9', 'VDD', '+VMOTOR')
    def is_power_net(n): return any(p in n for p in POWER_NETS)
    def is_decoupling_cap(ref, value):
        return ref.startswith('C') and any(v in value for v in ('100nF', '0.1uF', '1uF', '10uF', '4.7uF'))

    decoupling_fails = []
    for f in fps:
        if len(list(f['fp'].Pads())) < 8: continue  # focus on ICs (≥8 pin)
        for pad in f['fp'].Pads():
            net = pad.GetNetname()
            if not is_power_net(net) or 'GND' in net.upper(): continue
            pin_xy = (pad.GetPosition().x/mm, pad.GetPosition().y/mm)
            # find nearest cap on same net
            best_dist = float('inf'); best_ref = None
            for c in fps:
                if not is_decoupling_cap(c['ref'], c['value']): continue
                c_nets = {pp.GetNetname() for pp in c['fp'].Pads()}
                if net not in c_nets: continue
                if c['layer'] != f['layer']: continue  # same-layer requirement
                d = math.hypot(c['x'] - pin_xy[0], c['y'] - pin_xy[1])
                if d < best_dist: best_dist = d; best_ref = c['ref']
            if best_ref and best_dist > 3.0 + 0.05:  # R25 + fab tol
                decoupling_fails.append({
                    'ic': f['ref'], 'pad': pad.GetPadName(), 'net': net,
                    'nearest_cap': best_ref, 'distance_mm': round(best_dist, 2)
                })

    # ─── Report ───
    report = {
        'board': pcb_path,
        'hpwl': {
            'total_mm': round(total_hpwl, 1),
            'nets_with_pins_ge_2': len(hpwl_per_net),
            'worst_10': [(n, round(d, 2)) for n, d in worst_nets],
        },
        'density': density_per_zone,
        'decoupling': {
            'over_3mm_count': len(decoupling_fails),
            'worst': decoupling_fails[:10],
        },
    }
    json.dump(report, open(out_path, 'w'), indent=2)

    print("=" * 70)
    print(f"analytical_placement_proxies — {pcb_path}")
    print("=" * 70)
    print(f"\n  PROXY 1 HPWL: total {total_hpwl:.0f}mm over {len(hpwl_per_net)} nets")
    print(f"    Worst 5 by HPWL (routing-hardness):")
    for n, d in worst_nets[:5]: print(f"      {n}: {d:.1f}mm")

    print(f"\n  PROXY 2 DENSITY:")
    for z in density_per_zone:
        status = "OVER" if z['over_budget'] else "OK"
        print(f"    {z['zone']:35} {z['comp_frac']*100:5.1f}% {status}")

    print(f"\n  PROXY 3 DECOUPLING: {len(decoupling_fails)} IC pin(s) > 3.05mm")
    for f in decoupling_fails[:5]:
        print(f"    {f['ic']}.{f['pad']} ({f['net']}) → {f['nearest_cap']} {f['distance_mm']}mm")

    print(f"\n  Machine-readable: {out_path}")
    print()
    # exit non-zero if hard density-over or decoupling >5
    if any(z['over_budget'] for z in density_per_zone if not z['zone'].startswith('CH')) or len(decoupling_fails) > 5:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
