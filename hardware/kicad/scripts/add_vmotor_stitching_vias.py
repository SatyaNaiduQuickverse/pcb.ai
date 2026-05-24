#!/usr/bin/env python3
"""add_vmotor_stitching_vias.py — Queue #3 (master 2026-05-24).

Bump +VMOTOR plane via count to ≥360 for 280A continuous current capability.
Adds stitch vias on a regular grid within the +VMOTOR zone fill on In3.Cu,
avoiding collision with existing pads/vias.

Via spec (consistent with PR-routing-final-v2):
  - 0.6mm diameter, 0.3mm drill
  - F.Cu ↔ B.Cu (full stack)
  - Net = +VMOTOR

Stitching strategy:
  - Compute regular grid (3mm pitch) covering board area
  - For each grid point: check if +VMOTOR zone covers it on In3.Cu
  - Check no collision with existing via (≥1.5mm spacing) or pad (≥0.5mm)
  - Add via, repeat until count ≥ target

Engineering rationale: 0.3mm drill via at 1oz inner-layer copper carries
~2-3A continuous (IPC-2152). For 280A → 140 vias minimum; ≥360 vias gives
2.5× safety factor for thermal de-rating + current concentration at
high-density areas.
"""
import pcbnew
import math


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

TARGET_VMOTOR_VIA_COUNT = 360
VIA_DIA_MM = 0.6
VIA_DRILL_MM = 0.3
GRID_PITCH_MM = 3.0
MIN_VIA_SPACING_MM = 1.5
MIN_PAD_CLEARANCE_MM = 0.5

# Bounds inset from board edge (avoid edge collision)
EDGE_INSET = 2.0


def main():
    board = pcbnew.LoadBoard(PCB)

    # Find +VMOTOR zone on In3.Cu
    vmotor_zone = None
    for z in board.Zones():
        if z.GetNetname() == '+VMOTOR' and z.IsOnLayer(pcbnew.In3_Cu):
            vmotor_zone = z
            break
    if vmotor_zone is None:
        print("ERROR: +VMOTOR zone on In3.Cu not found")
        return 1

    # Get +VMOTOR net pointer for the new vias
    vmotor_net = None
    for n in board.GetNetsByName().values():
        if n.GetNetname() == '+VMOTOR':
            vmotor_net = n
            break
    if vmotor_net is None:
        print("ERROR: +VMOTOR net not found")
        return 1

    # Build existing-via positions and pad-bbox lists
    existing_vias = []
    pad_bbox = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            existing_vias.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            pad_bbox.append((pcbnew.ToMM(bb.GetLeft()) - MIN_PAD_CLEARANCE_MM,
                             pcbnew.ToMM(bb.GetTop()) - MIN_PAD_CLEARANCE_MM,
                             pcbnew.ToMM(bb.GetRight()) + MIN_PAD_CLEARANCE_MM,
                             pcbnew.ToMM(bb.GetBottom()) + MIN_PAD_CLEARANCE_MM))

    initial_count = sum(1 for t in board.GetTracks()
                        if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == '+VMOTOR')
    print(f"Initial +VMOTOR via count: {initial_count}")
    print(f"Target: ≥{TARGET_VMOTOR_VIA_COUNT}")
    needed = max(0, TARGET_VMOTOR_VIA_COUNT - initial_count)
    print(f"To add: {needed}")
    if needed == 0:
        return 0

    # Get +VMOTOR filled polygon on In3.Cu for in-poly test
    filled_polys = vmotor_zone.GetFilledPolysList(pcbnew.In3_Cu)

    # Get board outline bbox to bound grid
    edges = []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            edges.append(pcbnew.ToMM(d.GetStart().x))
            edges.append(pcbnew.ToMM(d.GetEnd().x))
            edges.append(pcbnew.ToMM(d.GetStart().y))
            edges.append(pcbnew.ToMM(d.GetEnd().y))
    if not edges:
        x0, y0, x1, y1 = 2, 2, 98, 98
    else:
        # Edges contain x's and y's interleaved; sort to get bounds
        xs = [edges[i] for i in range(0, len(edges), 2)]
        ys = [edges[i] for i in range(1, len(edges), 2)]
        # Actually need separate iteration over getstart/getend
        xs = []; ys = []
        for d in board.GetDrawings():
            if d.GetLayer() == pcbnew.Edge_Cuts:
                xs.append(pcbnew.ToMM(d.GetStart().x))
                xs.append(pcbnew.ToMM(d.GetEnd().x))
                ys.append(pcbnew.ToMM(d.GetStart().y))
                ys.append(pcbnew.ToMM(d.GetEnd().y))
        x0, y0, x1, y1 = min(xs)+EDGE_INSET, min(ys)+EDGE_INSET, max(xs)-EDGE_INSET, max(ys)-EDGE_INSET

    print(f"Grid bounds: x[{x0:.1f},{x1:.1f}] y[{y0:.1f},{y1:.1f}]")

    added = 0
    skipped_outside = 0
    skipped_via_close = 0
    skipped_pad_close = 0
    # Try grid points
    x = x0
    while x <= x1 and added < needed:
        y = y0
        while y <= y1 and added < needed:
            # Check if (x, y) inside +VMOTOR zone fill
            vec = pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6))
            if not filled_polys.Contains(vec):
                skipped_outside += 1
                y += GRID_PITCH_MM
                continue
            # Via-too-close check
            too_close_via = False
            for (vx, vy) in existing_vias:
                if math.hypot(vx - x, vy - y) < MIN_VIA_SPACING_MM:
                    too_close_via = True; break
            if too_close_via:
                skipped_via_close += 1
                y += GRID_PITCH_MM
                continue
            # Pad-bbox check
            in_pad = False
            for (bx0, by0, bx1, by1) in pad_bbox:
                if bx0 <= x <= bx1 and by0 <= y <= by1:
                    in_pad = True; break
            if in_pad:
                skipped_pad_close += 1
                y += GRID_PITCH_MM
                continue
            # Place via
            v = pcbnew.PCB_VIA(board)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetPosition(vec)
            v.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
            v.SetWidth(pcbnew.FromMM(VIA_DIA_MM))
            v.SetNet(vmotor_net)
            board.Add(v)
            existing_vias.append((x, y))
            added += 1
            y += GRID_PITCH_MM
        x += GRID_PITCH_MM

    print(f"Vias added: {added}")
    print(f"Skipped — outside zone: {skipped_outside}")
    print(f"Skipped — too close to via: {skipped_via_close}")
    print(f"Skipped — pad collision: {skipped_pad_close}")

    final_count = sum(1 for t in board.GetTracks()
                      if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == '+VMOTOR')
    print(f"\nFinal +VMOTOR via count: {final_count} (target ≥{TARGET_VMOTOR_VIA_COUNT})")
    board.Save(PCB)
    return 0 if final_count >= TARGET_VMOTOR_VIA_COUNT else 1


if __name__ == "__main__":
    raise SystemExit(main())
