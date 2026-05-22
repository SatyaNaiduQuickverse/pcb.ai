"""Phase 4b-redo3 — signal-density gate (D/S formula, per master 2026-05-22).

Computes signal-routing demand (D) vs supply (S) for the current .kicad_pcb
placement, applying the master-locked threshold:
  D/S < 0.85  → PASS (15% margin for router worst-case)
  D/S < 1.00  → MARGINAL (try autoroute, expect <95%)
  D/S ≥ 1.00 → FAIL (placement defect, requires redo)

Also computes per-zone D/S (4 zones: NW, NE, SW, SE quadrants) — single zone
> 0.85 is a local hotspot to relieve before whole-board passes.

DEMAND:
  D = Σ HPWL_i × W_eff
    HPWL_i = half-perimeter wirelength of net i's pad bounding box
    HPWL detour factor = 1.5 (master directive — accounts for Manhattan routing)
    W_eff = trace_width + 2 × clearance = 0.15 + 0.30 = 0.45 mm
    Signal nets = all nets EXCEPT plane-served (GND, +VMOTOR, +5V_FC, +5V_PI5,
                  +5V_AI, +9V_VTX1, +9V_VTX2, +3V3, BATGND, +BATT, +BATT_NTC)

SUPPLY:
  S_layer = A_board × (1 − f_components) × η_router
    A_board from kicad_pcb outline bbox
    f_components computed from pad area / board area per layer
    η_router = 0.40 (Freerouting 2-signal-layer empirical efficiency, conservative)
  Total S = S_F.Cu + S_B.Cu (2 signal layers)
"""
import pcbnew
import sys
import math
from collections import defaultdict

PCB_FILE = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Plane-served nets — Phase 5b-retry: list refined to match Freerouting empirical
# behavior (grep'd from freerouting.log "Queuing item" lines). Only GND + +VMOTOR
# are fully plane-served by current dsn_inject_planes.py. The 5V/9V/3V3 rails
# remain routed as signal traces (no dedicated inner plane defined for them).
PLANE_NETS = {
    "GND",          # In1.Cu full-board plane
    "+VMOTOR",      # In2.Cu top-half plane
}

# Routing model constants (master-locked)
W_EFF_MM = 0.45             # trace_width (0.15) + 2 × clearance (0.15)
DETOUR_FACTOR = 1.5         # HPWL × this = expected Manhattan-routed length
ETA_ROUTER_2LAYER = 0.40    # Freerouting 2-signal-layer efficiency (empirical)
ETA_ROUTER_3LAYER = 0.55    # if In3.Cu promoted to signal layer
GATE_PASS = 0.85
GATE_MARGINAL = 1.00


def main(num_signal_layers=2):
    board = pcbnew.LoadBoard(PCB_FILE)
    bbox = board.GetBoardEdgesBoundingBox()
    board_w_mm = bbox.GetWidth() / 1e6
    board_h_mm = bbox.GetHeight() / 1e6
    A_board = board_w_mm * board_h_mm
    print(f"=== Phase 4b-redo3 signal-density check ===")
    print(f"Board: {board_w_mm:.1f} × {board_h_mm:.1f} mm = {A_board:.0f} mm²")
    print(f"Layers used for signal routing: {num_signal_layers}")
    print(f"W_eff = {W_EFF_MM:.2f} mm; detour factor = {DETOUR_FACTOR}; "
          f"η_router = {ETA_ROUTER_2LAYER if num_signal_layers == 2 else ETA_ROUTER_3LAYER}")

    # ─── Gather pad positions per net ───
    nets_by_name = board.GetNetsByName()
    pad_pos_by_net = defaultdict(list)
    pad_area_by_layer = defaultdict(float)   # F.Cu / B.Cu in mm²
    total_pads = 0

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            netname = pad.GetNetname()
            pos = pad.GetPosition()
            x_mm = pos.x / 1e6
            y_mm = pos.y / 1e6
            pad_pos_by_net[netname].append((x_mm, y_mm))
            # Pad area approximation (rectangular bbox)
            sz = pad.GetSize()
            area = (sz.x / 1e6) * (sz.y / 1e6)
            # Layer assignment
            if pad.IsOnLayer(pcbnew.F_Cu):
                pad_area_by_layer["F.Cu"] += area
            if pad.IsOnLayer(pcbnew.B_Cu):
                pad_area_by_layer["B.Cu"] += area
            total_pads += 1

    print(f"\nTotal pads scanned: {total_pads}")
    print(f"Nets with pads: {len(pad_pos_by_net)}")

    # ─── Compute DEMAND ───
    # Per-net HPWL × W_eff × detour for signal nets only
    signal_demand_mm2 = 0.0
    plane_net_count = 0
    signal_net_count = 0
    per_zone_demand = defaultdict(float)   # zone key → mm²
    zone_bounds = [
        ("NW", 0, board_w_mm / 2, 0, board_h_mm / 2),
        ("NE", board_w_mm / 2, board_w_mm, 0, board_h_mm / 2),
        ("SW", 0, board_w_mm / 2, board_h_mm / 2, board_h_mm),
        ("SE", board_w_mm / 2, board_w_mm, board_h_mm / 2, board_h_mm),
    ]

    for netname, positions in pad_pos_by_net.items():
        if not netname or netname == "":
            continue       # unconnected pads
        if netname in PLANE_NETS:
            plane_net_count += 1
            continue
        # HPWL = (max_x − min_x) + (max_y − min_y) [half-perimeter]
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        hpwl_mm = (max(xs) - min(xs)) + (max(ys) - min(ys))
        net_demand_mm2 = hpwl_mm * DETOUR_FACTOR * W_EFF_MM
        signal_demand_mm2 += net_demand_mm2
        signal_net_count += 1
        # Zone assignment by net's bbox center
        cx = (max(xs) + min(xs)) / 2
        cy = (max(ys) + min(ys)) / 2
        for name, x0, x1, y0, y1 in zone_bounds:
            if x0 <= cx < x1 and y0 <= cy < y1:
                per_zone_demand[name] += net_demand_mm2
                break

    print(f"\nDEMAND analysis:")
    print(f"  Signal nets: {signal_net_count}; plane-served: {plane_net_count}")
    print(f"  Total signal demand D = {signal_demand_mm2:.0f} mm² (sum of HPWL × {DETOUR_FACTOR} × {W_EFF_MM})")

    # ─── Compute SUPPLY ───
    f_components_fcu = pad_area_by_layer["F.Cu"] / A_board
    f_components_bcu = pad_area_by_layer["B.Cu"] / A_board
    eta = ETA_ROUTER_2LAYER if num_signal_layers == 2 else ETA_ROUTER_3LAYER
    s_fcu = A_board * (1 - f_components_fcu) * eta
    s_bcu = A_board * (1 - f_components_bcu) * eta
    s_in3 = 0
    if num_signal_layers == 3:
        # Assume In3.Cu has very few pad-blocked area (just through-hole pads)
        s_in3 = A_board * (1 - 0.05) * eta
    s_total = s_fcu + s_bcu + s_in3

    print(f"\nSUPPLY analysis:")
    print(f"  F.Cu pad-blocked fraction: {f_components_fcu:.3f} ({pad_area_by_layer['F.Cu']:.0f}/{A_board:.0f} mm²)")
    print(f"  B.Cu pad-blocked fraction: {f_components_bcu:.3f} ({pad_area_by_layer['B.Cu']:.0f}/{A_board:.0f} mm²)")
    print(f"  S_F.Cu = {s_fcu:.0f} mm² ({A_board:.0f} × (1−{f_components_fcu:.3f}) × {eta})")
    print(f"  S_B.Cu = {s_bcu:.0f} mm²")
    if s_in3:
        print(f"  S_In3.Cu = {s_in3:.0f} mm² (signal-promoted)")
    print(f"  Total S = {s_total:.0f} mm²")

    # ─── Gate ───
    ds_ratio = signal_demand_mm2 / s_total
    print(f"\n=== D/S = {signal_demand_mm2:.0f} / {s_total:.0f} = {ds_ratio:.3f} ===")
    if ds_ratio < GATE_PASS:
        verdict = f"PASS ({ds_ratio:.3f} < {GATE_PASS}) — 15%+ margin"
        exit_code = 0
    elif ds_ratio < GATE_MARGINAL:
        verdict = f"MARGINAL ({GATE_PASS} ≤ {ds_ratio:.3f} < {GATE_MARGINAL}) — autoroute likely <95%"
        exit_code = 1
    else:
        verdict = f"FAIL ({ds_ratio:.3f} ≥ {GATE_MARGINAL}) — placement defect, redo required"
        exit_code = 2
    print(f"Verdict: {verdict}")

    # ─── Per-zone (Phase 5b-retry path iii — refine per-zone supply) ───
    # Compute per-zone pad area separately (was naive s_total/4 — overstated NW
    # which has higher battery+buck pad density than other quadrants).
    print(f"\nPer-zone D/S (quadrants — refined per-zone supply):")
    A_zone = A_board / 4
    pad_area_per_zone_fcu = defaultdict(float)
    pad_area_per_zone_bcu = defaultdict(float)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pos = pad.GetPosition()
            x_mm = pos.x / 1e6
            y_mm = pos.y / 1e6
            for name, x0, x1, y0, y1 in zone_bounds:
                if x0 <= x_mm < x1 and y0 <= y_mm < y1:
                    sz = pad.GetSize()
                    area = (sz.x / 1e6) * (sz.y / 1e6)
                    if pad.IsOnLayer(pcbnew.F_Cu):
                        pad_area_per_zone_fcu[name] += area
                    if pad.IsOnLayer(pcbnew.B_Cu):
                        pad_area_per_zone_bcu[name] += area
                    break
    for name, *_ in zone_bounds:
        f_zone_fcu = pad_area_per_zone_fcu[name] / A_zone
        f_zone_bcu = pad_area_per_zone_bcu[name] / A_zone
        s_zone_fcu = A_zone * max(0, 1 - f_zone_fcu) * eta
        s_zone_bcu = A_zone * max(0, 1 - f_zone_bcu) * eta
        s_zone_in3 = A_zone * 0.95 * eta if num_signal_layers == 3 else 0
        s_zone = s_zone_fcu + s_zone_bcu + s_zone_in3
        d = per_zone_demand.get(name, 0)
        r = d / s_zone if s_zone > 0 else 0
        flag = " ← hotspot" if r > GATE_PASS else ""
        print(f"  {name}: D={d:.0f}; f_F={f_zone_fcu:.2f}, f_B={f_zone_bcu:.2f}; S={s_zone:.0f}; D/S={r:.3f}{flag}")

    return exit_code


if __name__ == "__main__":
    num_layers = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    sys.exit(main(num_layers))
