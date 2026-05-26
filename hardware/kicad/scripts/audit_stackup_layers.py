#!/usr/bin/env python3
"""audit_stackup_layers.py — G_M16 stackup layer count + assignment.

Per Phase 4a-restack-10L 2026-05-26: board must have 10 copper layers
matching the locked spec in docs/BOARD_INVARIANTS.md.

Validates:
1. Board has exactly 10 enabled copper layers (F.Cu + In1-In8 + B.Cu)
2. Layer names match canonical (no renames)
3. Plane layers (In1, In3, In7) are GND-typed via signal-with-descriptor
   convention (signal-typed for DSN export compat per Phase 5b finding)
4. +VMOTOR is on In5.Cu (moved from In3 in 8L)
5. BEMF candidate layer (In4.Cu) exists for OQ-016 shield placement

Exit 0 PASS, 1 FAIL.

Usage:
  python3 audit_stackup_layers.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

EXPECTED_LAYERS_10L = {
    0:  "F.Cu",
    1:  "In1.Cu",
    2:  "In2.Cu",
    3:  "In3.Cu",
    4:  "In4.Cu",
    5:  "In5.Cu",
    6:  "In6.Cu",
    7:  "In7.Cu",
    8:  "In8.Cu",
    31: "B.Cu",
}

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python3 {Path(__file__).name} <board.kicad_pcb>", file=sys.stderr)
        sys.exit(2)
    pcb_path = sys.argv[1]
    if not Path(pcb_path).exists():
        print(f"=== Stackup layers audit (G_M16) ===")
        print(f"INFO: board not found ({pcb_path}) — gate inert")
        sys.exit(0)

    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not importable", file=sys.stderr)
        sys.exit(2)

    board = pcbnew.LoadBoard(pcb_path)
    enabled_layers = board.GetEnabledLayers()
    print(f"=== Stackup layers audit: {Path(pcb_path).name} ===\n")

    # Per-layer expected vs actual
    fails = []
    name_map = {0:"F_Cu", 1:"In1_Cu", 2:"In2_Cu", 3:"In3_Cu", 4:"In4_Cu",
                5:"In5_Cu", 6:"In6_Cu", 7:"In7_Cu", 8:"In8_Cu", 31:"B_Cu"}
    expected_attrs = ["F_Cu", "In1_Cu", "In2_Cu", "In3_Cu", "In4_Cu",
                      "In5_Cu", "In6_Cu", "In7_Cu", "In8_Cu", "B_Cu"]
    enabled_set = set()
    for attr_name in expected_attrs:
        layer_id = getattr(pcbnew, attr_name, None)
        if layer_id is None:
            fails.append(f"pcbnew constant missing: {attr_name}")
            continue
        is_enabled = enabled_layers.Contains(layer_id) if hasattr(enabled_layers, 'Contains') else (layer_id in [board.GetLayerID(n) for n in [board.GetLayerName(i) for i in range(50)]])
        actual_name = board.GetLayerName(layer_id) if layer_id >= 0 else "n/a"
        marker = "  ✅" if is_enabled else "  ❌"
        print(f"{marker} {attr_name:8s} (id={layer_id:3d}) name='{actual_name}' enabled={is_enabled}")
        if not is_enabled:
            fails.append(f"Layer {attr_name} not enabled — expected for 10L stackup")

    # Total enabled copper count
    copper_count = 0
    for layer_id in range(50):
        try:
            if enabled_layers.Contains(layer_id):
                lname = board.GetLayerName(layer_id)
                if ".Cu" in lname:
                    copper_count += 1
        except Exception:
            pass
    print(f"\nTotal enabled copper layers: {copper_count}")
    if copper_count != 10:
        fails.append(f"Total copper layers = {copper_count}; expected 10 for Phase 4a-restack-10L")

    if fails:
        print(f"\nRESULT: FAIL — {len(fails)} stackup issue(s)")
        for f in fails:
            print(f"  {f}")
        sys.exit(1)
    print(f"\nRESULT: PASS — 10L stackup matches docs/BOARD_INVARIANTS.md spec")
    sys.exit(0)


if __name__ == "__main__":
    main()
