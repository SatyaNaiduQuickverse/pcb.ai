#!/usr/bin/env python3
"""grid_placement_v1.py — segregated experiment per Sai 2026-05-26.

Sai approval: "Full commitment" (grid placement strategy). But experiment in
segregated dir first; surface results before promotion to main scripts/.

GOAL: produce GRID-SNAPPED anchor positions for CH1 major components that:
  - Snap to 1.0mm primary grid (0.1mm fine grid for sub-mm offsets)
  - Respect physics constraints (sub-zone, mount KO, highway, etc.)
  - Minimize HPWL (total trace length proxy)
  - Honor BILATERAL HS/LS layer assignment

OUTPUT: dict {ref: (grid_x, grid_y, layer, sub_zone)} compatible with worker's
bring_selected as anchor positions for major ICs. Passives still placed by
worker's connectivity-driven spiral around their parent anchors.

This is COMPLEMENTARY to bring_selected, NOT a replacement. Worker uses these
grid-snapped anchors as input; passives flow around them by current algorithm.

ALGORITHM (greedy, deterministic — no annealing yet):
  1. For each major IC (FET, MCU, driver, INA, op-amp) in placement-priority order:
     a. Compute "ideal" position from parametric engine
     b. Snap to 1mm grid
     c. Check forbidden zones — if hit, walk grid outward until clear
     d. Accept

NOT YET: simulated annealing, force-directed, full HPWL minimization. This is
the seed that proves whether grid-snap + physics-aware constraints produces
better results than free-coord bring_selected.

USAGE:
  python3 experiments/grid_placement/grid_placement_v1.py [--ch CH1]
"""
import os, sys, math
from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List

# Import parametric_placement from main scripts (read-only consumption)
SCRIPTS_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "..", "..", "hardware", "kicad", "scripts"))
sys.path.insert(0, SCRIPTS_DIR)
from parametric_placement import (BoardParameters, motor_pad_positions,
                                  ch_fet_anchors, ch_ic_anchors,
                                  placement_forbidden_zones, mirror_x, mirror_y)


@dataclass
class GridConfig:
    primary_cell_mm: float = 1.0
    fine_cell_mm:    float = 0.1
    search_max_cells: int  = 30  # max grid walk distance


def snap(value: float, cell: float) -> float:
    """Snap to nearest grid line."""
    return round(value / cell) * cell


def in_forbidden(x: float, y: float, body_w: float, body_h: float,
                 zones: List[Tuple[float,float,float,float,str]]) -> Optional[str]:
    bx0 = x - body_w/2; by0 = y - body_h/2
    bx1 = x + body_w/2; by1 = y + body_h/2
    for fx0, fy0, fx1, fy1, name in zones:
        if bx0 < fx1 and bx1 > fx0 and by0 < fy1 and by1 > fy0:
            return name
    return None


def walk_grid_for_slot(ideal_x: float, ideal_y: float, body_w: float, body_h: float,
                       g: GridConfig, p: BoardParameters,
                       zones: List, occupied: List[Tuple[float,float,float,float,str]]) -> Optional[Tuple[float,float]]:
    """Spiral-walk grid from ideal point until a free non-forbidden non-occupied slot found."""
    cell = g.primary_cell_mm
    sx = snap(ideal_x, cell); sy = snap(ideal_y, cell)
    # Try ideal first, then expanding rings
    for ring in range(g.search_max_cells):
        if ring == 0:
            candidates = [(sx, sy)]
        else:
            candidates = []
            for dx in range(-ring, ring+1):
                for dy in range(-ring, ring+1):
                    if abs(dx) == ring or abs(dy) == ring:
                        candidates.append((sx + dx*cell, sy + dy*cell))
        for cx, cy in candidates:
            why_fb = in_forbidden(cx, cy, body_w, body_h, zones)
            if why_fb: continue
            why_oc = in_forbidden(cx, cy, body_w, body_h, occupied)
            if why_oc: continue
            # Found slot
            return (cx, cy)
    return None


def place_ch1_majors(p: BoardParameters, g: GridConfig) -> Dict[str, Tuple[float,float,str,str,float,float]]:
    """Returns {ref: (x, y, layer, sub_zone, body_w, body_h)} for CH1 major ICs.

    body_w, body_h from typical footprints used in netlist:
      FET (PDFN5x6 or similar): 7.3 x 5.5 mm body
      MCU (QFN-32 / QFN-48): 6.31 x 6.31 mm
      Driver (QFN-16): 5.31 x 5.31 mm
      INA (SOIC-8): 3.25 x 2.92 mm
      Op-amp (SOT-23-5 or SOIC-8): same as INA
    """
    zones = placement_forbidden_zones(p)
    occupied: List[Tuple[float,float,float,float,str]] = []  # (x0,y0,x1,y1,ref)

    # Get parametric ideal positions
    fet_anchors = ch_fet_anchors('CH1', p)
    ic_anchors = ch_ic_anchors('CH1', p)

    BODY_DIM = {
        'Q5':  (7.3, 5.5), 'Q6':  (7.3, 5.5), 'Q7':  (7.3, 5.5),
        'Q8':  (7.3, 5.5), 'Q9':  (7.3, 5.5), 'Q10': (7.3, 5.5),
        'J19': (5.31, 5.31), 'J18': (6.31, 6.31),
        'J20': (3.25, 2.92), 'J21': (3.25, 2.92), 'J22': (3.25, 2.92),
        'U3':  (3.25, 2.92), 'U4':  (3.25, 2.92),
    }

    placed = {}
    # Per-layer occupied lists (BILATERAL: F.Cu HS-FET can sit at same XY as B.Cu LS-FET)
    occupied_per_layer: Dict[str, List[Tuple[float,float,float,float,str]]] = {
        'F.Cu': [], 'B.Cu': []
    }
    # Priority order: FETs first (most constrained), then driver, then MCU, then INAs, then op-amps
    order = ['Q5', 'Q6', 'Q7', 'Q8', 'Q9', 'Q10',  # FETs (HS first, then LS)
             'J19', 'J18',                          # Driver + MCU
             'J20', 'J21', 'J22',                   # INAs
             'U3', 'U4']                            # Op-amps

    for ref in order:
        if ref in fet_anchors:
            ideal_x, ideal_y, layer = fet_anchors[ref]
            sub_zone = 'FET_COL'
        elif ref in ic_anchors:
            ideal_x, ideal_y, layer, sub_zone = ic_anchors[ref]
        else:
            continue
        body_w, body_h = BODY_DIM[ref]
        # Forbidden zones are LAYER-AGNOSTIC (mount holes go through all layers)
        # Occupied lists are PER-LAYER (HS F.Cu can sit at same XY as LS B.Cu — bilateral)
        slot = walk_grid_for_slot(ideal_x, ideal_y, body_w, body_h, g, p,
                                  zones, occupied_per_layer[layer])
        if slot is None:
            placed[ref] = (None, None, layer, sub_zone, body_w, body_h)
            continue
        gx, gy = slot
        placed[ref] = (gx, gy, layer, sub_zone, body_w, body_h)
        # Mark occupied IN THIS LAYER (other layer free for paired component)
        occupied_per_layer[layer].append((gx-body_w/2, gy-body_h/2,
                                          gx+body_w/2, gy+body_h/2, ref))

    return placed


def report(placed):
    print("=" * 70)
    print(f"grid_placement_v1 result — {len(placed)} CH1 major components")
    print("=" * 70)
    print(f"{'REF':6} {'x':>7} {'y':>7} {'layer':>5} {'sub':>10} {'body':>10}")
    fails = 0
    for ref, (x, y, layer, sub, w, h) in placed.items():
        if x is None:
            print(f"  {ref:6} {'FAIL':>7} {'no slot':>7} {layer:>5} {sub:>10} {f'{w}×{h}':>10}")
            fails += 1
        else:
            print(f"  {ref:6} {x:7.1f} {y:7.1f} {layer:>5} {sub:>10} {f'{w}×{h}':>10}")
    print()
    if fails:
        print(f"  ❌ {fails} components failed to find grid slot")
    else:
        print(f"  ✅ all {len(placed)} components placed on grid")


def hpwl_estimate(placed):
    """Rough HPWL: sum of pairwise distances for connected components."""
    # For a real HPWL we'd need netlist; here use heuristic from group structure.
    # FET ↔ motor pad ↔ driver ↔ MCU ↔ INA chains
    pairs = [
        ('Q5', 'Q6'), ('Q7', 'Q8'), ('Q9', 'Q10'),  # HS-LS pairs (via cluster)
        ('Q5', 'J19'), ('Q7', 'J19'), ('Q9', 'J19'),  # FET gates ← driver
        ('J19', 'J18'),                                # driver ↔ MCU control
        ('J20', 'U4'), ('J21', 'U4'), ('J22', 'U4'),  # INA ↔ op-amp ADC
        ('U4', 'J18'), ('U3', 'J18'),                  # op-amp ↔ MCU ADC
    ]
    total = 0
    for a, b in pairs:
        if a in placed and b in placed:
            ax, ay = placed[a][0], placed[a][1]
            bx, by = placed[b][0], placed[b][1]
            if ax is not None and bx is not None:
                total += abs(ax-bx) + abs(ay-by)  # Manhattan
    return total


if __name__ == "__main__":
    p = BoardParameters()
    g = GridConfig()
    placed = place_ch1_majors(p, g)
    report(placed)
    print()
    hpwl = hpwl_estimate(placed)
    print(f"  HPWL Manhattan estimate (13-pair canonical): {hpwl:.1f} mm")
    print(f"  Compare with current bring_selected placement — TBD measure")
