#!/usr/bin/env python3
"""
audit_jlc_dfm.py — G_M1/G_M2/G_M3 combined JLC manufacturing DFM gate.

Proactive 2026-05-26 (catch class: fab rejection from below-spec geometry).
JLC PCBA capability (2-layer + multilayer 2024+, from jlcpcb.com/capabilities):

  Min trace width      0.10mm (4mil) — 1oz/oz; 0.13mm for 2oz; 0.20mm for 3oz
  Min via drill        0.30mm — through; 0.20mm for HDI/blind
  Min annular ring     0.13mm (5mil)
  Min hole-to-hole     0.20mm
  Min copper-to-edge   0.20mm

Our board uses 8L stackup with 3oz inner heat layers, so 0.20mm min trace
on those layers per JLC. Default 0.13mm for signal layers.

Combined audit (3 sub-checks, all in one runner):
  1. Min trace width per layer
  2. Min via drill
  3. Min annular ring (via copper diameter - drill diameter / 2 ≥ 0.13mm)

Exit 0 = all PASS, 1 = any spec violation.

Usage:
  python3 audit_jlc_dfm.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# JLC spec floors
MIN_TRACE_1OZ = 0.10
MIN_TRACE_3OZ = 0.20
MIN_VIA_DRILL = 0.30
MIN_ANNULAR = 0.13


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)

    print(f"=== JLC DFM combined audit: {Path(board_path).name} ===")
    print(f"Min trace: 0.10mm (1oz) / 0.20mm (3oz)")
    print(f"Min via drill: {MIN_VIA_DRILL}mm · Min annular ring: {MIN_ANNULAR}mm\n")

    fails = []
    track_count = 0
    via_count = 0

    # Identify which layers are 3oz heavy-copper
    # We use layer-name pattern: layers tagged "3oz" in stackup
    heavy_layers = set()
    for layer_id in range(pcbnew.PCB_LAYER_ID_COUNT):
        name = board.GetLayerName(layer_id)
        if name and "3oz" in name.lower():
            heavy_layers.add(layer_id)

    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            via_count += 1
            drill_mm = pcbnew.ToMM(t.GetDrillValue())
            width_mm = pcbnew.ToMM(t.GetWidth())  # copper outer diameter
            annular = (width_mm - drill_mm) / 2.0
            if drill_mm < MIN_VIA_DRILL:
                fails.append(f"  [FAIL] Via @({pcbnew.ToMM(t.GetPosition().x):.2f},"
                             f"{pcbnew.ToMM(t.GetPosition().y):.2f}): drill {drill_mm:.3f}mm < {MIN_VIA_DRILL}mm")
            if annular < MIN_ANNULAR:
                fails.append(f"  [FAIL] Via @({pcbnew.ToMM(t.GetPosition().x):.2f},"
                             f"{pcbnew.ToMM(t.GetPosition().y):.2f}): annular {annular:.3f}mm < {MIN_ANNULAR}mm "
                             f"(width {width_mm:.2f}, drill {drill_mm:.2f})")
        elif isinstance(t, pcbnew.PCB_TRACK):
            track_count += 1
            w_mm = pcbnew.ToMM(t.GetWidth())
            layer = t.GetLayer()
            floor = MIN_TRACE_3OZ if layer in heavy_layers else MIN_TRACE_1OZ
            if w_mm < floor:
                fails.append(f"  [FAIL] Track on layer {board.GetLayerName(layer)}: "
                             f"width {w_mm:.3f}mm < {floor}mm floor")

    print(f"Audited: {track_count} tracks, {via_count} vias\n")

    if track_count == 0 and via_count == 0:
        print("INFO: board has no tracks or vias yet — gate inert pre-routing")
        sys.exit(0)

    if fails:
        for f in fails[:15]:
            print(f)
        if len(fails) > 15:
            print(f"  ... +{len(fails)-15} more")
        print(f"\nRESULT: FAIL — {len(fails)} JLC DFM violations (fab will reject)")
        sys.exit(1)
    print("RESULT: PASS — all tracks + vias meet JLC SMT manufacturing capability")


if __name__ == "__main__":
    main()
